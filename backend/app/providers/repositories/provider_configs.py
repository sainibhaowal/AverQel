from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select, update

from app.providers.models.provider_config import ProviderConfig
from app.system.repositories.base import BaseRepository


class ProviderConfigsRepository(BaseRepository):
    def create(self, provider_config: ProviderConfig) -> ProviderConfig:
        self.apply_tenant_scope(provider_config.tenant_id)
        if not provider_config.visibility_scope:
            provider_config.visibility_scope = "user"
        if (
            provider_config.provider_type == "sentence-transformers"
            and provider_config.owner_user_id is None
        ):
            provider_config.visibility_scope = "system"
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
