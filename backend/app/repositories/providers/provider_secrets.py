from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.models.providers.provider_secret import ProviderSecret
from app.repositories.system.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class ProviderSecretsRepository(BaseRepository):
    def create_secret(self, secret: ProviderSecret) -> ProviderSecret:
        self.apply_tenant_scope(secret.tenant_id)
        self.db.add(secret)
        self.db.flush()
        return secret

    def get_by_provider_and_type(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
    ) -> ProviderSecret | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderSecret).where(
            ProviderSecret.tenant_id == tenant_id,
            ProviderSecret.provider_config_id == provider_config_id,
            ProviderSecret.secret_type == secret_type,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_secret_types_for_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> Sequence[str]:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderSecret.secret_type).where(
            ProviderSecret.tenant_id == tenant_id,
            ProviderSecret.provider_config_id == provider_config_id,
        )
        return self.db.execute(stmt).scalars().all()

    def list_for_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> Sequence[ProviderSecret]:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderSecret).where(
            ProviderSecret.tenant_id == tenant_id,
            ProviderSecret.provider_config_id == provider_config_id,
        )
        return self.db.execute(stmt).scalars().all()

    def rotate_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
        secret_ciphertext: bytes,
        secret_nonce: bytes,
        secret_kid: str,
        expires_at: datetime | None,
        metadata_json: dict[str, object],
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            update(ProviderSecret)
            .where(
                ProviderSecret.tenant_id == tenant_id,
                ProviderSecret.provider_config_id == provider_config_id,
                ProviderSecret.secret_type == secret_type,
            )
            .values(
                secret_ciphertext=secret_ciphertext,
                secret_nonce=secret_nonce,
                secret_kid=secret_kid,
                expires_at=expires_at,
                last_rotated_at=datetime.now(tz=UTC),
                metadata_json=metadata_json,
                updated_at=datetime.now(tz=UTC),
            )
        )
        result = self.db.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]

    def revoke_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
    ) -> bool:
        current = self.get_by_provider_and_type(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            secret_type=secret_type,
        )
        if current is None:
            return False
        self.db.delete(current)
        self.db.flush()
        return True

    def revoke_all_for_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> int:
        rows = self.list_for_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
        )
        for row in rows:
            self.db.delete(row)
        if rows:
            self.db.flush()
        return len(rows)
