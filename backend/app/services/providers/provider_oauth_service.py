from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import urlencode
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.repositories.providers.provider_configs import ProviderConfigsRepository
from app.services.security.provider_secret_service import ProviderSecretService
from app.services.system.audit_service import AuditService

OPENAI_OAUTH_PROVIDER_TYPE = "openai"
STATE_MAX_AGE_SECONDS = 600


@dataclass(slots=True)
class ProviderOAuthService:
    db: Session
    settings: Settings
    configs: ProviderConfigsRepository = field(init=False)
    secrets: ProviderSecretService = field(init=False)
    audit: AuditService = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit", AuditService(self.db))
        object.__setattr__(self, "configs", ProviderConfigsRepository(self.db))
        object.__setattr__(self, "secrets", ProviderSecretService(self.db))

    def status(self, *, tenant_id: UUID) -> tuple[bool, str]:
        enabled = bool(
            self.settings.provider_openai_oauth_enabled
            and self.settings.provider_openai_oauth_official_support_verified
            and self.settings.provider_openai_oauth_client_id
            and self.settings.provider_openai_oauth_redirect_uri
            and self.settings.provider_openai_oauth_allowed_redirect_uris
        )
        if not enabled:
            return (
                False,
                "OpenAI account linking is disabled until officially verified and configured.",
            )
        redirect_uri_value = self.settings.provider_openai_oauth_redirect_uri
        allowed_redirects = self.settings.provider_openai_oauth_allowed_redirect_uris
        if redirect_uri_value is None or allowed_redirects is None:
            return (
                False,
                "OpenAI account linking is disabled until officially verified and configured.",
            )
        redirect_uri = redirect_uri_value.rstrip("/")
        allowlisted = {item.rstrip("/") for item in allowed_redirects}
        if redirect_uri not in allowlisted:
            return (
                False,
                "OpenAI account linking is disabled until the redirect URI is allowlisted.",
            )
        return True, "OpenAI account linking is configured."

    def connected(self, *, tenant_id: UUID) -> bool:
        for provider in self.configs.list_by_tenant(tenant_id=tenant_id):
            if provider.provider_type != "openai" or provider.auth_mode != "oauth_pkce":
                continue
            for secret_type in ("oauth_access_token", "session_token"):
                masked = self.secrets.get_masked_secret(
                    tenant_id=tenant_id,
                    provider_config_id=provider.id,
                    secret_type=secret_type,
                )
                if masked is not None:
                    return True
        return False

    def start(
        self, *, tenant_id: UUID, actor_user_id: UUID | None
    ) -> tuple[bool, str | None, str]:
        enabled, message = self.status(tenant_id=tenant_id)
        if not enabled:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message=message,
                status_code=400,
            )
        nonce = str(uuid4())
        state = self._sign_state(
            tenant_id=tenant_id, actor_user_id=actor_user_id, nonce=nonce
        )
        params = urlencode(
            {
                "client_id": self.settings.provider_openai_oauth_client_id,
                "redirect_uri": self.settings.provider_openai_oauth_redirect_uri,
                "response_type": "code",
                "scope": "openid profile",
                "state": state,
                "nonce": nonce,
            }
        )
        url = f"{self.settings.provider_openai_oauth_authorize_url}?{params}"
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.oauth.start",
            resource_type="provider_oauth",
            details={"provider_type": "openai"},
        )
        return True, url, "OpenAI OAuth flow initialized."

    def callback(
        self,
        *,
        tenant_id: UUID,
        actor_user_id: UUID | None,
        code: str | None,
        state: str | None,
    ) -> tuple[bool, str]:
        enabled, message = self.status(tenant_id=tenant_id)
        if not enabled:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message=message,
                status_code=400,
            )
        if not code or not state:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback is incomplete.",
                status_code=400,
            )
        self._verify_state(tenant_id=tenant_id, state=state)
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.oauth.callback",
            resource_type="provider_oauth",
            details={"provider_type": "openai"},
        )
        return (
            False,
            "OpenAI OAuth callback flow is reserved for officially verified client support only.",
        )

    def _sign_state(
        self, *, tenant_id: UUID, actor_user_id: UUID | None, nonce: str
    ) -> str:
        payload = {
            "tenant_id": str(tenant_id),
            "actor_user_id": str(actor_user_id) if actor_user_id is not None else "",
            "nonce": nonce,
            "iat": int(time.time()),
            "provider_type": OPENAI_OAUTH_PROVIDER_TYPE,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        signature = hmac.new(
            self.settings.jwt_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        return (
            base64.urlsafe_b64encode(body).decode("utf-8").rstrip("=")
            + "."
            + base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
        )

    def _verify_state(self, *, tenant_id: UUID, state: str) -> dict[str, str | int]:
        try:
            encoded_body, encoded_sig = state.split(".", 1)
        except ValueError as exc:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback state is invalid.",
                status_code=400,
            ) from exc

        body = self._decode_base64url(encoded_body)
        expected_sig = hmac.new(
            self.settings.jwt_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        actual_sig = self._decode_base64url(encoded_sig)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback state failed verification.",
                status_code=400,
            )

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback state is malformed.",
                status_code=400,
            ) from exc

        if payload.get("provider_type") != OPENAI_OAUTH_PROVIDER_TYPE:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback state is invalid for this provider.",
                status_code=400,
            )
        if payload.get("tenant_id") != str(tenant_id):
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback tenant mismatch.",
                status_code=400,
            )
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback nonce is invalid.",
                status_code=400,
            )
        issued_at = payload.get("iat")
        if (
            not isinstance(issued_at, int)
            or int(time.time()) - issued_at > STATE_MAX_AGE_SECONDS
        ):
            raise ApiError(
                code="PROVIDER_OAUTH_UNSUPPORTED",
                message="OAuth callback state has expired.",
                status_code=400,
            )
        return cast(dict[str, str | int], payload)

    @staticmethod
    def _decode_base64url(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("utf-8"))
