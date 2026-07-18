from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.providers.provider_secret import ProviderSecret
from app.repositories.providers.provider_secrets import ProviderSecretsRepository
from app.services.security.provider_secret_crypto import (
    ProviderSecretCrypto,
    ProviderSecretCryptoError,
)
from app.services.system.audit_service import AuditService


@dataclass(frozen=True, slots=True)
class MaskedProviderSecret:
    secret_type: str
    masked_value: str
    expires_at: datetime | None
    metadata: dict[str, object]


class ProviderSecretService:
    def __init__(
        self,
        db: Session,
        *,
        crypto: ProviderSecretCrypto | None = None,
    ) -> None:
        self.db = db
        self.repo = ProviderSecretsRepository(db)
        self.crypto = crypto or ProviderSecretCrypto()
        self.audit = AuditService(db)

    @staticmethod
    def _aad(
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
    ) -> bytes:
        return f"{tenant_id}:{provider_config_id}:{secret_type}".encode()

    @staticmethod
    def _mask_value(secret_type: str, secret_value: str) -> str:
        if secret_type in {
            "oauth_access_token",
            "oauth_refresh_token",
            "session_token",
        }:
            return "Connected via provider account"

        stripped = secret_value.strip()
        if len(stripped) <= 8:
            return "****"

        prefix = stripped[:3]
        suffix = stripped[-4:]
        return f"{prefix}...{suffix}"

    def upsert_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
        secret_value: str,
        actor_user_id: uuid.UUID | None,
        expires_at: datetime | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> ProviderSecret:
        aad = self._aad(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        encrypted = self.crypto.encrypt(secret_value, aad=aad)
        metadata = dict(metadata_json or {})
        metadata["masked_value"] = self._mask_value(secret_type, secret_value)
        metadata["has_secret"] = True

        existing = self.repo.get_by_provider_and_type(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if existing is None:
            row = ProviderSecret(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
                secret_type=secret_type,
                expires_at=expires_at,
                metadata_json=metadata,
            )
            created = self.repo.create_secret(row)
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.secret.create",
                resource_type="provider_secret",
                resource_id=str(created.id),
                details={
                    "provider_config_id": str(provider_config_id),
                    "secret_type": secret_type,
                },
            )
            return created

        self.repo.rotate_secret(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
            secret_ciphertext=encrypted.ciphertext,
            secret_nonce=encrypted.nonce,
            secret_kid=encrypted.kid,
            expires_at=expires_at,
            metadata_json=metadata,
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.secret.rotate",
            resource_type="provider_secret",
            resource_id=str(existing.id),
            details={
                "provider_config_id": str(provider_config_id),
                "secret_type": secret_type,
            },
        )
        refreshed = self.repo.get_by_provider_and_type(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if refreshed is None:  # pragma: no cover - defensive
            raise ProviderSecretCryptoError(
                "rotated provider secret could not be reloaded"
            )
        return refreshed

    def get_secret_value(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
    ) -> str | None:
        row = self.repo.get_by_provider_and_type(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if row is None:
            return None

        aad = self._aad(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        decrypted = self.crypto.decrypt(
            ciphertext=row.secret_ciphertext,
            nonce=row.secret_nonce,
            kid=row.secret_kid,
            aad=aad,
        )
        if self.crypto.settings.provider_secret_audit_reads:
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=None,
                action="provider.secret.access",
                resource_type="provider_secret",
                resource_id=str(row.id),
                details={
                    "provider_config_id": str(provider_config_id),
                    "secret_type": secret_type,
                    "backend": self.crypto.settings.provider_secret_backend,
                },
            )
        return decrypted.decode("utf-8")

    def get_masked_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
    ) -> MaskedProviderSecret | None:
        row = self.repo.get_by_provider_and_type(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if row is None:
            return None

        masked_value = str(row.metadata_json.get("masked_value") or "Connected")
        return MaskedProviderSecret(
            secret_type=row.secret_type,
            masked_value=masked_value,
            expires_at=row.expires_at,
            metadata=dict(row.metadata_json),
        )

    def revoke_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
        actor_user_id: uuid.UUID | None,
    ) -> bool:
        row = self.repo.get_by_provider_and_type(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if row is None:
            return False

        revoked = self.repo.revoke_secret(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if revoked:
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.secret.revoke",
                resource_type="provider_secret",
                resource_id=str(row.id),
                details={
                    "provider_config_id": str(provider_config_id),
                    "secret_type": secret_type,
                },
            )
        return revoked

    def disconnect_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> int:
        revoked_count = 0
        for secret_type in self.repo.list_secret_types_for_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
        ):
            if self.revoke_secret(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                secret_type=secret_type,
                actor_user_id=actor_user_id,
            ):
                revoked_count += 1

        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.oauth.disconnect",
            resource_type="provider_config",
            resource_id=str(provider_config_id),
            details={"revoked_secret_count": str(revoked_count)},
        )
        return revoked_count
