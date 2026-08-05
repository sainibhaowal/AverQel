from __future__ import annotations

import logging
import time
import uuid

from celery import Task  # type: ignore[import-untyped]
from sqlalchemy import text

from app.core.config import get_settings
from app.ingestion.services.ingestion_service import (
    IngestionService,
    RetryableIngestionError,
)
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app  # type: ignore[attr-defined]
from app.system.services.metrics_service import (
    WORKER_JOB_TRANSITIONS_TOTAL,
    WORKER_STAGE_DURATION_SECONDS,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="ingestion.ping")  # type: ignore[misc]
def ingestion_ping() -> str:
    return "ok"


@celery_app.task(bind=True, name="ingestion.process_job")  # type: ignore[misc]
def process_ingestion_job(self: Task, job_id: str, tenant_id: str) -> str:
    start = time.perf_counter()
    settings = get_settings()
    session = get_session_factory()()
    stage = "ingestion_task"

    try:
        session.execute(text("SET ROLE aks_app"))
        service = IngestionService(db=session, settings=settings)

        try:
            parsed_tenant_id = uuid.UUID(tenant_id)
            parsed_job_id = uuid.UUID(job_id)
            set_db_tenant_context(session, parsed_tenant_id)
            service.process_ingestion_job(
                tenant_id=parsed_tenant_id,
                job_id=parsed_job_id,
            )
        except RetryableIngestionError as exc:
            countdown = service.compute_retry_delay(current_attempt=int(self.request.retries) + 1)
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="retry").inc()
            raise self.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.ingestion_max_attempts,
            ) from exc
        except Exception:
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="error").inc()
            logger.exception(
                "Ingestion task failed.",
                extra={"job_id": job_id, "tenant_id": tenant_id},
            )
            raise

        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="success").inc()
        return "ok"

    finally:
        WORKER_STAGE_DURATION_SECONDS.labels(stage=stage).observe(time.perf_counter() - start)

        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Worker rollback cleanup failed.", exc_info=True)

        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("Worker rollback after role reset failed.", exc_info=True)

        session.close()
