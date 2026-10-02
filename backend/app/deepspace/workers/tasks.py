from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import redis
from celery import Task
from sqlalchemy import select, text, update

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.deepspace.models.agent_runtime import DeepSpaceRunEvent
from app.deepspace.models.artifact_job import DeepSpaceArtifactJob
from app.deepspace.models.schedule_run import DeepSpaceScheduleRun
from app.deepspace.services.chat_service import DeepSpaceChatService, sse
from app.deepspace.services.run_events import append_event, cancellation_key
from app.deepspace.services.runtime_store import DeepSpaceRuntimeStore
from app.deepspace.services.task_loop import DeepSpaceTaskLoopStore
from app.deepspace.services.turn_queue import DeepSpaceTurnQueueStore
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="deepspace.index_conversation")  # type: ignore[misc]
def index_deepspace_conversation(*, tenant_id: str, user_id: str, conversation_id: str) -> str:
    """Build derived chat-search rows outside the interactive chat worker."""
    session = get_session_factory()()
    try:
        parsed_tenant_id = uuid.UUID(tenant_id)
        parsed_user_id = uuid.UUID(user_id)
        parsed_conversation_id = uuid.UUID(conversation_id)
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, parsed_tenant_id)
        from app.deepspace.services.conversation_retrieval import ConversationRetrievalService

        result = ConversationRetrievalService(session, get_settings()).index_conversation(
            tenant_id=parsed_tenant_id,
            user_id=parsed_user_id,
            conversation_id=parsed_conversation_id,
        )
        session.commit()
        return f"indexed={result['indexed']} removed={result['removed']}"
    except Exception:
        session.rollback()
        logger.warning("DeepSpace conversation indexing failed safely", exc_info=True)
        raise
    finally:
        try:
            session.rollback()
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        cast(Any, session).close()


@celery_app.task(name="deepspace.dispatch_turn_queue")  # type: ignore[misc]
def dispatch_deepspace_turn_queue(*, tenant_id: str, user_id: str, conversation_id: str) -> str:
    """Claim one durable FIFO turn and hand it to the isolated chat worker."""
    session = get_session_factory()()
    try:
        parsed_tenant_id = uuid.UUID(tenant_id)
        parsed_user_id = uuid.UUID(user_id)
        parsed_conversation_id = uuid.UUID(conversation_id)
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, parsed_tenant_id)
        claimed = DeepSpaceTurnQueueStore(session).claim_next(
            tenant_id=parsed_tenant_id,
            user_id=parsed_user_id,
            conversation_id=parsed_conversation_id,
        )
        if claimed is None:
            return "idle"
        try:
            run_deepspace_task.apply_async(
                kwargs={
                    "tenant_id": str(claimed.tenant_id),
                    "user_id": str(claimed.user_id),
                    "roles": claimed.roles,
                    "permissions": claimed.permissions,
                    "conversation_id": str(claimed.conversation_id),
                    "prompt": claimed.prompt,
                    "client_request_id": claimed.client_request_id,
                    "resume_from_request_id": claimed.resume_from_request_id,
                    "thinking_enabled": claimed.thinking_enabled,
                    "reasoning_effort": claimed.reasoning_effort,
                    "attachment_file_ids": claimed.attachment_file_ids,
                }
            )
        except Exception:
            DeepSpaceTurnQueueStore(session).release_claim(
                tenant_id=claimed.tenant_id,
                user_id=claimed.user_id,
                conversation_id=claimed.conversation_id,
                client_request_id=claimed.client_request_id,
            )
            raise
        return "dispatched"
    finally:
        try:
            session.rollback()
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        cast(Any, session).close()


def _publish_failure(
    *,
    db: Any,
    settings: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    client_request_id: str,
    message: str,
    run_id: uuid.UUID | None = None,
) -> None:
    if conversation_id is None:
        return
    append_event(
        db,
        settings=settings,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        run_id=run_id,
        frame=sse("error", {"code": "DEEPSPACE_WORKER_FAILED", "message": message}),
    )


@celery_app.task(bind=True, name="deepspace.run")  # type: ignore[misc]
def run_deepspace_task(
    self: Task,
    *,
    tenant_id: str,
    user_id: str,
    roles: list[str],
    permissions: list[str],
    conversation_id: str | None,
    prompt: str,
    client_request_id: str,
    thinking_enabled: bool,
    reasoning_effort: str | None = None,
    resume_approval_id: str | None = None,
    resume_user_question_id: str | None = None,
    resume_from_request_id: str | None = None,
    attachment_file_ids: list[str] | None = None,
) -> str:
    """Run a DeepSpace turn outside the browser request lifecycle."""
    settings = get_settings()
    parsed_tenant_id = uuid.UUID(tenant_id)
    parsed_user_id = uuid.UUID(user_id)
    parsed_conversation_id = uuid.UUID(conversation_id) if conversation_id else None
    request_id = str(client_request_id).strip()
    session = get_session_factory()()
    lock = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    lock_key = f"deepspace:worker-lock:{request_id}"
    # A continuation deliberately reuses the original request id.  Use an
    # owner token so this worker can release only its own lock on completion.
    lock_token = str(getattr(self.request, "id", "") or uuid.uuid4())
    lock_acquired = False
    resolved_conversation_id = parsed_conversation_id
    terminal_status = "completed"
    terminal_error: str | None = None
    resolved_run_id: uuid.UUID | None = None

    def update_schedule_run(status: str, error: str | None = None) -> None:
        if not request_id.startswith("schedule-"):
            return
        run = session.execute(
            select(DeepSpaceScheduleRun).where(
                DeepSpaceScheduleRun.request_id == request_id,
                DeepSpaceScheduleRun.tenant_id == parsed_tenant_id,
                DeepSpaceScheduleRun.user_id == parsed_user_id,
            )
        ).scalar_one_or_none()
        if run is None:
            return
        run.status = status
        run.error = error[:2000] if error else None
        if status == "running":
            run.started_at = datetime.now(UTC)
        if status in {"completed", "failed", "cancelled"}:
            run.completed_at = datetime.now(UTC)
        session.commit()

    try:
        lock_acquired = bool(lock.set(lock_key, lock_token, nx=True, ex=60 * 60 * 24))
        if not lock_acquired:
            return "already-running"
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, parsed_tenant_id)
        update_schedule_run("running")
        if lock.get(cancellation_key(parsed_tenant_id, parsed_user_id, request_id)):
            terminal_status = "cancelled"
            terminal_error = "user_cancelled"
            if resolved_conversation_id is not None:
                append_event(
                    session,
                    settings=settings,
                    tenant_id=parsed_tenant_id,
                    user_id=parsed_user_id,
                    conversation_id=resolved_conversation_id,
                    client_request_id=request_id,
                    run_id=resolved_run_id,
                    frame=sse(
                        "done",
                        {
                            "conversation_id": str(parsed_conversation_id),
                            "status": "cancelled",
                        },
                    ),
                )
            update_schedule_run("cancelled")
            if resolved_conversation_id is not None:
                # The API has already marked the durable run ``cancelling``.
                # This early-return path does not enter ChatService, which
                # normally finalizes the run.  Finalize it here so a cancelled
                # request cannot leave the conversation permanently blocked.
                DeepSpaceRuntimeStore(session).finish_requested_cancellations(
                    tenant_id=parsed_tenant_id,
                    user_id=parsed_user_id,
                    conversation_id=resolved_conversation_id,
                )
                DeepSpaceTurnQueueStore(session).finish(
                    tenant_id=parsed_tenant_id,
                    user_id=parsed_user_id,
                    conversation_id=resolved_conversation_id,
                    client_request_id=request_id,
                    status="cancelled",
                )
            return "cancelled"
        auth = AuthContext(
            user_id=parsed_user_id,
            tenant_id=parsed_tenant_id,
            roles=frozenset(roles),
            permissions=frozenset(permissions),
            token_id=f"deepspace-worker:{request_id}",
            auth_type="worker",
        )
        service = DeepSpaceChatService(db=session, settings=settings)

        async def execute() -> None:
            nonlocal resolved_conversation_id, resolved_run_id, terminal_error, terminal_status
            async for frame in service.stream_turn(
                auth=auth,
                conversation_id=parsed_conversation_id,
                prompt=prompt,
                client_request_id=request_id,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                request=None,
                resume_approval_id=resume_approval_id,
                resume_user_question_id=resume_user_question_id,
                resume_from_request_id=resume_from_request_id,
                attachment_file_ids=attachment_file_ids,
            ):
                # Every frame is committed before Redis fan-out. This is what
                # makes a later browser reconnect lossless.
                data_line = next(
                    (line[5:].strip() for line in frame.splitlines() if line.startswith("data:")),
                    "",
                )
                try:
                    data = json.loads(data_line)
                    if isinstance(data, dict):
                        if resolved_conversation_id is None and data.get("conversation_id"):
                            resolved_conversation_id = uuid.UUID(str(data["conversation_id"]))
                        raw_run_id = data.get("run_id")
                        if raw_run_id:
                            resolved_run_id = uuid.UUID(str(raw_run_id))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    pass
                if resolved_conversation_id is not None:
                    if resolved_run_id is not None:
                        # The first meta frame may arrive after earlier
                        # frames. Backfill those rows before publishing the
                        # current event. Legacy rows from before this release
                        # remain NULL and are conservatively protected.
                        session.execute(
                            update(DeepSpaceRunEvent)
                            .where(
                                DeepSpaceRunEvent.tenant_id == parsed_tenant_id,
                                DeepSpaceRunEvent.user_id == parsed_user_id,
                                DeepSpaceRunEvent.conversation_id == resolved_conversation_id,
                                DeepSpaceRunEvent.client_request_id == request_id,
                                DeepSpaceRunEvent.run_id.is_(None),
                            )
                            .values(run_id=resolved_run_id)
                        )
                    append_event(
                        session,
                        settings=settings,
                        tenant_id=parsed_tenant_id,
                        user_id=parsed_user_id,
                        conversation_id=resolved_conversation_id,
                        client_request_id=request_id,
                        frame=frame,
                        run_id=resolved_run_id,
                    )
                if "event: done" in frame:
                    data_line = next(
                        (
                            line[5:].strip()
                            for line in frame.splitlines()
                            if line.startswith("data:")
                        ),
                        "{}",
                    )
                    try:
                        terminal_status = str(json.loads(data_line).get("status") or "completed")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        terminal_status = "completed"
                elif "event: error" in frame:
                    # A worker must not report a failed provider stream as a
                    # completed queue turn merely because no `done` frame was
                    # emitted. The queue can then advance with truthful state.
                    terminal_status = "failed"
                    data_line = next(
                        (
                            line[5:].strip()
                            for line in frame.splitlines()
                            if line.startswith("data:")
                        ),
                        "{}",
                    )
                    try:
                        terminal_error = str(
                            json.loads(data_line).get("message")
                            or "DeepSpace stream returned an error"
                        )[:2000]
                    except (TypeError, ValueError, json.JSONDecodeError):
                        terminal_error = "DeepSpace stream returned an error"

        asyncio.run(execute())
        # A clarification or approval is deliberately non-terminal.  Its
        # queue record remains active until the same turn is resumed or
        # cancelled, so a later queued prompt cannot overtake it.
        if terminal_status not in {
            "completed",
            "cancelled",
            "failed",
            "awaiting_user",
            "awaiting_approval",
        }:
            terminal_status = "completed"
        update_schedule_run(terminal_status)
        return terminal_status
    except Exception:  # noqa: BLE001
        terminal_status = "failed"
        terminal_error = "DeepSpace run failed"
        logger.exception("Detached DeepSpace run failed", extra={"request_id": request_id})
        try:
            update_schedule_run("failed", "DeepSpace run failed")
        except Exception:  # noqa: BLE001
            session.rollback()
        try:
            _publish_failure(
                db=session,
                settings=settings,
                tenant_id=parsed_tenant_id,
                user_id=parsed_user_id,
                conversation_id=parsed_conversation_id,
                client_request_id=request_id,
                message="DeepSpace could not complete this response. Please retry.",
                run_id=resolved_run_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist detached DeepSpace failure")
        raise
    finally:
        if resolved_conversation_id is not None:
            try:
                queue_store = DeepSpaceTurnQueueStore(session)
                queue_store.finish(
                    tenant_id=parsed_tenant_id,
                    user_id=parsed_user_id,
                    conversation_id=resolved_conversation_id,
                    client_request_id=request_id,
                    status=terminal_status,
                    error=terminal_error,
                )
                if (
                    terminal_status not in {"failed", "blocked"}
                    and not queue_store.state(
                        tenant_id=parsed_tenant_id,
                        user_id=parsed_user_id,
                        conversation_id=resolved_conversation_id,
                    ).paused
                ):
                    # Queue-owned turns advance here. A direct run-now turn
                    # may also need to wake work that the user resumed while
                    # that independent chat was running; an idle dispatcher
                    # is harmless when no queued row exists.
                    dispatch_deepspace_turn_queue.apply_async(
                        kwargs={
                            "tenant_id": str(parsed_tenant_id),
                            "user_id": str(parsed_user_id),
                            "conversation_id": str(resolved_conversation_id),
                        }
                    )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to advance DeepSpace turn queue")
        try:
            session.rollback()
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        cast(Any, session).close()
        if lock_acquired:
            try:
                # Never remove a lock acquired by a replacement worker after
                # an unexpected expiry.
                if lock.get(lock_key) == lock_token:
                    lock.delete(lock_key)
            except Exception:  # noqa: BLE001
                logger.warning("Failed to release DeepSpace worker lock", exc_info=True)
        cast(Any, lock).close()


@celery_app.task(bind=True, name="deepspace.artifact_create")  # type: ignore[misc]
def create_artifact_task(self: Task, *, job_id: str, tenant_id: str, user_id: str) -> str:
    """Materialize a queued artifact through the existing Library ownership boundary."""
    del self
    session = get_session_factory()()
    try:
        parsed_tenant = uuid.UUID(tenant_id)
        parsed_user = uuid.UUID(user_id)
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, parsed_tenant)
        job = session.execute(
            select(DeepSpaceArtifactJob).where(
                DeepSpaceArtifactJob.id == uuid.UUID(job_id),
                DeepSpaceArtifactJob.tenant_id == parsed_tenant,
                DeepSpaceArtifactJob.user_id == parsed_user,
            )
        ).scalar_one_or_none()
        if job is None:
            return "not-found"
        job.status = "running"
        session.commit()
        result = DeepSpaceTaskLoopStore(session).write_workspace_file(
            tenant_id=parsed_tenant,
            user_id=parsed_user,
            conversation_id=job.conversation_id,
            filename=job.filename,
            content=job.content,
        )
        job.status = "completed"
        job.file_id = uuid.UUID(str(result["id"]))
        job.completed_at = datetime.now(UTC)
        session.commit()
        return str(job.id)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        try:
            job = session.execute(
                select(DeepSpaceArtifactJob).where(DeepSpaceArtifactJob.id == uuid.UUID(job_id))
            ).scalar_one_or_none()
            if job is not None:
                job.status = "failed"
                job.error = str(exc)[:2000]
                session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        raise
    finally:
        session.close()
