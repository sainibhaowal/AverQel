from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select, update

from app.providers.models.provider_config import ProviderConfig
from app.system.repositories.base import BaseRepository
from app.system.services.storage_quota import StorageQuotaService


class ProviderConfigsRepository(BaseRepository):
    @staticmethod
    def _metered_values(provider_config: ProviderConfig) -> tuple[object, ...]:
        return (
            provider_config.display_name,
            provider_config.provider_type,
            provider_config.auth_mode,
            provider_config.api_base_url,
            provider_config.default_chat_model,
            provider_config.default_embedding_model,
            provider_config.default_reranker_model,
        )

    def create(self, provider_config: ProviderConfig) -> ProviderConfig:
        self.apply_tenant_scope(provider_config.tenant_id)
        if not provider_config.visibility_scope:
            provider_config.visibility_scope = "user"
        if (
            provider_config.provider_type == "sentence-transformers"
            and provider_config.owner_user_id is None
        ):
            provider_config.visibility_scope = "system"
        StorageQuotaService(self.db).ensure_capacity(
            tenant_id=provider_config.tenant_id,
            user_id=provider_config.owner_user_id,
            additional_bytes=StorageQuotaService.estimate_bytes(
                *self._metered_values(provider_config)
            ),
        )
        self.db.add(provider_config)
        self.db.flush()
        return provider_config

    def get_by_id(
        self, *, tenant_id: uuid.UUID, provider_config_id: uuid.UUID
    ) -> ProviderConfig | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderConfig).where(
            ProviderConfig.tenant_id == tenant_id,
            ProviderConfig.id == provider_config_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_accessible_by_id(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> ProviderConfig | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderConfig).where(
            ProviderConfig.tenant_id == tenant_id,
            ProviderConfig.id == provider_config_id,
            or_(
                ProviderConfig.owner_user_id == owner_user_id,
                ProviderConfig.visibility_scope == "system",
            ),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_tenant(
        self, *, tenant_id: uuid.UUID, owner_user_id: uuid.UUID | None = None
    ) -> Sequence[ProviderConfig]:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            select(ProviderConfig)
            .where(ProviderConfig.tenant_id == tenant_id)
            .order_by(ProviderConfig.priority.asc(), ProviderConfig.created_at.asc())
        )
        if owner_user_id is not None:
            stmt = stmt.where(
                or_(
                    ProviderConfig.owner_user_id == owner_user_id,
                    ProviderConfig.visibility_scope == "system",
                )
            )
        else:
            stmt = stmt.where(ProviderConfig.visibility_scope == "system")
        return self.db.execute(stmt).scalars().all()

    def list_by_workspace(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None = None,
    ) -> Sequence[ProviderConfig]:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            select(ProviderConfig)
            .where(
                ProviderConfig.tenant_id == tenant_id,
                ProviderConfig.workspace_id == workspace_id,
            )
            .order_by(ProviderConfig.priority.asc(), ProviderConfig.created_at.asc())
        )
        if owner_user_id is not None:
            stmt = stmt.where(
                or_(
                    ProviderConfig.owner_user_id == owner_user_id,
                    ProviderConfig.visibility_scope == "system",
                )
            )
        else:
            stmt = stmt.where(ProviderConfig.visibility_scope == "system")
        return self.db.execute(stmt).scalars().all()

    def update_fields(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        values: dict[str, object],
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        current = self.get_by_id(tenant_id=tenant_id, provider_config_id=provider_config_id)
        if current is None:
            return False
        old_values = self._metered_values(current)
        new_values = tuple(
            values.get(name, getattr(current, name))
            for name in (
                "display_name",
                "provider_type",
                "auth_mode",
                "api_base_url",
                "default_chat_model",
                "default_embedding_model",
                "default_reranker_model",
            )
        )
        StorageQuotaService(self.db).ensure_capacity(
            tenant_id=tenant_id,
            user_id=current.owner_user_id,
            additional_bytes=StorageQuotaService.estimate_bytes(*new_values),
            replacing_bytes=StorageQuotaService.estimate_bytes(*old_values),
        )
        stmt = (
            update(ProviderConfig)
            .where(
                ProviderConfig.tenant_id == tenant_id,
                ProviderConfig.id == provider_config_id,
            )
            .values(**values)
        )
        result = self.db.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]

    def disable(self, *, tenant_id: uuid.UUID, provider_config_id: uuid.UUID) -> bool:
        return self.update_fields(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            values={"enabled": False},
        )

    def delete(self, *, tenant_id: uuid.UUID, provider_config_id: uuid.UUID) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = delete(ProviderConfig).where(
            ProviderConfig.tenant_id == tenant_id,
            ProviderConfig.id == provider_config_id,
        )
        result = self.db.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]
