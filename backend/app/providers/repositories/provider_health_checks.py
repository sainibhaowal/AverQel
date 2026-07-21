from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.providers.models.provider_health_check import ProviderHealthCheck
from app.repositories.system.base import BaseRepository


class ProviderHealthChecksRepository(BaseRepository):
    def record_check(self, row: ProviderHealthCheck) -> ProviderHealthCheck:
        self.apply_tenant_scope(row.tenant_id)
        self.db.add(row)
        self.db.flush()
        return row

    def get_latest_check(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> ProviderHealthCheck | None:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            select(ProviderHealthCheck)
            .where(
                ProviderHealthCheck.tenant_id == tenant_id,
                ProviderHealthCheck.provider_config_id == provider_config_id,
            )
            .order_by(
                ProviderHealthCheck.checked_at.desc(), ProviderHealthCheck.id.desc()
            )
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_recent_checks(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        limit: int = 20,
    ) -> Sequence[ProviderHealthCheck]:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            select(ProviderHealthCheck)
            .where(
                ProviderHealthCheck.tenant_id == tenant_id,
                ProviderHealthCheck.provider_config_id == provider_config_id,
            )
            .order_by(
                ProviderHealthCheck.checked_at.desc(), ProviderHealthCheck.id.desc()
            )
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()
