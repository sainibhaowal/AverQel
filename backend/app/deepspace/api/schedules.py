"""Tenant-scoped recurring DeepSpace prompt schedules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.errors import ApiError
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.schedule import DeepSpaceSchedule
from app.platform.database.session import get_db

router = APIRouter(prefix="/deepspace/schedules", tags=["deepspace-schedules"])


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=20_000)
    conversation_id: uuid.UUID
    interval_minutes: int = Field(default=60, ge=5, le=43_200)


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    prompt: str | None = Field(default=None, min_length=1, max_length=20_000)
    interval_minutes: int | None = Field(default=None, ge=5, le=43_200)
    status: str | None = Field(default=None, pattern="^(active|paused)$")


def _owned(db: Session, auth: AuthContext, schedule_id: uuid.UUID) -> DeepSpaceSchedule:
    schedule = db.execute(
        select(DeepSpaceSchedule).where(
            DeepSpaceSchedule.id == schedule_id,
            DeepSpaceSchedule.tenant_id == auth.tenant_id,
            DeepSpaceSchedule.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if schedule is None:
        raise ApiError(code="SCHEDULE_NOT_FOUND", message="Schedule not found.", status_code=404)
    return schedule


def _serialize(item: DeepSpaceSchedule) -> dict[str, object]:
    return {
        "id": str(item.id),
        "name": item.name,
        "prompt": item.prompt,
        "conversation_id": str(item.conversation_id),
        "interval_minutes": item.interval_minutes,
        "status": item.status,
        "next_run_at": item.next_run_at.isoformat(),
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "last_run_id": item.last_run_id,
        "created_at": item.created_at.isoformat(),
    }


@router.post("", dependencies=[Depends(require_permissions("queries:run"))])
def create_schedule(
    payload: ScheduleCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == auth.tenant_id,
            Conversation.user_id == auth.user_id,
            Conversation.kind == "deepspace",
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="DeepSpace conversation not found.",
            status_code=404,
        )
    now = datetime.now(UTC)
    schedule = DeepSpaceSchedule(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=payload.conversation_id,
        name=payload.name.strip(),
        prompt=payload.prompt.strip(),
        interval_minutes=payload.interval_minutes,
        next_run_at=now + timedelta(minutes=payload.interval_minutes),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _serialize(schedule)


@router.get("", dependencies=[Depends(require_permissions("queries:run"))])
def list_schedules(
    auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    items = (
        db.execute(
            select(DeepSpaceSchedule)
            .where(
                DeepSpaceSchedule.tenant_id == auth.tenant_id,
                DeepSpaceSchedule.user_id == auth.user_id,
            )
            .order_by(DeepSpaceSchedule.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_serialize(item) for item in items]


@router.patch("/{schedule_id}", dependencies=[Depends(require_permissions("queries:run"))])
def update_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    schedule = _owned(db, auth, schedule_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if value is not None and key in {"name", "prompt"}:
            value = str(value).strip()
        setattr(schedule, key, value)
    if payload.interval_minutes is not None:
        schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=payload.interval_minutes)
    db.commit()
    db.refresh(schedule)
    return _serialize(schedule)


@router.delete("/{schedule_id}", dependencies=[Depends(require_permissions("queries:run"))])
def delete_schedule(
    schedule_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    schedule = _owned(db, auth, schedule_id)
    db.delete(schedule)
    db.commit()
    return {"status": "deleted", "id": str(schedule_id)}
