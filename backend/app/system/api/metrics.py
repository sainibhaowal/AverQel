from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import suppress

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.rbac import require_permissions
from app.core.config import get_settings
from app.platform.database.session import get_db
from app.system.api.admin import require_platform_admin_access
from app.system.schemas.metrics_summary import MetricsSummaryResponse
from app.system.services.audit_service import AuditService
from app.system.services.metrics_service import (
    RUNTIME_METRICS_UPDATE_CHANNEL,
    RuntimeMetricsUnavailableError,
    metrics_payload,
    read_runtime_metrics_summary,
    read_runtime_metrics_summary_async,
)

router = APIRouter(tags=["metrics"])
logger = logging.getLogger(__name__)
METRICS_STREAM_MAX_SECONDS = 300
METRICS_STREAM_SNAPSHOT_SECONDS = 1.0
METRICS_STREAM_HEARTBEAT_SECONDS = 15.0


def _metrics_event(snapshot: dict[str, object]) -> str:
    payload = json.dumps(
        snapshot,
        separators=(",", ":"),
        default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value),
    )
    return f"event: metrics\ndata: {payload}\n\n"


def _metrics_signature(snapshot: dict[str, object]) -> tuple[object, ...]:
    return tuple(snapshot.get(key) for key in sorted(snapshot) if key != "snapshot_at")


async def _stream_metrics_snapshots(
    *,
    client: aioredis.Redis,
    pubsub: aioredis.client.PubSub,
    initial_snapshot: dict[str, object],
) -> AsyncIterator[str]:
    """Send an initial snapshot and subsequent service-wide updates over SSE."""
    started = time.monotonic()
    last_snapshot_at = started
    last_heartbeat_at = started
    last_signature = _metrics_signature(initial_snapshot)
    try:
        yield _metrics_event(initial_snapshot)
        while time.monotonic() - started < METRICS_STREAM_MAX_SECONDS:
            try:
                await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=METRICS_STREAM_SNAPSHOT_SECONDS,
                )
                now = time.monotonic()
                if now - last_snapshot_at >= METRICS_STREAM_SNAPSHOT_SECONDS:
                    snapshot = await read_runtime_metrics_summary_async(client)
                    signature = _metrics_signature(snapshot)
                    if signature != last_signature:
                        yield _metrics_event(snapshot)
                        last_signature = signature
                    last_snapshot_at = now
                if now - last_heartbeat_at >= METRICS_STREAM_HEARTBEAT_SECONDS:
                    yield ": keep-alive\n\n"
                    last_heartbeat_at = now
            except RuntimeMetricsUnavailableError:
                yield 'event: metrics_status\ndata: {"status":"unavailable"}\n\n'
                return
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("Admin runtime metrics stream ended unexpectedly", exc_info=True)
        yield 'event: metrics_status\ndata: {"status":"unavailable"}\n\n'
    finally:
        with suppress(Exception):
            await pubsub.aclose()  # type: ignore[no-untyped-call]
        with suppress(Exception):
            await client.aclose()


@router.get("/metrics")
def get_metrics() -> Response:
    """Raw Prometheus scrape endpoint — kept unauthenticated for internal scraper compatibility."""
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    dependencies=[Depends(require_permissions("admin:metrics:read"))],
)
def get_metrics_summary(
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> MetricsSummaryResponse:
    """Return service-wide counters only to allowlisted platform operators."""
    try:
        summary = read_runtime_metrics_summary()
    except RuntimeMetricsUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Shared runtime metrics are temporarily unavailable.",
        ) from exc
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.metrics.summary.read",
        resource_type="system_metrics",
    )
    return MetricsSummaryResponse(**summary)


@router.get(
    "/metrics/summary/stream",
    dependencies=[Depends(require_permissions("admin:metrics:read"))],
)
async def stream_metrics_summary(
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream service-wide snapshots to an allowlisted platform administrator."""
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.metrics.summary.stream.read",
        resource_type="system_metrics",
    )
    settings = get_settings()
    client: aioredis.Redis | None = None
    pubsub: aioredis.client.PubSub | None = None
    try:
        client = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        assert client is not None
        pubsub = client.pubsub()
        await pubsub.subscribe(RUNTIME_METRICS_UPDATE_CHANNEL)
        initial_snapshot = await read_runtime_metrics_summary_async(client)
    except Exception as exc:  # noqa: BLE001
        if pubsub is not None:
            with suppress(Exception):
                await pubsub.aclose()  # type: ignore[no-untyped-call]
        if client is not None:
            with suppress(Exception):
                await client.aclose()
        raise HTTPException(
            status_code=503,
            detail="Shared runtime metrics are temporarily unavailable.",
        ) from exc
    assert client is not None and pubsub is not None
    return StreamingResponse(
        _stream_metrics_snapshots(
            client=client,
            pubsub=pubsub,
            initial_snapshot=initial_snapshot,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
