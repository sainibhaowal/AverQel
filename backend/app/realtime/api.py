"""Authenticated application-wide realtime WebSocket."""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.errors import ApiError
from app.deepspace.api.chats import (
    _authenticate_websocket_auth_context,
    _require_websocket_permissions,
)
from app.platform.database.session import SessionLocal
from app.realtime.event_bus import decode_event, stream_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.websocket("/ws")
async def realtime_websocket(websocket: WebSocket) -> None:
    """Stream only events belonging to the authenticated tenant and user.

    The cursor is a Redis Stream ID. Clients may reconnect with the last ID
    they received; a snapshot endpoint remains the fallback if Redis trimmed
    that cursor.
    """
    db = SessionLocal()
    redis_client = None
    try:
        settings = get_settings()
        try:
            auth = await _authenticate_websocket_auth_context(websocket, db=db, settings=settings)
            _require_websocket_permissions(auth)
        except ApiError:
            # Reject the handshake before the socket is registered/accepted.
            # Do not include credentials or exception details in logs/reasons.
            logger.info("Rejected unauthenticated application realtime WebSocket")
            await websocket.close(code=1008, reason="Authentication required")
            return

        await websocket.accept()
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
        db.close()
