from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from binascii import Error as BinasciiError
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models.oauth_identity import OAuthIdentity
from app.auth.services.auth_service import AuthService, LoginResult
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import set_db_tenant_context

OAUTH_STATE_COOKIE = "averqel_auth_oauth_state"
OAUTH_STATE_COOKIE_PREFIX = f"{OAUTH_STATE_COOKIE}_"
OAUTH_2FA_COOKIE = "averqel_auth_oauth_2fa"
OAUTH_STATE_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class OAuthProvider:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    user_url: str
    email_url: str | None
    scopes: tuple[str, ...]


class OAuthLoginService:
    def __init__(self, db: Session | None, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def _cookie_path(self) -> str:
        return f"{self.settings.api_prefix.rstrip('/')}/auth/oauth"

    @staticmethod
    def _state_cookie_name(cookie_id: str) -> str:
        return f"{OAUTH_STATE_COOKIE_PREFIX}{cookie_id}"

    def provider(self, name: str) -> OAuthProvider:
        normalized = name.strip().lower()
        if normalized == "google":
            client_id = self.settings.auth_google_oauth_client_id
            client_secret = self.settings.auth_google_oauth_client_secret
            return OAuthProvider(
                name="google",
                client_id=client_id or "",
                client_secret=client_secret or "",
                authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",  # nosec B106 - protocol endpoint, not a credential
                user_url="https://openidconnect.googleapis.com/v1/userinfo",
                email_url=None,
                scopes=("openid", "email", "profile"),
            )
        if normalized == "github":
            client_id = self.settings.auth_github_oauth_client_id
            client_secret = self.settings.auth_github_oauth_client_secret
            return OAuthProvider(
                name="github",
                client_id=client_id or "",
                client_secret=client_secret or "",
                authorize_url="https://github.com/login/oauth/authorize",
                token_url="https://github.com/login/oauth/access_token",  # nosec B106 - protocol endpoint, not a credential
                user_url="https://api.github.com/user",
                email_url="https://api.github.com/user/emails",
                scopes=("read:user", "user:email"),
            )
        raise ApiError(
            code="OAUTH_PROVIDER_UNSUPPORTED",
            message="Unsupported login provider.",
            status_code=404,
        )

    def _redirect_uri(self, provider: str) -> str:
        template = (self.settings.auth_oauth_redirect_uri or "").strip()
        if not template:
            raise ApiError(
                code="OAUTH_NOT_CONFIGURED",
                message="OAuth login callback is not configured.",
                status_code=503,
            )
        uri = template.replace("{provider}", provider).rstrip("/")
        if not uri.startswith(("https://", "http://")):
            raise ApiError(
                code="OAUTH_NOT_CONFIGURED",
                message="OAuth login callback is invalid.",
                status_code=503,
            )
        return uri

    def frontend_redirect_uri(self) -> str:
        uri = (self.settings.auth_oauth_frontend_redirect_uri or "").strip().rstrip("/")
        if not uri.startswith(("https://", "http://")):
            raise ApiError(
                code="OAUTH_NOT_CONFIGURED",
                message="OAuth login frontend redirect is invalid.",
                status_code=503,
            )
        return uri

    @staticmethod
    def _pkce_verifier() -> str:
        return secrets.token_urlsafe(64)

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _sign_state(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        signature = hmac.new(
            self.settings.refresh_token_hash_secret.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        signed = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{encoded}.{signed}"

    def _verify_state(self, token: str, provider: str) -> dict[str, Any]:
        try:
            encoded, signed = token.split(".", maxsplit=1)
            expected = hmac.new(
                self.settings.refresh_token_hash_secret.encode("utf-8"),
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
            actual = base64.urlsafe_b64decode(signed + "=" * (-len(signed) % 4))
            if not hmac.compare_digest(expected, actual):
                raise ValueError("signature")
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if not isinstance(payload, dict) or payload.get("provider") != provider:
                raise ValueError("provider")
            if int(payload.get("expires_at") or 0) < int(time.time()):
                raise ValueError("expired")
            if not isinstance(payload.get("state"), str) or not isinstance(
                payload.get("verifier"), str
            ):
                raise ValueError("payload")
            return payload
        except (
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            BinasciiError,
        ) as exc:
            raise ApiError(
                code="OAUTH_STATE_INVALID",
                message="OAuth login state is invalid or expired.",
                status_code=400,
            ) from exc

    def start(self, *, provider_name: str, response: Response, return_to: str | None = None) -> str:
        provider = self.provider(provider_name)
        if not provider.client_id or not provider.client_secret:
            raise ApiError(
                code="OAUTH_NOT_CONFIGURED",
                message=f"{provider.name.title()} login is not configured.",
                status_code=503,
            )
        safe_return_to = (
            "/auth/login"
            if not return_to or not return_to.startswith("/") or return_to.startswith("//")
            else return_to
        )
        verifier = self._pkce_verifier()
        state_value = secrets.token_urlsafe(32)
        cookie_id = secrets.token_urlsafe(18)
        state = self._sign_state(
            {
                "provider": provider.name,
                "state": state_value,
                "verifier": verifier,
                "cookie_id": cookie_id,
                "return_to": safe_return_to,
                "expires_at": int(time.time()) + OAUTH_STATE_TTL_SECONDS,
            }
        )
        response.set_cookie(
            self._state_cookie_name(cookie_id),
            state,
            max_age=OAUTH_STATE_TTL_SECONDS,
            httponly=True,
            secure=self.settings.refresh_cookie_secure,
            samesite="lax",
            path=self._cookie_path(),
        )
        params = {
            "client_id": provider.client_id,
            "redirect_uri": self._redirect_uri(provider.name),
            "response_type": "code",
            "scope": " ".join(provider.scopes),
            "state": state_value,
            "code_challenge": self._pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        if provider.name == "google":
            params.update({"access_type": "online", "prompt": "select_account"})
        else:
            params["allow_signup"] = "true"
        return f"{provider.authorize_url}?{urlencode(params)}"

    def _exchange_code(self, provider: OAuthProvider, code: str, verifier: str) -> str:
        try:
            response = httpx.post(
                provider.token_url,
                data={
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret,
                    "code": code,
                    "redirect_uri": self._redirect_uri(provider.name),
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AverQel-Auth/1.0",
                },
                timeout=10.0,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise ApiError(
                code="OAUTH_TOKEN_EXCHANGE_FAILED",
                message="The OAuth provider could not be reached.",
                status_code=502,
            ) from exc
        if response.status_code >= 400:
            raise ApiError(
                code="OAUTH_TOKEN_EXCHANGE_FAILED",
                message="OAuth provider rejected the login.",
                status_code=401,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                code="OAUTH_TOKEN_EXCHANGE_FAILED",
                message="OAuth provider returned an invalid response.",
                status_code=502,
            ) from exc
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise ApiError(
                code="OAUTH_TOKEN_EXCHANGE_FAILED",
                message="OAuth provider did not return an access token.",
                status_code=401,
            )
        return access_token

    def _fetch_identity(
        self, provider: OAuthProvider, access_token: str
    ) -> tuple[str, str, str | None]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "AverQel-Auth/1.0",
        }
        try:
            response = httpx.get(
                provider.user_url, headers=headers, timeout=10.0, follow_redirects=False
            )
        except httpx.HTTPError as exc:
            raise ApiError(
                code="OAUTH_PROFILE_FAILED",
                message="The OAuth provider could not be reached.",
                status_code=502,
            ) from exc
        if response.status_code >= 400:
            raise ApiError(
                code="OAUTH_PROFILE_FAILED",
                message="Could not verify the OAuth account.",
                status_code=401,
            )
        try:
            profile = response.json()
        except ValueError as exc:
            raise ApiError(
                code="OAUTH_PROFILE_FAILED",
                message="OAuth profile was invalid.",
                status_code=401,
            ) from exc
        if not isinstance(profile, dict):
            raise ApiError(
                code="OAUTH_PROFILE_FAILED",
                message="OAuth profile was invalid.",
                status_code=401,
            )
        if provider.name == "google":
            subject = str(profile.get("sub") or "").strip()
            email = str(profile.get("email") or "").strip().lower()
            if not subject or not email or profile.get("email_verified") is not True:
                raise ApiError(
                    code="OAUTH_EMAIL_UNVERIFIED",
                    message="A verified email is required for login.",
                    status_code=403,
                )
            avatar = profile.get("picture") if isinstance(profile.get("picture"), str) else None
            return subject, email, avatar

        subject = str(profile.get("id") or "").strip()
        if not subject:
            raise ApiError(
                code="OAUTH_PROFILE_FAILED",
                message="GitHub account identity was invalid.",
                status_code=401,
            )
        try:
            emails_response = httpx.get(
                provider.email_url or "https://api.github.com/user/emails",
                headers=headers,
                timeout=10.0,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise ApiError(
                code="OAUTH_EMAIL_UNVERIFIED",
                message="The OAuth provider email could not be verified.",
                status_code=502,
            ) from exc
        if emails_response.status_code >= 400:
            raise ApiError(
                code="OAUTH_EMAIL_UNVERIFIED",
                message="GitHub did not return a verified email.",
                status_code=403,
            )
        try:
            emails = emails_response.json()
        except ValueError as exc:
            raise ApiError(
                code="OAUTH_EMAIL_UNVERIFIED",
                message="GitHub did not return a valid email response.",
                status_code=403,
            ) from exc
        verified = (
            next(
                (
                    item
                    for item in emails
                    if isinstance(item, dict)
                    and item.get("verified") is True
                    and item.get("primary") is True
                ),
                None,
            )
            if isinstance(emails, list)
            else None
        )
        if not isinstance(verified, dict):
            verified = (
                next(
                    (
                        item
                        for item in emails
                        if isinstance(item, dict) and item.get("verified") is True
                    ),
                    None,
                )
                if isinstance(emails, list)
                else None
            )
        email = (
            str(verified.get("email") or "").strip().lower() if isinstance(verified, dict) else ""
        )
        if not email:
            raise ApiError(
                code="OAUTH_EMAIL_UNVERIFIED",
                message="A verified GitHub email is required for login.",
                status_code=403,
            )
        avatar = profile.get("avatar_url") if isinstance(profile.get("avatar_url"), str) else None
        return subject, email, avatar

    def authenticate_callback(
        self,
        *,
        provider_name: str,
        code: str,
        state: str,
        state_cookie: str | None = None,
        state_cookies: list[str] | None = None,
    ) -> LoginResult:
        if self.db is None:
            raise ApiError(
                code="OAUTH_CALLBACK_INVALID",
                message="OAuth login callback is unavailable.",
                status_code=500,
            )
        provider = self.provider(provider_name)
        if (not state_cookie and not state_cookies) or not code or not state:
            raise ApiError(
                code="OAUTH_CALLBACK_INVALID",
                message="OAuth callback is incomplete.",
                status_code=400,
            )
        candidates = state_cookies or ([state_cookie] if state_cookie else [])
        payload: dict[str, Any] | None = None
        for candidate in candidates:
            try:
                candidate_payload = self._verify_state(candidate, provider.name)
            except ApiError:
                continue
            if hmac.compare_digest(str(candidate_payload["state"]), state):
                payload = candidate_payload
                break
        if payload is None:
            raise ApiError(
                code="OAUTH_STATE_INVALID",
                message="OAuth login state does not match.",
                status_code=400,
            )
        access_token = self._exchange_code(provider, code, str(payload["verifier"]))
        subject, email, avatar = self._fetch_identity(provider, access_token)
        set_db_tenant_context(self.db, "bypass")
        identity = self.db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider.name,
                OAuthIdentity.subject == subject,
            )
        ).scalar_one_or_none()
        auth = AuthService(self.db, self.settings)
        if identity is not None:
            user = auth.users.get_by_id_global(identity.user_id)
            if user is None or user.tenant_id != identity.tenant_id:
                raise ApiError(
                    code="OAUTH_IDENTITY_INVALID",
                    message="OAuth identity is not linked to an active account.",
                    status_code=401,
                )
            identity.email = email
            identity.avatar_url = avatar
        else:
            user = auth.users.get_by_email_global(email)
            if user is None:
                user = auth.register(email=email, password=secrets.token_urlsafe(48))
            # ``auth.register`` commits a new-user transaction.  Tenant context is
            # transaction-local, so restore the authentication bypass before
            # inserting the OAuth identity in the new transaction.
            set_db_tenant_context(self.db, "bypass")
            identity = OAuthIdentity(
                id=generate_uuid7_with_fallback(),
                tenant_id=user.tenant_id,
                user_id=user.id,
                provider=provider.name,
                subject=subject,
                email=email,
                avatar_url=avatar,
            )
            self.db.add(identity)
            self.db.flush()
        return auth.complete_external_login(user=user)
