from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import cast

from celery import Task  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.engine import CursorResult

from app.core.config import get_settings
from app.platform.database.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.documents.services.deletion_service import DeletionService
from app.system.services.audit_service import AuditService
from app.system.services.metrics_service import MAINTENANCE_JOB_EVENTS_TOTAL
from app.platform.worker.celery_app import celery_app  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@celery_app.task(name="maintenance.heartbeat")  # type: ignore[misc]
def maintenance_heartbeat() -> str:
    MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="heartbeat", status="ok").inc()
    return "ok"


@celery_app.task(name="maintenance.retention_cleanup")  # type: ignore[misc]
def retention_cleanup() -> dict[str, int]:
    start = time.perf_counter()
    settings = get_settings()
    session = get_session_factory()()
    cleaned_audit_total = 0
    cleaned_transient_total = 0

    try:
        session.execute(text("SET ROLE aks_app"))

        tenant_rows = session.query(Tenant.id).all()
        tenant_ids: list[uuid.UUID] = []
        for row in tenant_rows:
            if hasattr(row, "id"):
                tenant_ids.append(cast(uuid.UUID, row.id))
            elif hasattr(row, "__getitem__"):
                tenant_ids.append(cast(uuid.UUID, row[0]))
            else:
                tenant_ids.append(cast(uuid.UUID, row))
        transient_cutoff = datetime.now(tz=UTC) - timedelta(
            days=settings.transient_record_retention_days
        )

        for tenant_id in tenant_ids:
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )

            cleaned = AuditService(session).purge_old_events(
                tenant_id=tenant_id,
                retention_days=settings.audit_log_retention_days,
            )
            cleaned_audit_total += cleaned

            idempotency_result = session.execute(
                text("""
                    DELETE FROM idempotency_keys
                    WHERE tenant_id = :tenant_id
                      AND created_at < :cutoff
                    """),
                {"tenant_id": str(tenant_id), "cutoff": transient_cutoff},
            )
            deletion_result = session.execute(
                text("""
                    DELETE FROM data_deletions
                    WHERE tenant_id = :tenant_id
                      AND requested_at < :cutoff
                      AND status IN ('completed', 'failed')
                    """),
                {"tenant_id": str(tenant_id), "cutoff": transient_cutoff},
            )

            idempotency_deleted = (
                int(idempotency_result.rowcount or 0)
                if isinstance(idempotency_result, CursorResult)
                else 0
            )
            deletions_deleted = (
                int(deletion_result.rowcount or 0)
                if isinstance(deletion_result, CursorResult)
                else 0
            )
            cleaned_transient_total += idempotency_deleted + deletions_deleted

        session.commit()
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="retention_cleanup", status="ok").inc()

        logger.info(
            "Maintenance retention cleanup completed.",
            extra={
                "audit_logs_deleted": cleaned_audit_total,
                "transient_records_deleted": cleaned_transient_total,
                "duration_seconds": round(time.perf_counter() - start, 4),
            },
        )

        return {
            "audit_logs_deleted": cleaned_audit_total,
            "transient_records_deleted": cleaned_transient_total,
        }

    except Exception:  # noqa: BLE001
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(
            job="retention_cleanup", status="error"
        ).inc()
        logger.exception("Maintenance retention cleanup failed.")
        raise

    finally:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Maintenance rollback cleanup failed.", exc_info=True)

        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Maintenance rollback after role reset failed.", exc_info=True
                )

        session.close()


@celery_app.task(bind=True, name="maintenance.process_data_deletion")  # type: ignore[misc]
def process_data_deletion(self: Task, deletion_id: str, tenant_id: str) -> str:
    del self
    settings = get_settings()
    session = get_session_factory()()

    try:
        session.execute(text("SET ROLE aks_app"))
        service = DeletionService(session, settings)
        service.process_deletion(
            deletion_id=uuid.UUID(deletion_id),
            tenant_id=uuid.UUID(tenant_id),
        )
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(
            job="process_data_deletion", status="ok"
        ).inc()
        return "ok"

    except Exception:  # noqa: BLE001
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(
            job="process_data_deletion", status="error"
        ).inc()
        logger.exception(
            "Maintenance data deletion task failed.",
            extra={
                "deletion_id": deletion_id,
                "tenant_id": tenant_id,
            },
        )
        raise

    finally:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Maintenance deletion rollback cleanup failed.", exc_info=True)

        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Maintenance deletion rollback after role reset failed.",
                    exc_info=True,
                )

        session.close()
