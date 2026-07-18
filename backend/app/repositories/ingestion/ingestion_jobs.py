from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.ingestion.ingestion_job import IngestionJob
from app.repositories.system.base import BaseRepository

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class IngestionJobsRepository(BaseRepository):
    def create(self, job: IngestionJob) -> IngestionJob:
        self.apply_tenant_scope(job.tenant_id)
        self.db.add(job)
        self.db.flush()
        return job

    def get_by_id(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> IngestionJob | None:
        self.apply_tenant_scope(tenant_id)
        query = select(IngestionJob).where(
            IngestionJob.tenant_id == tenant_id,
            IngestionJob.id == job_id,
        )
        return self.db.execute(query).scalar_one_or_none()

    def get_by_document_id(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> IngestionJob | None:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.document_id == document_id,
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(1)
        )
        return self.db.execute(query).scalar_one_or_none()

    def list_by_document_id(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[IngestionJob]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.document_id == document_id,
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
        )
        return list(self.db.execute(query).scalars().all())

    def set_status(
        self,
        *,
        tenant_id: uuid.UUID,
        job: IngestionJob,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        dead_letter_reason: str | None = None,
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        job.status = status
        job.last_error_code = error_code
        job.last_error_message = error_message
        job.updated_at = datetime.now(tz=UTC)

        if status == "dead_lettered":
            job.dead_lettered_at = datetime.now(tz=UTC)
            job.dead_letter_reason = (
                dead_letter_reason or error_code or "unknown_failure"
            )
        elif dead_letter_reason:
            job.dead_letter_reason = dead_letter_reason

    def increment_attempt(self, *, tenant_id: uuid.UUID, job: IngestionJob) -> None:
        self.apply_tenant_scope(tenant_id)
        job.attempt_count += 1
        job.updated_at = datetime.now(tz=UTC)

    def count_active_by_tenant(self, *, tenant_id: uuid.UUID) -> int:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(func.count())
            .select_from(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.status.in_(
                    ["queued", "downloading", "parsing", "chunking", "embedding"]
                ),
            )
        )
        return self.db.execute(query).scalar() or 0

    def get_by_document_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, IngestionJob]:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return {}

        query = (
            select(IngestionJob)
            .where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.document_id.in_(document_ids),
            )
            .order_by(
                IngestionJob.document_id.asc(),
                IngestionJob.created_at.desc(),
                IngestionJob.id.desc(),
            )
        )
        rows = self.db.execute(query).scalars().all()
        result: dict[uuid.UUID, IngestionJob] = {}
        for row in rows:
            result.setdefault(row.document_id, row)
        return result
