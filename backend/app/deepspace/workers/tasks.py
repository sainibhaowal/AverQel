from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import redis
from celery import Task
from sqlalchemy import select, text

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.deepspace.models.artifact_job import DeepSpaceArtifactJob
from app.deepspace.models.schedule_run import DeepSpaceScheduleRun
from app.deepspace.services.chat_service import DeepSpaceChatService, sse
from app.deepspace.services.run_events import append_event, cancellation_key
from app.deepspace.services.task_loop import DeepSpaceTaskLoopStore
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _publish_failure(
    *,
    db: Any,
    settings: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    client_request_id: str,
    message: str,
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
    resume_approval_id: str | None = None,
    resume_user_question_id: str | None = None,
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
    lock_acquired = False
    resolved_conversation_id = parsed_conversation_id

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
        lock_acquired = bool(lock.set(lock_key, "1", nx=True, ex=60 * 60 * 24))
        if not lock_acquired:
            return "already-running"
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, parsed_tenant_id)
        update_schedule_run("running")
        if lock.get(cancellation_key(parsed_tenant_id, parsed_user_id, request_id)):
            if resolved_conversation_id is not None:
                append_event(
                    session,
                    settings=settings,
                    tenant_id=parsed_tenant_id,
                    user_id=parsed_user_id,
                    conversation_id=resolved_conversation_id,
                    client_request_id=request_id,
                    frame=sse(
                        "done",
                        {
                            "conversation_id": str(parsed_conversation_id),
                            "status": "cancelled",
                        },
                    ),
                )
            update_schedule_run("cancelled")
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
            nonlocal resolved_conversation_id
            async for frame in service.stream_turn(
                auth=auth,
                conversation_id=parsed_conversation_id,
                prompt=prompt,
                client_request_id=request_id,
                thinking_enabled=thinking_enabled,
                request=None,
                resume_approval_id=resume_approval_id,
                resume_user_question_id=resume_user_question_id,
            ):
                # Every frame is committed before Redis fan-out. This is what
                # makes a later browser reconnect lossless.
                if resolved_conversation_id is None:
                    data_line = next(
                        (
                            line[5:].strip()
                            for line in frame.splitlines()
                            if line.startswith("data:")
                        ),
                        "",
                    )
                    try:
                        data = json.loads(data_line)
                        resolved_conversation_id = uuid.UUID(str(data["conversation_id"]))
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        pass
                if resolved_conversation_id is not None:
                    append_event(
                        session,
                        settings=settings,
                        tenant_id=parsed_tenant_id,
                        user_id=parsed_user_id,
                        conversation_id=resolved_conversation_id,
                        client_request_id=request_id,
                        frame=frame,
                    )

        asyncio.run(execute())
        update_schedule_run("completed")
        return "completed"
    except Exception:  # noqa: BLE001
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
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist detached DeepSpace failure")
        raise
    finally:
        try:
            session.rollback()
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        cast(Any, session).close()
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
