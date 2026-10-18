from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import ssl
import time
from base64 import b64encode
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import ApiError
from app.system.api import contact as contact_api
from app.system.api.contact import (
    _contact_delivery_configured,
    _contact_inbound_configured,
    _contact_verification_configured,
    _contact_verification_html,
    _forward_resend_received_email,
    _issue_contact_verification,
    _send_contact_email,
    _send_contact_verification_email,
    _verify_contact_code,
    _verify_resend_signature,
    confirm_contact_email_verification,
    receive_resend_inbound_email,
    request_contact_email_verification,
    submit_public_contact,
)
from app.system.schemas.public_contact import PublicContactCreate
from app.system.services import smtp_client
from app.system.workers import tasks_notifications

pytestmark = pytest.mark.unit_no_db


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "notification_smtp_host": "smtp.resend.com",
        "notification_smtp_port": 465,
        "notification_smtp_username": "resend",
        "notification_smtp_password": "test-token",
        "notification_smtp_from": "AverQel <contact@averqel.com>",
        "notification_smtp_starttls": False,
        "notification_smtp_implicit_tls": True,
        "public_contact_recipient": "private@example.net",
        "public_contact_from": "AverQel <contact@averqel.com>",
        "public_contact_verification_from": "AverQel Verification <verify@averqel.com>",
        "jwt_secret": "local-test-jwt-secret-that-is-long-enough-123456",
        "redis_url": "redis://unused",
        "rate_limit_public_contact_verification_ip_per_hour": 10,
        "rate_limit_public_contact_verification_email_per_hour": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "production",
        "jwt_secret": "j" * 48,
        "refresh_token_hash_secret": "r" * 48,
        "database_url": "postgresql+psycopg://app:secret@db.example/averqel",
        "minio_access_key": "averqel-storage",
        "minio_secret_key": "m" * 40,
        "refresh_cookie_secure": True,
        "connector_oauth_redirect_uri": "https://averqel.com/api/v1/connectors/oauth/callback",
        "connector_oauth_frontend_redirect_uri": "https://averqel.com/settings/connections",
        "averqel_public_origin": "https://averqel.com",
        "malware_scan_enabled": True,
        "malware_scan_required": True,
        "provider_secret_active_kid": "test-kid",
        "provider_secret_keyring_json": '{"test-kid":"AAAAAAAAAAAAAAAAAAAAAA=="}',
        "notification_smtp_host": "smtp.resend.com",
        "notification_smtp_from": "contact@averqel.com",
        "notification_smtp_username": "resend",
        "notification_smtp_password": "test-token",
        "notification_smtp_starttls": False,
        "notification_smtp_implicit_tls": True,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


def _inbound_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "public_contact_address": "contact@averqel.com",
        "public_contact_resend_api_key": "test-resend-api-key",
        "public_contact_resend_webhook_secret": "whsec-correctly-configured-test-secret",
        "public_contact_recipient": "private@example.net",
        "public_contact_from": "AverQel <contact@averqel.com>",
        "notification_smtp_from": "AverQel <contact@averqel.com>",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _signed_webhook(body: bytes, *, secret: bytes = b"test-signing-key") -> dict[str, str]:
    webhook_id = "evt_test_123"
    timestamp = str(int(time.time()))
    signing_input = f"{webhook_id}.{timestamp}.".encode() + body
    signature = b64encode(hmac.new(secret, signing_input, hashlib.sha256).digest()).decode("ascii")
    return {
        "svix-id": webhook_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
    }


def _webhook_request(body: bytes, headers: dict[str, str]) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/contact/resend-inbound",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "query_string": b"",
    }
    return Request(scope, receive)


def _json_request(path: str, payload: dict[str, object]) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
        "query_string": b"",
        "client": ("203.0.113.10", 12345),
    }
    return Request(scope, receive)


class _FakeContactRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        item = self.values.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at <= time.time():
            self.values.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, *, ex: int, nx: bool = False) -> bool:
        if nx and self.get(key) is not None:
            return False
        self.values[key] = (value, time.time() + ex)
        return True

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(self.values.pop(key, None) is not None)
        return removed

    def eval(self, script: str, numkeys: int, *args: object) -> int:
        if script == contact_api._VERIFY_CONTACT_OTP_SCRIPT:
            challenge_key, token_key = str(args[0]), str(args[1])
            email_hash, code_hash = str(args[2]), str(args[3])
            max_attempts, token_ttl = int(args[4]), int(args[5])
            raw = self.get(challenge_key)
            if raw is None:
                return 0
            challenge = json.loads(raw)
            if challenge["email_hash"] != email_hash:
                return -1
            attempts = int(challenge["attempts"]) + 1
            if attempts > max_attempts:
                self.delete(challenge_key)
                return -2
            if challenge["code_hash"] == code_hash:
                if not self.set(token_key, email_hash, ex=token_ttl, nx=True):
                    return -3
                self.delete(challenge_key)
                return 1
            if attempts >= max_attempts:
                self.delete(challenge_key)
                return -2
            remaining = max(int(self.values[challenge_key][1] - time.time()), 1)
            challenge["attempts"] = attempts
            self.set(challenge_key, json.dumps(challenge), ex=remaining)
            return 0
        if script == contact_api._CONSUME_CONTACT_VERIFICATION_SCRIPT:
            token_key, email_hash = str(args[0]), str(args[1])
            stored_email_hash = self.get(token_key)
            if stored_email_hash is None:
                return 0
            if stored_email_hash != email_hash:
                return -1
            self.delete(token_key)
            return 1
        raise AssertionError("Unexpected Redis script")


def _smtp_context() -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    client.__enter__.return_value = client
    return client, client


@pytest.mark.parametrize(
    ("starttls", "implicit_tls", "expected"),
    [(True, False, True), (False, True, True), (False, False, False), (True, True, False)],
)
def test_contact_delivery_requires_one_encrypted_transport(
    starttls: bool, implicit_tls: bool, expected: bool
) -> None:
    settings = _settings(
        notification_smtp_starttls=starttls,
        notification_smtp_implicit_tls=implicit_tls,
    )

    assert _contact_delivery_configured(settings) is expected


def test_contact_delivery_requires_smtp_authentication() -> None:
    settings = _settings(notification_smtp_password=None)

    assert _contact_delivery_configured(settings) is False
    assert _contact_delivery_configured(_settings(public_contact_from=None)) is False
    assert (
        _contact_delivery_configured(
            _settings(notification_smtp_from="notifications@another.example")
        )
        is False
    )


@pytest.mark.parametrize(
    ("starttls", "implicit_tls", "expected"),
    [(True, False, True), (False, True, True), (False, False, False), (True, True, False)],
)
def test_production_smtp_requires_exactly_one_tls_mode(
    starttls: bool, implicit_tls: bool, expected: bool
) -> None:
    settings = _production_settings(
        notification_smtp_starttls=starttls,
        notification_smtp_implicit_tls=implicit_tls,
    )

    if expected:
        settings.validate_production_hardening()
    else:
        with pytest.raises(ValueError, match="exactly one SMTP TLS mode"):
            settings.validate_production_hardening()


def test_production_rejects_partial_resend_inbound_configuration() -> None:
    settings = _production_settings(public_contact_address="contact@averqel.com")

    with pytest.raises(ValueError, match="requires the contact address, API key"):
        settings.validate_production_hardening()


def test_smtp_connection_uses_implicit_tls_without_starttls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_manager, client = _smtp_context()
    smtp_ssl = Mock(return_value=context_manager)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", smtp_ssl)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP", Mock())

    with smtp_client.smtp_connection(_settings(), timeout=12) as connection:
        assert connection is client

    smtp_ssl.assert_called_once()
    assert smtp_ssl.call_args.args == ("smtp.resend.com", 465)
    assert smtp_ssl.call_args.kwargs["timeout"] == 12
    assert isinstance(smtp_ssl.call_args.kwargs["context"], ssl.SSLContext)
    client.ehlo.assert_called_once_with()
    client.starttls.assert_not_called()


def test_smtp_connection_preserves_starttls_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    context_manager, client = _smtp_context()
    smtp = Mock(return_value=context_manager)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP", smtp)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", Mock())
    settings = _settings(
        notification_smtp_host="smtp.example.net",
        notification_smtp_port=587,
        notification_smtp_starttls=True,
        notification_smtp_implicit_tls=False,
    )

    with smtp_client.smtp_connection(settings, timeout=15):
        pass

    smtp.assert_called_once_with("smtp.example.net", 587, timeout=15)
    assert client.ehlo.call_count == 2
    client.starttls.assert_called_once()
    assert isinstance(client.starttls.call_args.kwargs["context"], ssl.SSLContext)


def test_contact_email_authenticates_and_sends_with_resend_smtps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_manager, client = _smtp_context()
    smtp_ssl = Mock(return_value=context_manager)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", smtp_ssl)
    payload = PublicContactCreate(
        name="Visitor",
        email="visitor@example.net",
        subject="Question",
        message="How does AverQel work?",
        verification_token="verified-contact-token-for-this-test-only",
    )

    _send_contact_email(payload, _settings())

    smtp_ssl.assert_called_once()
    client.login.assert_called_once_with("resend", "test-token")
    sent_message = client.send_message.call_args.args[0]
    assert sent_message["From"] == "AverQel <contact@averqel.com>"
    assert sent_message["To"] == "private@example.net"
    assert sent_message["Reply-To"] == "visitor@example.net"
    assert sent_message["Subject"] == "AverQel contact: Question"


def test_contact_verification_requires_a_sender_on_the_contact_mail_domain() -> None:
    assert _contact_verification_configured(_settings()) is True
    assert (
        _contact_verification_configured(
            _settings(public_contact_verification_from="verify@another.example")
        )
        is False
    )
    assert (
        _contact_verification_configured(_settings(public_contact_verification_from=None)) is False
    )
    assert (
        _contact_verification_configured(
            _settings(jwt_secret="change-me-please-use-env-secret-min-32-chars")
        )
        is False
    )


def test_contact_verification_email_uses_authenticated_tls_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_manager, client = _smtp_context()
    smtp_ssl = Mock(return_value=context_manager)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", smtp_ssl)

    _send_contact_verification_email(
        email="visitor@example.net",
        code="037291",
        challenge_id="A" * 32,
        settings=_settings(),
    )

    smtp_ssl.assert_called_once()
    client.login.assert_called_once_with("resend", "test-token")
    sent_message = client.send_message.call_args.args[0]
    assert sent_message["From"] == "AverQel Verification <verify@averqel.com>"
    assert sent_message["To"] == "visitor@example.net"
    assert sent_message.get_content_type() == "multipart/alternative"
    plain_body = sent_message.get_body(preferencelist=("plain",))
    html_body = sent_message.get_body(preferencelist=("html",))
    assert plain_body is not None
    assert html_body is not None
    assert "037291" in plain_body.get_content()
    assert "10 minutes" in plain_body.get_content()
    html_content = html_body.get_content()
    assert "Verify your email" in html_content
    assert "YOUR ONE-TIME CODE" in html_content
    assert "037291" in html_content
    assert 'src="cid:averqel-contact-email-logo"' in html_content
    assert "https://" not in html_content

    logo_part = next(part for part in sent_message.walk() if part.get_content_type() == "image/png")
    assert logo_part.get_content_disposition() == "inline"
    assert logo_part["Content-ID"] == "<averqel-contact-email-logo>"
    assert logo_part.get_payload(decode=True)


def test_contact_verification_html_escapes_code_content() -> None:
    html_content = _contact_verification_html("<script>alert(1)</script>")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_content
    assert "<script>alert(1)</script>" not in html_content


def test_public_contact_requires_single_use_matching_verified_email_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    fake_redis = _FakeContactRedis()
    issued_code: list[str] = []
    sent_messages: list[PublicContactCreate] = []
    monkeypatch.setattr(contact_api, "_contact_verification_redis", lambda _url: fake_redis)
    monkeypatch.setattr(
        contact_api,
        "_rate_limit_contact_verification",
        lambda *, email, **_kwargs: contact_api._contact_email_fingerprint(email, settings),
    )
    monkeypatch.setattr(
        contact_api,
        "_send_contact_verification_email",
        lambda *, code, **_kwargs: issued_code.append(code),
    )
    monkeypatch.setattr(contact_api, "_rate_limit_public_contact", lambda *_args: None)
    monkeypatch.setattr(
        contact_api,
        "_send_contact_email",
        lambda payload, _settings: sent_messages.append(payload),
    )

    request_response = asyncio.run(
        request_contact_email_verification(
            _json_request("/api/v1/contact/verification/request", {"email": "visitor@example.net"}),
            settings,
        )
    )
    assert len(issued_code) == 1
    stored_challenge = fake_redis.get(
        contact_api._contact_challenge_key(request_response.challenge_id)
    )
    assert stored_challenge is not None
    assert "visitor@example.net" not in stored_challenge
    assert issued_code[0] not in stored_challenge

    verified = asyncio.run(
        confirm_contact_email_verification(
            _json_request(
                "/api/v1/contact/verification/confirm",
                {
                    "email": "visitor@example.net",
                    "challenge_id": request_response.challenge_id,
                    "code": issued_code[0],
                },
            ),
            settings,
        )
    )
    assert verified.verified is True

    contact_payload = {
        "name": "Visitor",
        "email": "visitor@example.net",
        "subject": "Question",
        "message": "Hello AverQel",
        "verification_token": verified.verification_token,
    }
    with pytest.raises(ApiError) as wrong_email_error:
        asyncio.run(
            submit_public_contact(
                _json_request(
                    "/api/v1/contact",
                    {**contact_payload, "email": "someone-else@example.net"},
                ),
                settings,
            )
        )
    assert wrong_email_error.value.status_code == 403
    assert sent_messages == []

    accepted = asyncio.run(
        submit_public_contact(
            _json_request("/api/v1/contact", contact_payload),
            settings,
        )
    )
    assert accepted.accepted is True
    assert len(sent_messages) == 1

    with pytest.raises(ApiError) as replay_error:
        asyncio.run(
            submit_public_contact(
                _json_request("/api/v1/contact", contact_payload),
                settings,
            )
        )
    assert replay_error.value.status_code == 403
    assert len(sent_messages) == 1


def test_contact_verification_code_is_limited_to_five_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    fake_redis = _FakeContactRedis()
    issued_code: list[str] = []
    monkeypatch.setattr(contact_api, "_contact_verification_redis", lambda _url: fake_redis)
    monkeypatch.setattr(
        contact_api,
        "_rate_limit_contact_verification",
        lambda *, email, **_kwargs: contact_api._contact_email_fingerprint(email, settings),
    )
    monkeypatch.setattr(
        contact_api,
        "_send_contact_verification_email",
        lambda *, code, **_kwargs: issued_code.append(code),
    )
    challenge_id = _issue_contact_verification(
        request=_json_request(
            "/api/v1/contact/verification/request", {"email": "visitor@example.net"}
        ),
        email="visitor@example.net",
        settings=settings,
    )

    wrong_code = "000000" if issued_code[0] != "000000" else "000001"
    for _ in range(contact_api.CONTACT_OTP_MAX_ATTEMPTS):
        assert (
            _verify_contact_code(
                email="visitor@example.net",
                challenge_id=challenge_id,
                code=wrong_code,
                settings=settings,
            )
            is None
        )

    assert (
        _verify_contact_code(
            email="visitor@example.net",
            challenge_id=challenge_id,
            code=issued_code[0],
            settings=settings,
        )
        is None
    )


def test_expired_contact_verification_code_cannot_be_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    fake_redis = _FakeContactRedis()
    issued_code: list[str] = []
    monkeypatch.setattr(contact_api, "_contact_verification_redis", lambda _url: fake_redis)
    monkeypatch.setattr(
        contact_api,
        "_rate_limit_contact_verification",
        lambda *, email, **_kwargs: contact_api._contact_email_fingerprint(email, settings),
    )
    monkeypatch.setattr(
        contact_api,
        "_send_contact_verification_email",
        lambda *, code, **_kwargs: issued_code.append(code),
    )
    challenge_id = _issue_contact_verification(
        request=_json_request(
            "/api/v1/contact/verification/request", {"email": "visitor@example.net"}
        ),
        email="visitor@example.net",
        settings=settings,
    )
    challenge_key = contact_api._contact_challenge_key(challenge_id)
    stored = fake_redis.values[challenge_key]
    fake_redis.values[challenge_key] = (stored[0], time.time() - 1)

    assert (
        _verify_contact_code(
            email="visitor@example.net",
            challenge_id=challenge_id,
            code=issued_code[0],
            settings=settings,
        )
        is None
    )


def test_contact_inbound_forwarding_requires_all_resend_settings() -> None:
    assert _contact_inbound_configured(_inbound_settings()) is True
    assert (
        _contact_inbound_configured(_inbound_settings(public_contact_resend_webhook_secret=None))
        is False
    )


def test_resend_signature_verification_uses_raw_payload_and_timestamp() -> None:
    body = b'{"type":"email.received"}'
    headers = _signed_webhook(body)

    assert (
        _verify_resend_signature(
            body=body,
            webhook_id=headers["svix-id"],
            timestamp=headers["svix-timestamp"],
            signatures=headers["svix-signature"],
            secret=f"whsec_{b64encode(b'test-signing-key').decode('ascii')}",
        )
        is True
    )
    assert (
        _verify_resend_signature(
            body=body + b" ",
            webhook_id=headers["svix-id"],
            timestamp=headers["svix-timestamp"],
            signatures=headers["svix-signature"],
            secret=f"whsec_{b64encode(b'test-signing-key').decode('ascii')}",
        )
        is False
    )
    assert (
        _verify_resend_signature(
            body=body,
            webhook_id=headers["svix-id"],
            timestamp=headers["svix-timestamp"],
            signatures=headers["svix-signature"],
            secret=f"whsec_{b64encode(b'test-signing-key').decode('ascii')}",
            now=int(headers["svix-timestamp"]) + 301,
        )
        is False
    )


def test_resend_inbound_webhook_forwards_verified_contact_mail_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = (
        b'{"type":"email.received","data":{"email_id":"'
        + str(uuid4()).encode()
        + b'","to":["contact@averqel.com"]}}'
    )
    headers = _signed_webhook(body)
    forwarded: list[str] = []
    monkeypatch.setattr(
        contact_api,
        "_forward_resend_received_email",
        lambda email_id, _settings: forwarded.append(email_id),
    )

    response = asyncio.run(
        receive_resend_inbound_email(
            _webhook_request(body, headers),
            _inbound_settings(
                public_contact_resend_webhook_secret=(
                    f"whsec_{b64encode(b'test-signing-key').decode('ascii')}"
                )
            ),
        )
    )

    assert response.status_code == 204
    assert len(forwarded) == 1


def test_resend_inbound_webhook_rejects_bad_signature_without_forwarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"type":"email.received","data":{"email_id":"00000000-0000-0000-0000-000000000000"}}'
    headers = _signed_webhook(body)
    forwarded = Mock()
    monkeypatch.setattr(contact_api, "_forward_resend_received_email", forwarded)
    headers["svix-signature"] = "v1,invalid"

    response = asyncio.run(
        receive_resend_inbound_email(_webhook_request(body, headers), _inbound_settings())
    )

    assert response.status_code == 401
    forwarded.assert_not_called()


def test_resend_inbound_webhook_ignores_other_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = (
        b'{"type":"email.received","data":{"email_id":"'
        + str(uuid4()).encode()
        + b'","to":["other@averqel.com"]}}'
    )
    headers = _signed_webhook(body)
    forwarded = Mock()
    monkeypatch.setattr(contact_api, "_forward_resend_received_email", forwarded)

    response = asyncio.run(
        receive_resend_inbound_email(
            _webhook_request(body, headers),
            _inbound_settings(
                public_contact_resend_webhook_secret=(
                    f"whsec_{b64encode(b'test-signing-key').decode('ascii')}"
                )
            ),
        )
    )

    assert response.status_code == 204
    forwarded.assert_not_called()


def test_resend_inbound_forward_uses_reply_to_and_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email_id = str(uuid4())
    received_response = Mock()
    received_response.json.return_value = {
        "data": {
            "to": ["contact@averqel.com"],
            "from": "Visitor <visitor@example.net>",
            "subject": "Product question",
            "text": "Hello AverQel",
            "attachments": [],
        }
    }
    received_response.raise_for_status.return_value = None
    sent_response = Mock()
    sent_response.raise_for_status.return_value = None
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = received_response
    client.post.return_value = sent_response
    monkeypatch.setattr(contact_api.httpx, "Client", Mock(return_value=client))

    _forward_resend_received_email(email_id, _inbound_settings())

    client.get.assert_called_once_with(
        f"https://api.resend.com/emails/receiving/{email_id}",
        headers={"Authorization": "Bearer test-resend-api-key"},
    )
    request = client.post.call_args
    assert request.args == ("https://api.resend.com/emails",)
    assert request.kwargs["headers"]["Idempotency-Key"] == f"averqel-inbound-{email_id}"
    assert request.kwargs["json"]["from"] == "AverQel <contact@averqel.com>"
    assert request.kwargs["json"]["to"] == ["private@example.net"]
    assert request.kwargs["json"]["reply_to"] == "visitor@example.net"
    assert "Hello AverQel" in request.kwargs["json"]["text"]


def test_notification_email_uses_the_shared_implicit_tls_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_manager, client = _smtp_context()
    smtp_ssl = Mock(return_value=context_manager)
    monkeypatch.setattr(smtp_client.smtplib, "SMTP_SSL", smtp_ssl)
    monkeypatch.setattr(tasks_notifications, "get_settings", lambda: _settings())

    tasks_notifications._send_email(
        recipient="user@example.net",
        subject="Account notice",
        body="AverQel account notice.",
        delivery_id="delivery-1",
    )

    smtp_ssl.assert_called_once()
    client.login.assert_called_once_with("resend", "test-token")
    sent_message = client.send_message.call_args.args[0]
    assert sent_message["To"] == "user@example.net"
    assert sent_message["Subject"] == "Account notice"
