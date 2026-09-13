"""Celery beat poller for tenant-owned recurring DeepSpace schedules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.auth.rbac import resolve_permissions
from app.deepspace.models.schedule import DeepSpaceSchedule
from app.deepspace.workers.tasks import run_deepspace_task
from app.platform.database.session import get_session_factory
from app.platform.worker.celery_app import celery_app


@celery_app.task(name="deepspace.dispatch_schedules")  # type: ignore[misc]
def dispatch_schedules() -> int:
    """Claim due schedules once and enqueue normal, auditable DeepSpace runs."""
    db = get_session_factory()()
    now = datetime.now(UTC)
    count = 0
    try:
        rows = (
            db.execute(
                select(DeepSpaceSchedule)
                .where(DeepSpaceSchedule.status == "active", DeepSpaceSchedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
                .limit(100)
            )
            .scalars()
            .all()
        )
        permissions = sorted(resolve_permissions(roles=frozenset({"user"})))
        for schedule in rows:
            request_id = f"schedule-{schedule.id}-{uuid.uuid4()}"
            schedule.last_run_at = now
            schedule.last_run_id = request_id
            schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
            run_deepspace_task.delay(
                tenant_id=str(schedule.tenant_id),
                user_id=str(schedule.user_id),
                roles=["user"],
                permissions=permissions,
                conversation_id=str(schedule.conversation_id),
                prompt=schedule.prompt,
                client_request_id=request_id,
                thinking_enabled=True,
            )
            count += 1
        db.commit()
        return count
    finally:
        db.close()
