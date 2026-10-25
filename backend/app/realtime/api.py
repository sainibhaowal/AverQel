"""Authenticated application-wide realtime WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import get_settings
from app.core.errors import ApiError
from app.deepspace.api.chats import (
    _authenticate_websocket_auth_context,
    _require_websocket_permissions,
)
from app.platform.database.session import SessionLocal
from app.realtime.event_bus import decode_event, stream_key
from app.system.services.cache_service import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/realtime", tags=["realtime"])

REALTIME_TICKET_PREFIX = "averqel:realtime:ticket:"
REALTIME_TICKET_TTL_SECONDS = 60
_CONSUME_TICKET_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""


@router.post("/ticket")
def create_realtime_ticket(auth: AuthContext = Depends(get_auth_context)) -> dict[str, int | str]:
    """Issue a short-lived, single-use ticket for browser WebSocket auth."""
    _require_websocket_permissions(auth)
    ticket = secrets.token_urlsafe(32)
    get_redis_client().setex(
        f"{REALTIME_TICKET_PREFIX}{ticket}",
        REALTIME_TICKET_TTL_SECONDS,
        json.dumps(
            {
                "user_id": str(auth.user_id),
                "tenant_id": str(auth.tenant_id),
                "roles": sorted(auth.roles),
                "permissions": sorted(auth.permissions),
                "token_id": auth.token_id,
            },
            separators=(",", ":"),
        ),
    )
    return {"ticket": ticket, "expires_in_seconds": REALTIME_TICKET_TTL_SECONDS}


async def _authenticate_realtime_ticket(ticket: str, redis_client: Any) -> AuthContext:
    if not ticket or len(ticket) > 128:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="The realtime WebSocket ticket is invalid or expired.",
            status_code=401,
        )

    raw = await redis_client.eval(
        _CONSUME_TICKET_SCRIPT,
        1,
        f"{REALTIME_TICKET_PREFIX}{ticket}",
    )
    if raw is None:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="The realtime WebSocket ticket is invalid or expired.",
            status_code=401,
        )
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("ticket payload must be an object")
        auth = AuthContext(
            user_id=uuid.UUID(str(payload["user_id"])),
            tenant_id=uuid.UUID(str(payload["tenant_id"])),
            roles=frozenset(str(role) for role in payload.get("roles", [])),
            permissions=frozenset(str(permission) for permission in payload.get("permissions", [])),
            token_id=str(payload.get("token_id") or "realtime-ticket"),
        )
        _require_websocket_permissions(auth)
        return auth
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="The realtime WebSocket ticket is invalid.",
            status_code=401,
        ) from exc


@router.websocket("/ws")
async def realtime_websocket(websocket: WebSocket) -> None:
    """Stream only events belonging to the authenticated tenant and user.

    The cursor is a Redis Stream ID. Clients may reconnect with the last ID
    they received; a snapshot endpoint remains the fallback if Redis trimmed
    that cursor.
    """
    db = None
    redis_client = None
    try:
        settings = get_settings()
        try:
            ticket = str(websocket.query_params.get("ticket") or "").strip()
            if ticket:
                redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
                auth = await _authenticate_realtime_ticket(ticket, redis_client)
            else:
                # Retain the existing JWT/API-key handshake for non-browser clients.
                db = SessionLocal()
                auth = await _authenticate_websocket_auth_context(
                    websocket, db=db, settings=settings
                )
                _require_websocket_permissions(auth)
        except ApiError:
            # Reject the handshake before the socket is registered/accepted.
            # Do not include credentials or exception details in logs/reasons.
            logger.info("Rejected unauthenticated application realtime WebSocket")
            await websocket.close(code=1008, reason="Authentication required")
            return

        await websocket.accept()
        if redis_client is None:
            redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
        key = stream_key(auth.tenant_id, auth.user_id)
        cursor = str(websocket.query_params.get("last_event_id") or "$")
        await websocket.send_json(
            {
                "event": "realtime_ready",
                "protocol": "averqel-realtime-v1",
                "cursor": cursor,
            }
        )

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.25)
                if isinstance(message, dict) and message.get("event") == "ping":
                    await websocket.send_json({"event": "pong"})
            except TimeoutError:
                pass

            batches = await redis_client.xread({key: cursor}, block=250, count=100)
            for _, entries in batches or []:
                for entry_id, fields in entries:
                    cursor = str(entry_id)
                    event = decode_event(fields)
                    if event is not None:
                        await websocket.send_json(
                            {"event": "realtime", "cursor": cursor, "payload": event}
                        )
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        logger.exception("Application realtime WebSocket failed")
        try:
            await websocket.close(code=1011, reason="Realtime channel failed")
        except Exception:  # noqa: BLE001
            logger.debug("Realtime WebSocket close failed", exc_info=True)
    finally:
        if redis_client is not None:
            await redis_client.aclose()
        if db is not None:
            db.close()
