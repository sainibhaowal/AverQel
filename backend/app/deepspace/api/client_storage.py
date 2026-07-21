from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.deepspace.integrations.client_proxy import (
    STORAGE_REQUEST_PREFIX,
    client_proxy_registry,
)
from app.platform.database.session import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deepspace/client-storage", tags=["deepspace-client-storage"])


@router.websocket("/ws")
async def client_storage_websocket(websocket: WebSocket) -> None:
    """Authenticated client-owned data channel.

    The VPS uses this channel only for transient compute/RPC. Persistent user
    content is written by the desktop/browser client into its local store.
    The server does not acknowledge this channel until authentication succeeds.
    """
    await websocket.accept()
    db = SessionLocal()
    tenant_id = ""
    user_id = ""
    try:
        from app.deepspace.api.chats import (
            _authenticate_websocket_auth_context,
            _require_websocket_permissions,
        )

        settings = get_settings()
        auth = await _authenticate_websocket_auth_context(websocket, db=db, settings=settings)
        _require_websocket_permissions(auth)
        tenant_id = str(auth.tenant_id)
        user_id = str(auth.user_id)
        await client_proxy_registry.register_client(
            tenant_id,
            user_id,
            websocket,
            channel="storage",
        )
        await websocket.send_json(
            {
                "event": "client_storage_ready",
                "protocol": "averqel-client-storage-v1",
                "persistence_owner": "client",
                "server_persistence": "metadata_only_when_rpc_is_used",
            }
        )

        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        request_key = f"{STORAGE_REQUEST_PREFIX}{tenant_id}:{user_id}"
        stop_pump = asyncio.Event()

        async def pump_worker_requests() -> None:
            while not stop_pump.is_set():
                item = await redis_client.blpop(request_key, timeout=1)
                if item is None:
                    continue
                try:
                    await websocket.send_text(item[1])
                except Exception:  # noqa: BLE001
                    return

        pump_task = asyncio.create_task(pump_worker_requests())

        try:
            while True:
                data = await websocket.receive_json()
                if not isinstance(data, dict):
                    continue
                if data.get("event") == "rpc_response":
                    if not client_proxy_registry.handle_response(data):
                        client_proxy_registry.publish_worker_response(
                            data, redis_url=settings.redis_url
                        )
                    continue
                if data.get("event") == "ping":
                    await websocket.send_json({"event": "pong"})
        finally:
            stop_pump.set()
            pump_task.cancel()
            await redis_client.aclose()
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        logger.exception("Client-owned storage WebSocket failed")
        try:
            await websocket.close(code=1011, reason="Client storage channel failed")
        except Exception:  # noqa: BLE001
            pass
    finally:
        if tenant_id and user_id:
            client_proxy_registry.unregister_client(
                tenant_id,
                user_id,
                channel="storage",
                websocket=websocket,
            )
        db.close()
