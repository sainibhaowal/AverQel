from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.documents.models.data_deletion import DataDeletion
from app.repositories.system.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class DataDeletionsRepository(BaseRepository):
    def create(self, *, row: DataDeletion) -> DataDeletion:
        self.apply_tenant_scope(row.tenant_id)
        self.db.add(row)
        self.db.flush()
        return row

    def get_by_id(
        self, *, tenant_id: uuid.UUID, deletion_id: uuid.UUID
    ) -> DataDeletion | None:
        self.apply_tenant_scope(tenant_id)
        statement = select(DataDeletion).where(
            DataDeletion.tenant_id == tenant_id,
            DataDeletion.id == deletion_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_next_queued(self, *, tenant_id: uuid.UUID) -> DataDeletion | None:
        self.apply_tenant_scope(tenant_id)
        statement = (
            select(DataDeletion)
            .where(
                DataDeletion.tenant_id == tenant_id,
                DataDeletion.status == "queued",
            )
            .order_by(DataDeletion.requested_at.asc(), DataDeletion.id.asc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_by_tenant(
        self, *, tenant_id: uuid.UUID, limit: int = 20
    ) -> list[DataDeletion]:
        self.apply_tenant_scope(tenant_id)
        safe_limit = max(1, min(limit, 100))
        statement = (
            select(DataDeletion)
            .where(DataDeletion.tenant_id == tenant_id)
            .order_by(DataDeletion.requested_at.desc(), DataDeletion.id.desc())
            .limit(safe_limit)
        )
        return list(self.db.execute(statement).scalars().all())

    def mark_processing(self, *, tenant_id: uuid.UUID, row: DataDeletion) -> None:
        self.apply_tenant_scope(tenant_id)
        row.status = "processing"
        row.started_at = datetime.now(tz=UTC)
        row.completed_at = None
        row.failed_at = None
        row.error_code = None
        row.error_message = None

    def mark_completed(
        self,
        *,
        tenant_id: uuid.UUID,
        row: DataDeletion,
        result_counts: dict[str, int],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        row.status = "completed"
        row.completed_at = datetime.now(tz=UTC)
        row.failed_at = None
        row.result_counts = result_counts
        row.error_code = None
        row.error_message = None

    def mark_failed(
        self,
        *,
        tenant_id: uuid.UUID,
        row: DataDeletion,
        error_code: str,
        error_message: str,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        row.status = "failed"
        row.completed_at = None
        row.failed_at = datetime.now(tz=UTC)
        row.error_code = error_code
        row.error_message = error_message
