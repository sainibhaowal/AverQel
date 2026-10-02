"""Tenant-scoped realtime event publication and replay over Redis Streams."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import redis
import redis.asyncio as aioredis

from app.core.config import Settings

STREAM_PREFIX = "averqel:realtime:v1"
STREAM_MAXLEN = 10_000


def stream_key(tenant_id: uuid.UUID | str, user_id: uuid.UUID | str) -> str:
    return f"{STREAM_PREFIX}:{tenant_id}:{user_id}"


def build_event(
    *,
    event_type: str,
    resource: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "resource": resource,
        "data": data or {},
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def publish_event_sync(
    client: redis.Redis,
    *,
    tenant_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    event_type: str,
    resource: str,
    data: dict[str, Any] | None = None,
) -> str:
    """Publish from synchronous workers without opening a second Redis path."""
    payload = build_event(event_type=event_type, resource=resource, data=data)
    return str(
        client.xadd(
            stream_key(tenant_id, user_id),
            {"payload": json.dumps(payload, separators=(",", ":"))},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
    )


async def publish_event(
    settings: Settings,
    *,
    tenant_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    event_type: str,
    resource: str,
    data: dict[str, Any] | None = None,
) -> str | None:
    """Publish one bounded, user-scoped event and return its Redis cursor.

    Redis Streams provide a short replay window for reconnects. REST snapshots
    remain the source of truth when a cursor has expired or a stream is lost.
    """
    payload = build_event(event_type=event_type, resource=resource, data=data)
    client = aioredis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    try:
        return str(
            await client.xadd(
                stream_key(tenant_id, user_id),
                {"payload": json.dumps(payload, separators=(",", ":"))},
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
        )
    finally:
        await client.aclose()


def decode_event(fields: dict[str, Any]) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(fields.get("payload") or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("type"), str) or not isinstance(payload.get("resource"), str):
        return None
    return payload
