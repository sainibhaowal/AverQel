from __future__ import annotations

from collections.abc import Callable

from pytest import MonkeyPatch
from sqlalchemy import text

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.ingestion.models.ingestion_job import IngestionJob
from app.ingestion.services.embedding_service import EmbeddingService
from app.ingestion.services.ingestion_service import (
    IngestionService,
    RetryableIngestionError,
)
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.system.services.storage_service import StorageService
from tests.conftest import SeededUser


def test_retry_and_dead_letter_path_for_retryable_failures(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-retry-path",
        "editor-retry@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )

    document_id = generate_uuid7_with_fallback()
    job_id = generate_uuid7_with_fallback()

    setup = get_session_factory()()
    try:
        setup.add(
            Document(
                id=document_id,
                tenant_id=seeded.tenant_id,
                uploaded_by_user_id=seeded.user_id,
                filename="retry.txt",
                content_type="text/plain",
                size_bytes=64,
                sha256_hash="f" * 64,
                storage_bucket="aks-documents",
                storage_object_key=f"{seeded.tenant_id}/{document_id}/retry.txt",
                status="queued",
            )
        )
        setup.add(
            IngestionJob(
                id=job_id,
                tenant_id=seeded.tenant_id,
                document_id=document_id,
                status="queued",
                attempt_count=0,
                max_attempts=settings.ingestion_max_attempts,
            )
        )
        setup.commit()
    finally:
        setup.close()

    monkeypatch.setattr(
        StorageService,
        "get_bytes",
        lambda self, *, bucket, object_key: b"text that forces embedding retry",
    )

    def always_retryable(self: EmbeddingService, texts: list[str]) -> list[list[float]]:
        del texts
        raise ApiError(
            code="EMBEDDING_PROVIDER_UNAVAILABLE",
            message="provider timeout",
            status_code=503,
        )

    monkeypatch.setattr(EmbeddingService, "embed_many", always_retryable)

    worker = get_session_factory()()
    try:
        worker.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(worker, seeded.tenant_id)
        service = IngestionService(db=worker, settings=settings)

        for _ in range(settings.ingestion_max_attempts - 1):
            try:
                service.process_ingestion_job(tenant_id=seeded.tenant_id, job_id=job_id)
                raise AssertionError("expected retryable ingestion error")
            except RetryableIngestionError:
                pass

        service.process_ingestion_job(tenant_id=seeded.tenant_id, job_id=job_id)

        final_job = service.jobs.get_by_id(tenant_id=seeded.tenant_id, job_id=job_id)
        assert final_job is not None
        assert final_job.status == "dead_lettered"
        assert final_job.attempt_count == settings.ingestion_max_attempts
        assert final_job.last_error_code == "EMBEDDING_PROVIDER_UNAVAILABLE"

        final_doc = service.documents.get_by_id(
            tenant_id=seeded.tenant_id, document_id=document_id
        )
        assert final_doc is not None
        assert final_doc.status == "dead_lettered"
    finally:
        worker.execute(text("RESET ROLE"))
        worker.close()
