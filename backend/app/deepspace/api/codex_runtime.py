from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import get_settings
from app.deepspace.integrations.client_proxy import client_proxy_registry
from app.deepspace.integrations.codex_proxy import (
    CODEX_ONLINE_TTL_SECONDS,
    CODEX_STREAM_TTL_SECONDS,
    codex_online_key,
    codex_request_key,
    codex_response_key,
)
from app.system.services.cache_service import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deepspace/codex-runtime", tags=["deepspace-codex-runtime"])
MAX_FRAME_BYTES = 256_000
MAX_STREAM_BYTES = 16_000_000
CODEX_TICKET_PREFIX = "averqel:codex-runtime:ticket:"
CODEX_TICKET_TTL_SECONDS = 60
_CONSUME_TICKET_SCRIPT = (
    "local v=redis.call('get', KEYS[1]); if v then redis.call('del', KEYS[1]); end; return v"
)
_REFRESH_OWNER_TTL_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_CLAIM_OWNER_SCRIPT = """
if redis.call('exists', KEYS[1]) == 0 then
  redis.call('del', KEYS[2])
  redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[2])
  return 1
end
return 0
"""
_REPLACE_LOCAL_OWNER_SCRIPT = """
if redis.call('get', KEYS[1]) ~= ARGV[1] then
  return 0
end
redis.call('del', KEYS[2])
redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""
_DELETE_OWNER_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  redis.call('del', KEYS[1])
  redis.call('del', KEYS[2])
  return 1
end
return 0
"""
ALLOWED_RESPONSE_EVENTS = {
    "response.output_text.delta",
    "response.output_item.added",
    "response.function_call_arguments.delta",
    "response.function_call_arguments.done",
    "response.completed",
    "response.failed",
    "response.incomplete",
    "error",
}


@router.post(
    "/ticket",
    dependencies=[Depends(require_permissions("queries:run"))],
)
def create_codex_runtime_ticket(
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, int | str]:
    """Mint a short-lived one-use ticket so JWTs never appear in WS URLs."""
    ticket = secrets.token_urlsafe(32)
    get_redis_client().setex(
        f"{CODEX_TICKET_PREFIX}{ticket}",
        CODEX_TICKET_TTL_SECONDS,
        json.dumps(
            {
                "user_id": str(auth.user_id),
                "tenant_id": str(auth.tenant_id),
                "roles": sorted(auth.roles),
                "permissions": sorted(getattr(auth, "permissions", frozenset())),
                "token_id": auth.token_id,
            },
            separators=(",", ":"),
        ),
    )
    return {"ticket": ticket, "expires_in_seconds": CODEX_TICKET_TTL_SECONDS}


@router.websocket("/ws")
async def codex_runtime_websocket(websocket: WebSocket) -> None:
    """Authenticated, transient RPC channel to a user's local Electron runtime."""
    await websocket.accept()
    tenant_id = ""
    user_id = ""
    connection_id = str(uuid.uuid4())
    redis_client = None
    pump_task: asyncio.Task[None] | None = None
    stop_pump = asyncio.Event()
    active_requests: set[str] = set()
    response_sizes: dict[str, int] = {}
    online_key = ""
    try:
        settings = get_settings()
        ticket = str(websocket.query_params.get("ticket") or "").strip()
        if not ticket or len(ticket) > 128:
            await websocket.close(code=4401, reason="A runtime ticket is required")
            return
        redis_client = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url, decode_responses=True
        )
        ticket_data = await redis_client.eval(
            _CONSUME_TICKET_SCRIPT,
            1,
            f"{CODEX_TICKET_PREFIX}{ticket}",
        )
        if not ticket_data:
            await websocket.close(code=4401, reason="The runtime ticket is invalid or expired")
            return
        try:
            claims = json.loads(ticket_data)
            auth = AuthContext(
                user_id=uuid.UUID(str(claims["user_id"])),
                tenant_id=uuid.UUID(str(claims["tenant_id"])),
                roles=frozenset(str(role) for role in claims.get("roles", [])),
                permissions=frozenset(
                    str(permission) for permission in claims.get("permissions", [])
                ),
                token_id=str(claims.get("token_id") or "codex-runtime-ticket"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            await websocket.close(code=4401, reason="The runtime ticket is invalid")
            return
        permissions = set(auth.permissions)
        if "queries:run" not in permissions:
            from app.auth.rbac import resolve_permissions

            permissions = set(
                resolve_permissions(roles=auth.roles, direct_permissions=auth.permissions)
            )
        if "queries:run" not in permissions:
            await websocket.close(code=4403, reason="Insufficient permission")
            return
        tenant_id = str(auth.tenant_id)
        user_id = str(auth.user_id)
        online_key = codex_online_key(tenant_id, user_id)
        existing_socket = client_proxy_registry.get_client_connection(
            tenant_id, user_id, channel="codex"
        )
        existing_connection_id = getattr(
            getattr(existing_socket, "state", None), "codex_runtime_id", None
        )
        acquired = 0
        if existing_connection_id:
            acquired = await redis_client.eval(
                _REPLACE_LOCAL_OWNER_SCRIPT,
                2,
                online_key,
                codex_request_key(tenant_id, user_id),
                existing_connection_id,
                connection_id,
                CODEX_ONLINE_TTL_SECONDS,
            )
        if not acquired:
            acquired = await redis_client.eval(
                _CLAIM_OWNER_SCRIPT,
                2,
                online_key,
                codex_request_key(tenant_id, user_id),
                connection_id,
                CODEX_ONLINE_TTL_SECONDS,
            )
            if not acquired:
                await websocket.close(
                    code=4002, reason="Another AverQel Desktop runtime is connected"
                )
                return
        websocket.state.codex_runtime_id = connection_id
        await client_proxy_registry.register_client(
            tenant_id,
            user_id,
            websocket,
            channel="codex",
        )
        await websocket.send_json(
            {"event": "codex_runtime_ready", "protocol": "averqel-codex-runtime-v1"}
        )

        async def pump_worker_requests() -> None:
            request_key = codex_request_key(tenant_id, user_id)
            while not stop_pump.is_set():
                item = await redis_client.blpop(request_key, timeout=1)
                if item is None:
                    continue
                try:
                    packet = json.loads(item[1])
                    request_id = packet.get("id") if isinstance(packet, dict) else None
                    if not isinstance(request_id, str) or len(request_id) > 64:
                        continue
                    if packet.get("event") == "codex_infer":
                        active_requests.add(request_id)
                        response_sizes[request_id] = 0
                    elif packet.get("event") == "codex_cancel":
                        if request_id not in active_requests:
                            continue
                    await websocket.send_json(packet)
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning("Dropped malformed Codex runtime request")
                except Exception:  # noqa: BLE001
                    return

        pump_task = asyncio.create_task(pump_worker_requests())
        while True:
            frame = await websocket.receive_json()
            if not isinstance(frame, dict):
                continue
            event = frame.get("event")
            if event == "ping":
                refreshed = await redis_client.eval(
                    _REFRESH_OWNER_TTL_SCRIPT,
                    1,
                    online_key,
                    connection_id,
                    CODEX_ONLINE_TTL_SECONDS,
                )
                if not refreshed:
                    await websocket.close(code=4002, reason="Desktop runtime ownership changed")
                    break
                await websocket.send_json({"event": "pong"})
                continue
            if event != "codex_stream_frame":
                continue
            request_id = frame.get("id")
            kind = frame.get("kind")
            if not isinstance(request_id, str) or request_id not in active_requests:
                continue
            if kind not in {"event", "error", "closed"}:
                continue
            data = frame.get("data")
            if kind == "event":
                if not isinstance(data, dict) or data.get("type") not in ALLOWED_RESPONSE_EVENTS:
                    continue
            elif kind == "error":
                if not isinstance(data, dict) or not isinstance(data.get("message"), str):
                    continue
                error_code = data.get("code")
                api_request_id = data.get("request_id")
                parameter = data.get("param")
                http_status = data.get("http_status")
                data = {
                    "message": data["message"][:500],
                    **(
                        {"code": error_code}
                        if isinstance(error_code, str)
                        and len(error_code) <= 96
                        and all(
                            character.isalnum() or character in "_.-" for character in error_code
                        )
                        else {}
                    ),
                    **(
                        {"request_id": api_request_id}
                        if isinstance(api_request_id, str)
                        and len(api_request_id) <= 128
                        and all(
                            character.isalnum() or character in "_.:-"
                            for character in api_request_id
                        )
                        else {}
                    ),
                    **({"param": parameter[:96]} if isinstance(parameter, str) else {}),
                    **(
                        {"http_status": http_status}
                        if isinstance(http_status, int) and 100 <= http_status <= 599
                        else {}
                    ),
                }
            else:
                data = {}
            payload = json.dumps(
                {"kind": kind, "data": data},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            payload_size = len(payload.encode("utf-8"))
            if payload_size > MAX_FRAME_BYTES:
                payload = json.dumps(
                    {
                        "kind": "error",
                        "data": {"message": "Codex stream frame exceeded the size limit."},
                    },
                    separators=(",", ":"),
                )
                kind = "error"
                payload_size = len(payload.encode("utf-8"))
            total_size = response_sizes.get(request_id, 0) + payload_size
            if total_size > MAX_STREAM_BYTES:
                payload = json.dumps(
                    {
                        "kind": "error",
                        "data": {"message": "Codex response exceeded the stream size limit."},
                    },
                    separators=(",", ":"),
                )
                kind = "error"
                payload_size = len(payload.encode("utf-8"))
            response_sizes[request_id] = total_size
            response_key = codex_response_key(request_id)
            await redis_client.xadd(response_key, {"frame": payload})
            await redis_client.expire(response_key, CODEX_STREAM_TTL_SECONDS)
            if kind in {"error", "closed"}:
                active_requests.discard(request_id)
                response_sizes.pop(request_id, None)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("Codex desktop runtime WebSocket failed")
        try:
            await websocket.close(code=1011, reason="Codex runtime channel failed")
        except Exception:  # noqa: BLE001, B110 - cleanup must not mask the original error
            logger.debug("Codex runtime websocket close failed", exc_info=True)
    finally:
        stop_pump.set()
        if pump_task is not None:
            pump_task.cancel()
            await asyncio.gather(pump_task, return_exceptions=True)
        if redis_client is not None:
            if online_key:
                try:
                    await redis_client.eval(
                        _DELETE_OWNER_SCRIPT,
                        2,
                        online_key,
                        codex_request_key(tenant_id, user_id),
                        connection_id,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("Codex runtime online marker cleanup failed", exc_info=True)
            await redis_client.aclose()
        if tenant_id and user_id:
            client_proxy_registry.unregister_client(
                tenant_id,
                user_id,
                channel="codex",
                websocket=websocket,
            )
