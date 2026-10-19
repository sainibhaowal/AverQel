from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from base64 import b64decode, b64encode
from email.message import EmailMessage
from email.utils import parseaddr
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import TypeVar, cast

import httpx
import redis
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import DEFAULT_JWT_SECRET, Settings, get_settings
from app.core.errors import ApiError
from app.system.schemas.public_contact import (
    PublicContactAccepted,
    PublicContactCreate,
    PublicContactStatusResponse,
    PublicContactVerificationAccepted,
    PublicContactVerificationConfirm,
    PublicContactVerificationRequest,
    PublicContactVerificationSent,
    is_valid_email_address,
)
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.smtp_client import smtp_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["public-contact"])
MAX_CONTACT_REQUEST_BYTES = 40 * 1024
MAX_CONTACT_VERIFICATION_REQUEST_BYTES = 4 * 1024
MAX_RESEND_WEBHOOK_BYTES = 64 * 1024
RESEND_WEBHOOK_TOLERANCE_SECONDS = 300
CONTACT_OTP_TTL_SECONDS = 600
CONTACT_VERIFICATION_TOKEN_TTL_SECONDS = 1800
CONTACT_OTP_MAX_ATTEMPTS = 5
_REDIS_CONNECT_TIMEOUT_SECONDS = 2.0
_REDIS_SOCKET_TIMEOUT_SECONDS = 2.0
_CONTACT_EMAIL_LOGO_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "averqel-contact-email-logo.png"
)
CONTACT_REQUEST_BODY = {
    "required": True,
    "content": {"application/json": {"schema": PublicContactCreate.model_json_schema()}},
}
CONTACT_VERIFICATION_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {"schema": PublicContactVerificationRequest.model_json_schema()}
    },
}
CONTACT_VERIFICATION_CONFIRM_BODY = {
    "required": True,
    "content": {
        "application/json": {"schema": PublicContactVerificationConfirm.model_json_schema()}
    },
}

_VERIFY_CONTACT_OTP_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local challenge = cjson.decode(raw)
if challenge.email_hash ~= ARGV[1] then return -1 end
local ttl = redis.call('PTTL', KEYS[1])
if ttl <= 0 then
    redis.call('DEL', KEYS[1])
    return 0
end
challenge.attempts = tonumber(challenge.attempts or 0) + 1
if challenge.attempts > tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1])
    return -2
end
if challenge.code_hash == ARGV[2] then
    local stored = redis.call('SET', KEYS[2], ARGV[1], 'EX', tonumber(ARGV[4]), 'NX')
    if not stored then return -3 end
    redis.call('DEL', KEYS[1])
    return 1
end
if challenge.attempts >= tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1])
    return -2
end
redis.call('PSETEX', KEYS[1], ttl, cjson.encode(challenge))
return 0
"""

_CONSUME_CONTACT_VERIFICATION_SCRIPT = """
local email_hash = redis.call('GET', KEYS[1])
if not email_hash then return 0 end
if email_hash ~= ARGV[1] then return -1 end
redis.call('DEL', KEYS[1])
return 1
"""

_ContactPayload = TypeVar("_ContactPayload", bound=BaseModel)


class _PlainTextHTMLParser(HTMLParser):
    """Convert an HTML-only inbound message to readable plain text."""

    _BLOCK_TAGS = {"br", "div", "li", "p", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text_email_body(received: dict[str, object]) -> str:
    text_body = received.get("text")
    if isinstance(text_body, str) and text_body.strip():
        return text_body.strip()

    html_body = received.get("html")
    if isinstance(html_body, str) and html_body.strip():
        parser = _PlainTextHTMLParser()
        parser.feed(html_body)
        return " ".join(" ".join(parser.parts).split())
    return "(This email did not contain readable text.)"


def _verify_resend_signature(
    *,
    body: bytes,
    webhook_id: str | None,
    timestamp: str | None,
    signatures: str | None,
    secret: str | None,
    now: int | None = None,
) -> bool:
    if not all((webhook_id, timestamp, signatures, secret)):
        return False
    if not secret or not secret.startswith("whsec_"):
        return False
    try:
        sent_at = int(timestamp or "")
        key = b64decode(secret.removeprefix("whsec_"), validate=True)
    except (ValueError, TypeError):
        return False
    if not key:
        return False

    current_time = int(time.time()) if now is None else now
    if abs(current_time - sent_at) > RESEND_WEBHOOK_TOLERANCE_SECONDS:
        return False

    signed_content = f"{webhook_id}.{timestamp}.".encode() + body
    expected = b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode("ascii")
    for item in (signatures or "").split():
        version, separator, signature = item.partition(",")
        if version == "v1" and separator and hmac.compare_digest(signature, expected):
            return True
    return False


def _mailbox(value: str | None) -> str | None:
    if not value or "\r" in value or "\n" in value:
        return None
    address = parseaddr(value)[1]
    if not address or not is_valid_email_address(address):
        return None
    return address


def _contact_delivery_configured(settings: Settings) -> bool:
    recipient = settings.public_contact_recipient
    sender = settings.public_contact_from
    return bool(
        settings.notification_smtp_host
        and settings.notification_smtp_starttls != settings.notification_smtp_implicit_tls
        and settings.notification_smtp_username
        and settings.notification_smtp_password
        and recipient
        and _mailbox(recipient) == recipient.strip()
        and sender
        and _mailbox(sender)
        and _contact_sender_domain_matches_smtp(settings)
    )


def _contact_sender_domain_matches_smtp(settings: Settings) -> bool:
    public_sender = _mailbox(settings.public_contact_from)
    smtp_sender = _mailbox(settings.notification_smtp_from)
    return bool(
        public_sender
        and smtp_sender
        and public_sender.rsplit("@", 1)[1].casefold() == smtp_sender.rsplit("@", 1)[1].casefold()
    )


def _contact_verification_configured(settings: Settings) -> bool:
    if not _contact_delivery_configured(settings):
        return False
    verification_sender = _mailbox(settings.public_contact_verification_from)
    configured_sender = _mailbox(settings.public_contact_from)
    return bool(
        verification_sender
        and configured_sender
        and settings.jwt_secret != DEFAULT_JWT_SECRET
        and verification_sender.rsplit("@", 1)[1].casefold()
        == configured_sender.rsplit("@", 1)[1].casefold()
        and settings.redis_url
    )


def _contact_hmac_key(settings: Settings) -> bytes:
    """Derive a purpose-specific key without storing raw addresses or OTPs."""
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        b"averqel:public-contact-email-verification:v1",
        hashlib.sha256,
    ).digest()


def _contact_email_fingerprint(email: str, settings: Settings) -> str:
    return hmac.new(
        _contact_hmac_key(settings), email.strip().casefold().encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _contact_otp_fingerprint(
    *, email_fingerprint: str, challenge_id: str, code: str, settings: Settings
) -> str:
    material = f"{challenge_id}:{email_fingerprint}:{code}".encode()
    return hmac.new(_contact_hmac_key(settings), material, hashlib.sha256).hexdigest()


@lru_cache(maxsize=8)
def _contact_verification_redis(redis_url: str) -> redis.Redis:
    return redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
        retry_on_timeout=False,
    )


def _contact_challenge_key(challenge_id: str) -> str:
    return f"public_contact:email_verification:challenge:{challenge_id}"


def _contact_verified_token_key(token: str) -> str:
    token_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"public_contact:email_verification:token:{token_fingerprint}"


def _rate_limit_public_contact(request: Request, settings: Settings) -> None:
    client_ip = request.client.host.strip() if request.client and request.client.host else "unknown"
    ip_fingerprint = hmac.new(
        settings.jwt_secret.encode("utf-8"), client_ip.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    RateLimitService(settings).enforce(
        request=request,
        key=f"rate_limit:public_contact:{ip_fingerprint}",
        limit=settings.rate_limit_public_contact_submissions_per_hour,
        window_seconds=3600,
        scope="public_contact",
    )


async def _read_json_payload(
    request: Request,
    *,
    model: type[_ContactPayload],
    max_bytes: int = MAX_CONTACT_REQUEST_BYTES,
) -> _ContactPayload:
    if "application/json" not in request.headers.get("content-type", "").lower():
        raise ApiError(
            code="UNSUPPORTED_MEDIA_TYPE",
            message="Send the contact form as JSON.",
            status_code=415,
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ApiError(
                    code="PAYLOAD_TOO_LARGE",
                    message="The contact form is too large.",
                    status_code=413,
                )
        except ValueError:
            raise ApiError(
                code="BAD_REQUEST",
                message="The contact request is invalid.",
                status_code=400,
            ) from None

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise ApiError(
                code="PAYLOAD_TOO_LARGE",
                message="The contact form is too large.",
                status_code=413,
            )
        body.extend(chunk)

    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ApiError(
            code="VALIDATION_ERROR",
            message="The contact form request is not valid JSON.",
            status_code=422,
        ) from None

    try:
        return model.model_validate(data)
    except ValidationError as exc:
        errors = exc.errors(include_input=False)
        raise ApiError(
            code="VALIDATION_ERROR",
            message="The contact form contains invalid fields.",
            status_code=422,
            details={
                "errors": [
                    {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                    for item in errors
                ]
            },
        ) from None


def _send_contact_email(payload: PublicContactCreate, settings: Settings) -> None:
    recipient = settings.public_contact_recipient
    sender_header = settings.public_contact_from
    smtp_username = settings.notification_smtp_username
    smtp_password = settings.notification_smtp_password
    if not _contact_delivery_configured(settings):
        raise RuntimeError("Public contact delivery is not configured")

    recipient_address = _mailbox(recipient)
    sender_address = _mailbox(sender_header)
    if not recipient_address or not sender_address:
        raise RuntimeError("Public contact email settings are invalid")

    message = EmailMessage()
    message["From"] = sender_header
    message["To"] = recipient_address
    message["Reply-To"] = payload.email
    message["Subject"] = f"AverQel contact: {payload.subject}"
    message["Message-ID"] = f"<averqel-contact-{uuid.uuid4()}@{sender_address.rsplit('@', 1)[-1]}>"
    message.set_content(
        "A visitor sent a message through the AverQel website contact form.\n\n"
        f"Name: {payload.name}\n"
        f"Reply email: {payload.email}\n"
        f"Subject: {payload.subject}\n\n"
        f"{payload.message}\n"
    )

    with smtp_connection(settings, timeout=12) as client:
        if not smtp_username or not smtp_password:
            raise RuntimeError("Public contact SMTP authentication is not configured")
        client.login(smtp_username, smtp_password)
        client.send_message(message)


def _send_contact_verification_email(
    *, email: str, code: str, challenge_id: str, settings: Settings
) -> None:
    sender_header = settings.public_contact_verification_from
    sender_address = _mailbox(sender_header)
    smtp_username = settings.notification_smtp_username
    smtp_password = settings.notification_smtp_password
    if not _contact_verification_configured(settings) or not sender_address:
        raise RuntimeError("Public contact email verification is not configured")

    message = EmailMessage()
    message["From"] = sender_header
    message["To"] = email
    message["Subject"] = "Your AverQel contact form verification code"
    message["Message-ID"] = (
        f"<averqel-contact-verification-{challenge_id}@{sender_address.rsplit('@', 1)[-1]}>"
    )
    message.set_content(
        "AverQel contact form — email verification\n\n"
        "Enter this code on the AverQel contact form to verify your email address and continue:\n\n"
        f"{code}\n\n"
        "This code expires in 10 minutes and can be used once. If you did not request this code, "
        "you can ignore this email."
    )
    message.add_alternative(_contact_verification_html(code), subtype="html")
    html_part = message.get_body(preferencelist=("html",))
    if html_part is None:
        raise RuntimeError("Public contact verification HTML body could not be created")
    html_part.add_related(
        _CONTACT_EMAIL_LOGO_PATH.read_bytes(),
        maintype="image",
        subtype="png",
        cid="<averqel-contact-email-logo>",
        disposition="inline",
    )

    with smtp_connection(settings, timeout=12) as client:
        if not smtp_username or not smtp_password:
            raise RuntimeError("Public contact SMTP authentication is not configured")
        client.login(smtp_username, smtp_password)
        client.send_message(message)


def _contact_verification_html(code: str) -> str:
    safe_code = escape(code)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>Verify your email for AverQel</title>
  </head>
  <body style="margin:0;padding:0;background-color:#eef3fb;color:#14213d;font-family:Arial,Helvetica,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      A one-time code is ready to verify your AverQel contact email.
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;background-color:#eef3fb;">
      <tr>
        <td align="center" style="padding:32px 14px;">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #dce5f2;border-radius:18px;overflow:hidden;">
            <tr>
              <td align="center" style="padding:22px 24px 18px;background-color:#ffffff;">
                <img src="cid:averqel-contact-email-logo" width="120" height="90" alt="AverQel" style="display:block;width:120px;height:90px;max-width:100%;border:0;outline:none;text-decoration:none;">
              </td>
            </tr>
            <tr>
              <td style="padding:0;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td width="34%" height="4" style="height:4px;background-color:#08cbe8;font-size:0;line-height:0;">&nbsp;</td>
                    <td width="33%" height="4" style="height:4px;background-color:#176efb;font-size:0;line-height:0;">&nbsp;</td>
                    <td width="33%" height="4" style="height:4px;background-color:#b210fc;font-size:0;line-height:0;">&nbsp;</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:32px 36px 30px;">
                <p style="margin:0 0 12px;color:#176efb;font-size:12px;font-weight:700;letter-spacing:1.4px;line-height:18px;">SECURE EMAIL VERIFICATION</p>
                <h1 style="margin:0 0 14px;color:#101b33;font-size:26px;font-weight:700;line-height:32px;">Verify your email</h1>
                <p style="margin:0 0 22px;color:#526078;font-size:16px;line-height:25px;">
                  Enter this code on the AverQel contact form to confirm this email address and continue with your message.
                </p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;background-color:#f3f7ff;border:1px solid #d9e6ff;border-radius:14px;">
                  <tr>
                    <td align="center" style="padding:20px 14px 22px;">
                      <p style="margin:0 0 8px;color:#61708a;font-size:12px;font-weight:700;letter-spacing:1.2px;line-height:18px;">YOUR ONE-TIME CODE</p>
                      <p style="margin:0;color:#101b33;font-family:'Courier New',Courier,monospace;font-size:32px;font-weight:700;letter-spacing:8px;line-height:42px;">{safe_code}</p>
                    </td>
                  </tr>
                </table>
                <p style="margin:21px 0 0;color:#526078;font-size:14px;line-height:22px;">
                  This code expires in <strong style="color:#263550;">10 minutes</strong> and can be used once.
                </p>
                <p style="margin:14px 0 0;color:#718096;font-size:13px;line-height:21px;">
                  If you didn’t request this code, you can safely ignore this email.
                </p>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:17px 24px;background-color:#f8faff;border-top:1px solid #e8edf5;color:#7a879a;font-size:12px;line-height:18px;">
                AverQel · Secure contact verification
              </td>
            </tr>
          </table>
          <p style="margin:16px 0 0;color:#8b96a8;font-size:11px;line-height:16px;">This message was sent because someone entered this address on the AverQel contact form.</p>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _rate_limit_contact_verification(
    *, request: Request, email: str, action: str, settings: Settings
) -> str:
    client_ip = request.client.host.strip() if request.client and request.client.host else "unknown"
    ip_material = f"{action}:{client_ip}".encode()
    ip_fingerprint = hmac.new(_contact_hmac_key(settings), ip_material, hashlib.sha256).hexdigest()
    limiter = RateLimitService(settings)
    limiter.enforce(
        request=request,
        key=f"rate_limit:public_contact_verification:{action}:ip:{ip_fingerprint}",
        limit=settings.rate_limit_public_contact_verification_ip_per_hour,
        window_seconds=3600,
        scope="public_contact_verification",
    )
    email_fingerprint = _contact_email_fingerprint(email, settings)
    if action == "request":
        limiter.enforce_counter(
            key=f"rate_limit:public_contact_verification:email:{email_fingerprint}",
            limit=settings.rate_limit_public_contact_verification_email_per_hour,
            window_seconds=3600,
            scope="public_contact_verification_email",
        )
    return email_fingerprint


def _issue_contact_verification(*, request: Request, email: str, settings: Settings) -> str:
    email_fingerprint = _rate_limit_contact_verification(
        request=request, email=email, action="request", settings=settings
    )
    challenge_id = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_fingerprint = _contact_otp_fingerprint(
        email_fingerprint=email_fingerprint,
        challenge_id=challenge_id,
        code=code,
        settings=settings,
    )
    challenge = json.dumps(
        {"email_hash": email_fingerprint, "code_hash": code_fingerprint, "attempts": 0},
        separators=(",", ":"),
        sort_keys=True,
    )
    client = _contact_verification_redis(settings.redis_url)
    challenge_key = _contact_challenge_key(challenge_id)
    if not client.set(challenge_key, challenge, ex=CONTACT_OTP_TTL_SECONDS, nx=True):
        raise RuntimeError("Unable to create a public contact verification challenge")

    try:
        _send_contact_verification_email(
            email=email,
            code=code,
            challenge_id=challenge_id,
            settings=settings,
        )
    except Exception:
        client.delete(challenge_key)
        raise
    return challenge_id


def _verify_contact_code(
    *, email: str, challenge_id: str, code: str, settings: Settings
) -> str | None:
    email_fingerprint = _contact_email_fingerprint(email, settings)
    code_fingerprint = _contact_otp_fingerprint(
        email_fingerprint=email_fingerprint,
        challenge_id=challenge_id,
        code=code,
        settings=settings,
    )
    verification_token = secrets.token_urlsafe(32)
    client = _contact_verification_redis(settings.redis_url)
    result = cast(
        int,
        client.eval(
            _VERIFY_CONTACT_OTP_SCRIPT,
            2,
            _contact_challenge_key(challenge_id),
            _contact_verified_token_key(verification_token),
            email_fingerprint,
            code_fingerprint,
            str(CONTACT_OTP_MAX_ATTEMPTS),
            str(CONTACT_VERIFICATION_TOKEN_TTL_SECONDS),
        ),
    )
    if result == 1:
        return verification_token
    if result == -3:
        raise RuntimeError("Unable to create a public contact verification token")
    return None


def _consume_contact_verification(
    *, email: str, verification_token: str, settings: Settings
) -> bool:
    email_fingerprint = _contact_email_fingerprint(email, settings)
    client = _contact_verification_redis(settings.redis_url)
    result = cast(
        int,
        client.eval(
            _CONSUME_CONTACT_VERIFICATION_SCRIPT,
            1,
            _contact_verified_token_key(verification_token),
            email_fingerprint,
        ),
    )
    return result == 1


def _contact_inbound_configured(settings: Settings) -> bool:
    return bool(
        settings.public_contact_resend_api_key
        and settings.public_contact_resend_webhook_secret
        and settings.public_contact_address
        and _mailbox(settings.public_contact_address) == settings.public_contact_address.strip()
        and settings.public_contact_recipient
        and _mailbox(settings.public_contact_recipient) == settings.public_contact_recipient.strip()
        and settings.public_contact_from
        and _mailbox(settings.public_contact_from)
        and _contact_sender_domain_matches_smtp(settings)
    )


def _contains_contact_address(recipients: object, contact_address: str) -> bool:
    if isinstance(recipients, str):
        values = [recipients]
    elif isinstance(recipients, list):
        values = recipients
    else:
        return False
    normalized_contact = contact_address.casefold()
    return any(
        isinstance(value, str)
        and (address := _mailbox(value)) is not None
        and address.casefold() == normalized_contact
        for value in values
    )


def _forward_resend_received_email(email_id: str, settings: Settings) -> None:
    """Forward one verified Resend inbound message without persisting its contents."""
    if not _contact_inbound_configured(settings):
        raise RuntimeError("Resend inbound forwarding is not configured")

    api_key = settings.public_contact_resend_api_key
    contact_address = settings.public_contact_address
    private_recipient = _mailbox(settings.public_contact_recipient)
    sender_header = settings.public_contact_from
    if not api_key or not contact_address or not private_recipient or not sender_header:
        raise RuntimeError("Resend inbound forwarding settings are invalid")

    try:
        parsed_email_id = str(uuid.UUID(email_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("Resend inbound email ID is invalid") from exc

    api_headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=12) as client:
        received_response = client.get(
            f"https://api.resend.com/emails/receiving/{parsed_email_id}",
            headers=api_headers,
        )
        received_response.raise_for_status()
        received_data = received_response.json()
        received = received_data.get("data", received_data)
        if not isinstance(received, dict) or not _contains_contact_address(
            received.get("to"), contact_address
        ):
            raise RuntimeError("Resend inbound email is not addressed to the contact address")

        original_from = received.get("from")
        original_sender = _mailbox(original_from) if isinstance(original_from, str) else None
        original_subject = received.get("subject")
        subject = original_subject if isinstance(original_subject, str) else "(no subject)"
        subject = " ".join(subject.replace("\r", " ").replace("\n", " ").split())[:180]
        original_body = _plain_text_email_body(received)
        body = (
            f"A message was sent to {contact_address}.\n\n"
            f"From: {original_from if isinstance(original_from, str) else '(unknown sender)'}\n"
            f"Subject: {subject}\n\n"
            f"{original_body}\n"
        )
        attachments = received.get("attachments")
        if isinstance(attachments, list) and attachments:
            body += (
                "\nThis message included attachment(s). They are available in the Resend "
                "Receiving dashboard; attachments are not included in this forwarded copy.\n"
            )

        forwarded_email: dict[str, object] = {
            "from": sender_header,
            "to": [private_recipient],
            "subject": f"Contact@ AverQel: {subject}",
            "text": body,
        }
        if original_sender:
            forwarded_email["reply_to"] = original_sender

        forward_response = client.post(
            "https://api.resend.com/emails",
            headers={
                **api_headers,
                "Idempotency-Key": f"averqel-inbound-{parsed_email_id}",
            },
            json=forwarded_email,
        )
        forward_response.raise_for_status()


@router.get("/status", response_model=PublicContactStatusResponse)
def get_contact_status(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> PublicContactStatusResponse:
    response.headers["Cache-Control"] = "no-store"
    return PublicContactStatusResponse(available=_contact_verification_configured(settings))


@router.post(
    "/verification/request",
    response_model=PublicContactVerificationSent,
    openapi_extra={"requestBody": CONTACT_VERIFICATION_REQUEST_BODY},
)
async def request_contact_email_verification(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> PublicContactVerificationSent:
    if not _contact_verification_configured(settings):
        raise ApiError(
            code="PUBLIC_CONTACT_UNAVAILABLE",
            message="Website contact email verification is not available on this server.",
            status_code=503,
        )
    payload = await _read_json_payload(
        request,
        model=PublicContactVerificationRequest,
        max_bytes=MAX_CONTACT_VERIFICATION_REQUEST_BYTES,
    )
    try:
        challenge_id = await run_in_threadpool(
            _issue_contact_verification,
            request=request,
            email=payload.email,
            settings=settings,
        )
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        # SMTP/Redis exceptions may include sensitive connection details.
        logger.warning("Public contact verification delivery failed (%s).", type(exc).__name__)
        raise ApiError(
            code="PUBLIC_CONTACT_VERIFICATION_FAILED",
            message="We could not send a verification code right now. Please try again later.",
            status_code=503,
        ) from None
    return PublicContactVerificationSent(
        challenge_id=challenge_id,
        expires_in_seconds=CONTACT_OTP_TTL_SECONDS,
    )


@router.post(
    "/verification/confirm",
    response_model=PublicContactVerificationAccepted,
    openapi_extra={"requestBody": CONTACT_VERIFICATION_CONFIRM_BODY},
)
async def confirm_contact_email_verification(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> PublicContactVerificationAccepted:
    if not _contact_verification_configured(settings):
        raise ApiError(
            code="PUBLIC_CONTACT_UNAVAILABLE",
            message="Website contact email verification is not available on this server.",
            status_code=503,
        )
    payload = await _read_json_payload(
        request,
        model=PublicContactVerificationConfirm,
        max_bytes=MAX_CONTACT_VERIFICATION_REQUEST_BYTES,
    )
    try:
        await run_in_threadpool(
            _rate_limit_contact_verification,
            request=request,
            email=payload.email,
            action="confirm",
            settings=settings,
        )
        verification_token = await run_in_threadpool(
            _verify_contact_code,
            email=payload.email,
            challenge_id=payload.challenge_id,
            code=payload.code,
            settings=settings,
        )
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Public contact verification check failed (%s).", type(exc).__name__)
        raise ApiError(
            code="PUBLIC_CONTACT_VERIFICATION_FAILED",
            message="We could not verify that code right now. Please try again later.",
            status_code=503,
        ) from None
    if not verification_token:
        raise ApiError(
            code="PUBLIC_CONTACT_VERIFICATION_INVALID",
            message="That code is invalid or expired. Request a new code and try again.",
            status_code=400,
        )
    return PublicContactVerificationAccepted(
        verification_token=verification_token,
        expires_in_seconds=CONTACT_VERIFICATION_TOKEN_TTL_SECONDS,
    )


@router.post(
    "",
    response_model=PublicContactAccepted,
    openapi_extra={"requestBody": CONTACT_REQUEST_BODY},
)
async def submit_public_contact(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> PublicContactAccepted:
    await run_in_threadpool(_rate_limit_public_contact, request, settings)
    payload = await _read_json_payload(request, model=PublicContactCreate)

    # Quietly accept automated honeypot submissions without forwarding them.
    if payload.website.strip():
        return PublicContactAccepted()

    if not _contact_verification_configured(settings):
        raise ApiError(
            code="PUBLIC_CONTACT_UNAVAILABLE",
            message="Website contact delivery is not available on this server.",
            status_code=503,
        )

    try:
        verified = await run_in_threadpool(
            _consume_contact_verification,
            email=payload.email,
            verification_token=payload.verification_token,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Public contact email verification state failed (%s).", type(exc).__name__)
        raise ApiError(
            code="PUBLIC_CONTACT_VERIFICATION_UNAVAILABLE",
            message="Email verification is temporarily unavailable. Please verify your email again.",
            status_code=503,
        ) from None
    if not verified:
        raise ApiError(
            code="PUBLIC_CONTACT_EMAIL_NOT_VERIFIED",
            message="Verify this email address before sending your message.",
            status_code=403,
        )

    try:
        await run_in_threadpool(_send_contact_email, payload, settings)
    except Exception as exc:  # noqa: BLE001
        # SMTP exception text can contain recipient details, so log only its class.
        logger.warning("Public contact delivery failed (%s).", type(exc).__name__)
        raise ApiError(
            code="PUBLIC_CONTACT_DELIVERY_FAILED",
            message="We could not send your message right now. Please try again later.",
            status_code=503,
        ) from None

    return PublicContactAccepted()


@router.post("/resend-inbound", include_in_schema=False)
async def receive_resend_inbound_email(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    if not _contact_inbound_configured(settings):
        return Response(status_code=503)

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_RESEND_WEBHOOK_BYTES:
            return Response(status_code=413)
        body.extend(chunk)

    if not _verify_resend_signature(
        body=bytes(body),
        webhook_id=request.headers.get("svix-id"),
        timestamp=request.headers.get("svix-timestamp"),
        signatures=request.headers.get("svix-signature"),
        secret=settings.public_contact_resend_webhook_secret,
    ):
        return Response(status_code=401)

    try:
        event = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return Response(status_code=400)
    if not isinstance(event, dict):
        return Response(status_code=400)
    if event.get("type") != "email.received":
        return Response(status_code=204)

    event_data = event.get("data")
    if not isinstance(event_data, dict):
        return Response(status_code=400)
    contact_address = settings.public_contact_address
    if not contact_address or not _contains_contact_address(event_data.get("to"), contact_address):
        return Response(status_code=204)
    email_id = event_data.get("email_id")
    if not isinstance(email_id, str):
        return Response(status_code=400)

    try:
        await run_in_threadpool(_forward_resend_received_email, email_id, settings)
    except Exception as exc:  # noqa: BLE001
        # Provider exceptions can include recipient addresses or message content.
        logger.warning("Resend inbound contact forwarding failed (%s).", type(exc).__name__)
        return Response(status_code=503)

    return Response(status_code=204)
