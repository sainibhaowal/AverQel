from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.providers.provider_model_cache import ProviderModelCache
from app.repositories.system.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class ProviderModelCacheRepository(BaseRepository):
    def upsert_models(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        models: Sequence[ProviderModelCache],
    ) -> list[ProviderModelCache]:
        self.apply_tenant_scope(tenant_id)
        persisted: list[ProviderModelCache] = []
        for model in models:
            stmt = select(ProviderModelCache).where(
                ProviderModelCache.tenant_id == tenant_id,
                ProviderModelCache.provider_config_id == provider_config_id,
                ProviderModelCache.model_name == model.model_name,
                ProviderModelCache.model_kind == model.model_kind,
            )
            existing = self.db.execute(stmt).scalar_one_or_none()
            if existing is None:
                self.db.add(model)
                persisted.append(model)
                continue
            existing.display_name = model.display_name
            existing.context_window = model.context_window
            existing.capabilities_json = dict(model.capabilities_json)
            existing.is_available = model.is_available
            existing.last_seen_at = datetime.now(tz=UTC)
            persisted.append(existing)
        self.db.flush()
        return persisted

    def get_model(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        model_name: str,
        model_kind: str,
    ) -> ProviderModelCache | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderModelCache).where(
            ProviderModelCache.tenant_id == tenant_id,
            ProviderModelCache.provider_config_id == provider_config_id,
            ProviderModelCache.model_name == model_name,
            ProviderModelCache.model_kind == model_kind,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_models(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        model_kind: str | None = None,
    ) -> Sequence[ProviderModelCache]:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderModelCache).where(
            ProviderModelCache.tenant_id == tenant_id,
            ProviderModelCache.provider_config_id == provider_config_id,
        )
        if model_kind is not None:
            stmt = stmt.where(ProviderModelCache.model_kind == model_kind)
        stmt = stmt.order_by(ProviderModelCache.model_name.asc())
        return self.db.execute(stmt).scalars().all()

    def purge_stale_models(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        seen_names: set[tuple[str, str]],
    ) -> int:
        self.apply_tenant_scope(tenant_id)
        rows = self.list_models(
            tenant_id=tenant_id, provider_config_id=provider_config_id
        )
        removed = 0
        for row in rows:
            if (row.model_name, row.model_kind) in seen_names:
                continue
            self.db.delete(row)
            removed += 1
        if removed:
            self.db.flush()
        return removed
