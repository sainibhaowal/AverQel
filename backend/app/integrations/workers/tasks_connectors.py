from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime

from celery import Task  # type: ignore[import-untyped]
from celery.exceptions import Retry  # type: ignore[import-untyped]
from sqlalchemy import select, text

from app.core.config import get_settings
from app.platform.database.session import get_session_factory
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.integration import Integration
from app.integrations.services.connector_orchestrator import ConnectorOrchestrator
from app.system.services.metrics_service import (
    WORKER_JOB_TRANSITIONS_TOTAL,
    WORKER_LOCK_CONTENTION_TOTAL,
    WORKER_RETRIES_TOTAL,
    WORKER_STAGE_DURATION_SECONDS,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

CONNECTOR_SYNC_STAGE = "connector_sync"


def _compute_retry_delay(*, current_attempt: int) -> int:
    base_delay_seconds = 30
    max_delay_seconds = 15 * 60
    attempt = max(1, int(current_attempt))
    return min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))


def _checkpoint_retry_state(
    connector: Connector,
) -> tuple[bool, str | None, str | None, str | None]:
    config = connector.config if isinstance(connector.config, dict) else {}
    checkpoint = config.get(Connector.SYNC_CHECKPOINT_CONFIG_KEY)
    if not isinstance(checkpoint, dict):
        return False, None, None, None
    return (
        bool(checkpoint.get("retryable")),
        str(checkpoint.get("error_code") or "") or None,
        str(checkpoint.get("status") or "") or None,
        str(checkpoint.get("retry_after_at") or "") or None,
    )


def _countdown_from_retry_after_at(retry_after_at: str | None) -> int | None:
    if not retry_after_at:
        return None
    try:
        parsed = datetime.fromisoformat(retry_after_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    remaining = int((parsed - datetime.now(tz=UTC)).total_seconds())
    return max(1, remaining)


def _connector_sync_lock_key(connector_id: uuid.UUID) -> int:
    digest = hashlib.sha256(connector_id.bytes).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def _acquire_connector_sync_lock(session, connector_id: uuid.UUID) -> bool:
    lock_key = _connector_sync_lock_key(connector_id)
    result = session.execute(
        text("SELECT pg_try_advisory_lock(:lock_key)"),
        {"lock_key": lock_key},
    )
    return bool(result.scalar())


def _release_connector_sync_lock(session, connector_id: uuid.UUID) -> None:
    lock_key = _connector_sync_lock_key(connector_id)
    try:
        session.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": lock_key},
        )
    except Exception:  # noqa: BLE001
        logger.debug("Failed to release connector sync lock.", exc_info=True)


def _cleanup_connector_session(session) -> None:
    try:
        session.rollback()
    except Exception:  # noqa: BLE001
        logger.debug("Connector worker rollback cleanup failed.", exc_info=True)

    try:
        session.execute(text("RESET ROLE"))
        session.commit()
    except Exception:  # noqa: BLE001
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug(
                "Connector worker rollback after role reset failed.",
                exc_info=True,
            )

    try:
        session.close()
    except Exception:  # noqa: BLE001
        logger.debug("Connector worker session close failed.", exc_info=True)


@celery_app.task(name="app.integrations.workers.tasks_connectors.sync_all_connectors")
def sync_all_connectors_task() -> None:
    """
    Periodic task to discover and trigger syncs for all active connectors.
    """
    factory = get_session_factory()
    with factory() as session:
        result = session.execute(
            select(Connector.id).where(Connector.status == ConnectorStatus.ACTIVE)
        )
        connector_ids = result.scalars().all()

        for cid in connector_ids:
            run_connector_sync_task.delay(str(cid))


@celery_app.task(bind=True, name="app.integrations.workers.tasks_connectors.run_connector_sync")
def run_connector_sync_task(self: Task, connector_id_str: str) -> str:
    """
    Individual sync task for a specific connector.
    """
    start = time.perf_counter()
    settings = get_settings()
    connector_id = uuid.UUID(connector_id_str)
    stage = CONNECTOR_SYNC_STAGE
    session = get_session_factory()()
    acquired_lock = False
    current_attempt = int(self.request.retries) + 1

    try:
        session.execute(text("SET ROLE aks_app"))
        row = session.execute(
            select(Connector, Integration)
            .join(Integration, Connector.integration_id == Integration.id)
            .where(Connector.id == connector_id)
        ).first()
        if not row:
            logger.warning("Connector %s was not found for sync.", connector_id)
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="error").inc()
            return "missing"

        connector, integration = row
        acquired_lock = _acquire_connector_sync_lock(session, connector.id)
        if not acquired_lock:
            logger.info("Connector %s is already being synced.", connector.id)
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="locked").inc()
            WORKER_LOCK_CONTENTION_TOTAL.labels(stage=stage).inc()
            return "locked"

        result = ConnectorOrchestrator(session).sync_connector(
            connector.id,
            connector.tenant_id,
            attempt=current_attempt,
        )

        session.expire_all()
        refreshed = session.get(Connector, connector.id)
        retryable, error_code, checkpoint_status, checkpoint_retry_after_at = (
            _checkpoint_retry_state(refreshed)
            if refreshed is not None
            else (False, None, None, None)
        )
        result_status = str(result.get("status") or "").lower()
        sync_meta = result.get("sync")
        response_retry_after_at = (
            str(sync_meta.get("retry_after_at") or "")
            if isinstance(sync_meta, dict)
            else ""
        ) or None

        if retryable and result_status in {"error", "offline", "degraded"}:
            countdown = _countdown_from_retry_after_at(
                response_retry_after_at or checkpoint_retry_after_at
            ) or _compute_retry_delay(current_attempt=current_attempt)
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="retry").inc()
            WORKER_RETRIES_TOTAL.labels(stage=stage).inc()
            raise self.retry(
                exc=RuntimeError(
                    "Retryable connector sync failure: "
                    f"{error_code or checkpoint_status or result_status or 'unknown'}"
                ),
                countdown=countdown,
                max_retries=max(1, int(getattr(settings, "ingestion_max_attempts", 3))),
            )

        if result_status in {"success", "skipped", "healthy"}:
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="success").inc()
            return result_status

        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="error").inc()
        logger.error(
            "Connector sync finished with non-success status.",
            extra={
                "connector_id": str(connector.id),
                "tenant_id": str(connector.tenant_id),
                "integration_slug": integration.slug,
                "status": result_status,
                "retryable": retryable,
                "error_code": error_code,
                "checkpoint_status": checkpoint_status,
            },
        )
        return result_status or "error"
    except Retry:
        raise
    except Exception:
        logger.exception("Connector sync task failed for %s", connector_id)
        WORKER_JOB_TRANSITIONS_TOTAL.labels(stage=stage, status="error").inc()
        raise
    finally:
        WORKER_STAGE_DURATION_SECONDS.labels(stage=stage).observe(
            time.perf_counter() - start
        )
        if acquired_lock:
            _release_connector_sync_lock(session, connector_id)
        _cleanup_connector_session(session)
