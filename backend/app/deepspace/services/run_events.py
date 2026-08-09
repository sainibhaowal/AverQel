"""Durable event log and live fan-out for detached DeepSpace runs."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from typing import Any

import redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.deepspace.models.agent_runtime import DeepSpaceRunEvent

logger = logging.getLogger(__name__)


def channel_name(client_request_id: str) -> str:
    return f"deepspace:run:{client_request_id}"


def cancellation_key(tenant_id: uuid.UUID, user_id: uuid.UUID, client_request_id: str) -> str:
    return f"deepspace:cancel:{tenant_id}:{user_id}:{client_request_id}"


def event_name_from_frame(frame: str) -> str:
    for line in frame.splitlines():
        if line.startswith("event:"):
            return line.partition(":")[2].strip() or "message"
    return "message"


def is_terminal_event(event_name: str) -> bool:
    return event_name in {"done", "error"}


def append_event(
    db: Session,
    *,
    settings: Settings,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_request_id: str,
    frame: str,
) -> DeepSpaceRunEvent:
    """Commit one frame before publishing it, so reconnects never miss it."""
    normalized_id = str(client_request_id).strip()
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )
    latest = db.execute(
        select(func.max(DeepSpaceRunEvent.sequence)).where(
            DeepSpaceRunEvent.tenant_id == tenant_id,
            DeepSpaceRunEvent.user_id == user_id,
            DeepSpaceRunEvent.conversation_id == conversation_id,
            DeepSpaceRunEvent.client_request_id == normalized_id,
        )
    ).scalar_one()
    event = DeepSpaceRunEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=normalized_id,
        sequence=int(latest or 0) + 1,
        frame=frame,
        event_name=event_name_from_frame(frame),
    )
    db.add(event)
    db.commit()
    payload = json.dumps(
        {"sequence": event.sequence, "frame": event.frame},
        separators=(",", ":"),
    )
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.publish(channel_name(normalized_id), payload)
        client.close()
    except Exception:  # noqa: BLE001
        # PostgreSQL is authoritative. A reconnect will replay this event even
        # if Redis is temporarily unavailable.
        logger.warning("DeepSpace live event publish failed", exc_info=True)
    return event


def load_events(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    client_request_id: str,
    after_sequence: int = 0,
) -> list[DeepSpaceRunEvent]:
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )
    return list(
        db.execute(
            select(DeepSpaceRunEvent)
            .where(
                DeepSpaceRunEvent.tenant_id == tenant_id,
                DeepSpaceRunEvent.user_id == user_id,
                DeepSpaceRunEvent.conversation_id == conversation_id,
                DeepSpaceRunEvent.client_request_id == str(client_request_id).strip(),
                DeepSpaceRunEvent.sequence > max(0, int(after_sequence)),
            )
            .order_by(DeepSpaceRunEvent.sequence.asc())
        )
        .scalars()
        .all()
    )


def decode_live_event(payload: str) -> tuple[int, str] | None:
    try:
        data: dict[str, Any] = json.loads(payload)
        return int(data["sequence"]), str(data["frame"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


def frames_after(
    events: Iterable[DeepSpaceRunEvent], *, after_sequence: int = 0
) -> list[tuple[int, str]]:
    return [(event.sequence, event.frame) for event in events if event.sequence > after_sequence]


_TIMELINE_EVENT_NAMES = {
    "agent_plan",
    "thinking",
    "lane_thinking",
    "lane_agent_thinking",
    "agent_thinking",
    "tool_start",
    "tool_result",
    "tool_error",
    "ask_user_question",
    "permission_request",
    "permission_granted",
    "permission_denied",
    "agent_testing",
    "agent_verifying",
    "agent_self_correct",
}
_THINKING_EVENT_NAMES = {
    "thinking",
    "lane_thinking",
    "lane_agent_thinking",
    "agent_thinking",
}


def timeline_events(
    events: Iterable[DeepSpaceRunEvent],
) -> list[dict[str, Any]]:
    """Return a compact, ordered replay of meaningful UI activity events.

    The full SSE log remains the reconnect source of truth. History only needs
    semantic timeline events: adjacent thinking frames are coalesced, while
    tool and approval boundaries are retained so the original order survives
    a page reload without duplicating every token delta in the history API.
    """

    result: list[dict[str, Any]] = []
    for event in events:
        event_name = event.event_name or event_name_from_frame(event.frame)
        if event_name not in _TIMELINE_EVENT_NAMES:
            continue
        data_line = next(
            (
                line.partition(":")[2].strip()
                for line in event.frame.splitlines()
                if line.startswith("data:")
            ),
            "{}",
        )
        try:
            payload = json.loads(data_line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload.setdefault("timestamp", event.created_at.isoformat())
        if event_name in _THINKING_EVENT_NAMES and result:
            previous = result[-1]
            if previous.get("event") in _THINKING_EVENT_NAMES:
                previous_data = dict(previous.get("data") or {})
                previous_data["text"] = (
                    f"{previous_data.get('text') or ''}{payload.get('text') or ''}"
                )
                previous["data"] = previous_data
                previous["sequence_end"] = event.sequence
                continue
        result.append(
            {
                "event": event_name,
                "data": payload,
                "sequence": event.sequence,
                "sequence_end": event.sequence,
            }
        )
    return result
