from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import cast

from celery import Task  # type: ignore[import-untyped]
from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult

from app.auth.models.tenant import Tenant
from app.core.config import get_settings
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.services.turn_queue import DeepSpaceTurnQueueStore
from app.deepspace.workers.tasks import dispatch_deepspace_turn_queue
from app.documents.models.collection import CollectionChatMedia
from app.documents.services.deletion_service import DeletionService
from app.platform.database.session import get_session_factory
from app.platform.worker.celery_app import celery_app  # type: ignore[attr-defined]
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.audit_service import AuditService
from app.system.services.cache_service import get_redis_client
from app.system.services.metrics_service import MAINTENANCE_JOB_EVENTS_TOTAL
from app.system.services.storage_service import StorageService

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017
DEEPSPACE_RUN_STALE_MINUTES = 30
DEEPSPACE_QUEUE_CLAIM_STALE_MINUTES = 10
STORAGE_CLEANUP_MAX_ATTEMPTS = 12
COLLECTION_CHAT_MEDIA_ORPHAN_HOURS = 24


@celery_app.task(name="maintenance.deepspace_context_cleanup")  # type: ignore[misc]
def deepspace_context_cleanup() -> dict[str, int]:
    """Refresh TTLs for temporary references without deleting unknown epochs."""
    deleted_refs = 0
    session = get_session_factory()()
    try:
        redis_client = get_redis_client()
        keys = list(redis_client.scan_iter(match="deepspace:mcp-result:v1:*", count=500))
        # Redis TTL is authoritative; delete only keys that have expired and
        # are still visible to a backend with a custom eviction policy.
        for key in keys:
            if int(redis_client.ttl(key)) == -1:
                redis_client.expire(key, 900)
        # Context epochs are durable runtime history but currently have no
        # lifecycle identity. Preserve them until a source adapter can prove
        # they belong to safely archived content. Redis remains TTL-governed.
        return {"mcp_result_keys_checked": len(keys), "context_epochs_deleted": 0}
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("DeepSpace context cleanup failed")
        return {"mcp_result_keys_checked": deleted_refs, "context_epochs_deleted": 0}
    finally:
        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        session.close()


@celery_app.task(name="maintenance.heartbeat")  # type: ignore[misc]
def maintenance_heartbeat() -> str:
    session = get_session_factory()()
    stale_total = 0
    try:
        session.execute(text("SET ROLE aks_app"))
        cutoff = datetime.now(tz=UTC) - timedelta(minutes=DEEPSPACE_RUN_STALE_MINUTES)
        tenant_ids = session.execute(text("SELECT id FROM tenants")).scalars().all()
        for tenant_id in tenant_ids:
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            result = session.execute(
                text("""
                    UPDATE deepspace_agent_runs
                    SET status = CASE WHEN cancel_requested THEN 'cancelled' ELSE 'failed' END,
                        last_error = CASE
                            WHEN cancel_requested THEN 'cancelled_after_worker_lease_expired'
                            ELSE 'worker_lease_expired'
                        END,
                        updated_at = CURRENT_TIMESTAMP,
                        heartbeat_at = NULL
                    WHERE tenant_id = :tenant_id
                      AND status IN ('running', 'cancelling')
                      AND (heartbeat_at IS NULL OR heartbeat_at < :cutoff)
                """),
                {"tenant_id": str(tenant_id), "cutoff": cutoff},
            )
            stale_total += int(result.rowcount or 0)
            queue_cutoff = datetime.now(tz=UTC) - timedelta(
                minutes=DEEPSPACE_QUEUE_CLAIM_STALE_MINUTES
            )
            stale_queue_pairs = session.execute(
                select(
                    DeepSpaceQueuedTurn.user_id,
                    DeepSpaceQueuedTurn.conversation_id,
                )
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.status == "running",
                    DeepSpaceQueuedTurn.started_at.is_not(None),
                    DeepSpaceQueuedTurn.started_at < queue_cutoff,
                )
                .distinct()
            ).all()
            for queue_user_id, queue_conversation_id in stale_queue_pairs:
                queue_store = DeepSpaceTurnQueueStore(session)
                recovered = queue_store.recover_stale_claims(
                    tenant_id=tenant_id,
                    user_id=queue_user_id,
                    conversation_id=queue_conversation_id,
                )
                if (
                    recovered
                    and not queue_store.state(
                        tenant_id=tenant_id,
                        user_id=queue_user_id,
                        conversation_id=queue_conversation_id,
                    ).paused
                ):
                    try:
                        dispatch_deepspace_turn_queue.apply_async(
                            kwargs={
                                "tenant_id": str(tenant_id),
                                "user_id": str(queue_user_id),
                                "conversation_id": str(queue_conversation_id),
                            }
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Failed to redispatch a recovered DeepSpace queue claim",
                            extra={
                                "tenant_id": str(tenant_id),
                                "conversation_id": str(queue_conversation_id),
                            },
                        )
            queued_pairs = session.execute(
                select(
                    DeepSpaceQueuedTurn.user_id,
                    DeepSpaceQueuedTurn.conversation_id,
                )
                .where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.status == "queued",
                )
                .distinct()
            ).all()
            for queue_user_id, queue_conversation_id in queued_pairs:
                queue_store = DeepSpaceTurnQueueStore(session)
                if queue_store.state(
                    tenant_id=tenant_id,
                    user_id=queue_user_id,
                    conversation_id=queue_conversation_id,
                ).paused or queue_store.active_request_id(
                    tenant_id=tenant_id,
                    user_id=queue_user_id,
                    conversation_id=queue_conversation_id,
                ):
                    continue
                try:
                    # This is also the retry path if a previous worker
                    # finished a turn but broker submission of the next one
                    # failed after the queue row was already completed.
                    dispatch_deepspace_turn_queue.apply_async(
                        kwargs={
                            "tenant_id": str(tenant_id),
                            "user_id": str(queue_user_id),
                            "conversation_id": str(queue_conversation_id),
                        }
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to dispatch a queued DeepSpace turn",
                        extra={
                            "tenant_id": str(tenant_id),
                            "conversation_id": str(queue_conversation_id),
                        },
                    )
        session.commit()
        if stale_total:
            logger.warning("Finalized %d expired DeepSpace worker leases.", stale_total)
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("DeepSpace lease cleanup failed during maintenance heartbeat.")
    finally:
        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        session.close()
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
            # Legacy run events have no durable run identity. They may belong
            # to an active, paused, waiting, or retryable run, so preserving
            # them is the only safe decision until an authoritative linkage is
            # available. New lifecycle scans handle only registered items.
            run_events_deleted = 0

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
            cleaned_transient_total += idempotency_deleted + deletions_deleted + run_events_deleted

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
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="retention_cleanup", status="error").inc()
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
                logger.debug("Maintenance rollback after role reset failed.", exc_info=True)

        session.close()


@celery_app.task(name="maintenance.storage_cleanup")  # type: ignore[misc]
def storage_cleanup() -> dict[str, int]:
    """Retry failed object deletion without depending on the deleted user row."""
    session = get_session_factory()()
    succeeded = failed = 0
    try:
        session.execute(text("SET ROLE aks_app"))
        # Select jobs across tenants only in the trusted maintenance worker.
        session.execute(text("SELECT set_config('app.tenant_id', 'bypass', true)"))
        now = datetime.now(tz=UTC)
        jobs = list(
            session.query(StorageCleanupJob)
            .filter(
                StorageCleanupJob.status == "pending",
                StorageCleanupJob.next_attempt_at <= now,
                StorageCleanupJob.attempts < STORAGE_CLEANUP_MAX_ATTEMPTS,
            )
            .order_by(StorageCleanupJob.next_attempt_at.asc())
            .limit(100)
            .with_for_update(skip_locked=True)
            .all()
        )
        for job in jobs:
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(job.tenant_id)},
            )
            try:
                StorageService(get_settings()).delete_object(
                    bucket=job.bucket,
                    object_key=job.object_key,
                    raise_on_error=True,
                )
                job.status = "completed"
                job.last_error = None
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                job.attempts += 1
                job.last_error = str(exc)[:2000]
                if job.attempts >= STORAGE_CLEANUP_MAX_ATTEMPTS:
                    job.status = "failed"
                else:
                    job.next_attempt_at = now + timedelta(
                        minutes=min(60, 2 ** min(job.attempts, 6))
                    )
                failed += 1
        session.commit()
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="storage_cleanup", status="ok").inc()
        return {"succeeded": succeeded, "failed": failed}
    except Exception:  # noqa: BLE001
        session.rollback()
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="storage_cleanup", status="error").inc()
        logger.exception("Storage cleanup retry task failed.")
        raise
    finally:
        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        session.close()


@celery_app.task(name="maintenance.collection_chat_media_orphan_sweep")  # type: ignore[misc]
def collection_chat_media_orphan_sweep() -> dict[str, int]:
    """Move abandoned collection uploads into the durable cleanup queue."""
    session = get_session_factory()()
    queued = 0
    try:
        session.execute(text("SET ROLE aks_app"))
        session.execute(text("SELECT set_config('app.tenant_id', 'bypass', true)"))
        cutoff = datetime.now(tz=UTC) - timedelta(hours=COLLECTION_CHAT_MEDIA_ORPHAN_HOURS)
        media_rows = list(
            session.query(CollectionChatMedia)
            .filter(
                CollectionChatMedia.status == "uploaded",
                CollectionChatMedia.attached_message_id.is_(None),
                CollectionChatMedia.created_at < cutoff,
            )
            .order_by(CollectionChatMedia.created_at.asc())
            .limit(200)
            .with_for_update(skip_locked=True)
            .all()
        )
        for media in media_rows:
            session.add(
                StorageCleanupJob(
                    tenant_id=media.tenant_id,
                    owner_user_id=media.uploaded_by_user_id,
                    bucket=media.bucket,
                    object_key=media.object_key,
                )
            )
            media.status = "cleanup_queued"
            queued += 1
        session.commit()
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(
            job="collection_chat_media_orphan_sweep", status="ok"
        ).inc()
        return {"queued": queued}
    except Exception:  # noqa: BLE001
        session.rollback()
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(
            job="collection_chat_media_orphan_sweep", status="error"
        ).inc()
        logger.exception("Collection chat media orphan sweep failed")
        raise
    finally:
        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
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
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="process_data_deletion", status="ok").inc()
        return "ok"

    except Exception:  # noqa: BLE001
        MAINTENANCE_JOB_EVENTS_TOTAL.labels(job="process_data_deletion", status="error").inc()
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
