from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.providers.models.provider_usage_record import ProviderUsageRecord
from app.repositories.system.base import BaseRepository


class ProviderUsageRecordsRepository(BaseRepository):
    def create(self, row: ProviderUsageRecord) -> ProviderUsageRecord:
        self.apply_tenant_scope(row.tenant_id)
        self.db.add(row)
        self.db.flush()
        return row

    def list_by_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        limit: int = 100,
    ) -> Sequence[ProviderUsageRecord]:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            select(ProviderUsageRecord)
            .where(
                ProviderUsageRecord.tenant_id == tenant_id,
                ProviderUsageRecord.provider_config_id == provider_config_id,
            )
            .order_by(ProviderUsageRecord.created_at.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()
