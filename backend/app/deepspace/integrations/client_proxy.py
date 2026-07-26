import asyncio
import json
import logging
import uuid
from typing import Any

import redis
from fastapi import WebSocket

logger = logging.getLogger(__name__)

STORAGE_REQUEST_PREFIX = "averqel:client-storage:request:"
STORAGE_RESPONSE_PREFIX = "averqel:client-storage:response:"
STORAGE_RPC_TTL_SECONDS = 90

class ClientProxyRegistry:
    """
    Manages the authenticated client-owned storage connection.

    This channel is limited to encrypted chat, memory, and provider persistence
    RPCs. Local filesystem and shell proxying are intentionally unsupported.
    """
    def __init__(self):
        self._clients: dict[tuple[str, str], WebSocket] = {}
        self._pending_requests: dict[str, asyncio.Future[Any]] = {}

    @staticmethod
    def _key(tenant_id: str, user_id: str, channel: str) -> tuple[str, str]:
        return (f"{tenant_id}:{user_id}", str(channel or "storage"))

    async def register_client(
        self,
        tenant_id: str,
        user_id: str,
        websocket: WebSocket,
        *,
        channel: str = "storage",
    ):
        key = self._key(tenant_id, user_id, channel)
        previous = self._clients.get(key)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=4002, reason="Replaced by a newer client channel")
            except Exception:  # noqa: BLE001
                pass
        self._clients[key] = websocket
        logger.info("Registered client proxy connection for %s/%s", key[0], key[1])

    def unregister_client(
        self,
        tenant_id: str,
        user_id: str,
        *,
        channel: str = "storage",
        websocket: WebSocket | None = None,
    ):
        key = self._key(tenant_id, user_id, channel)
        current = self._clients.get(key)
        if current is not None and (websocket is None or current is websocket):
            del self._clients[key]
            logger.info("Unregistered client proxy connection for %s/%s", key[0], key[1])

    def is_client_connected(
        self, tenant_id: str, user_id: str, *, channel: str = "storage"
    ) -> bool:
        key = self._key(tenant_id, user_id, channel)
        return key in self._clients

    def is_storage_connected(self, tenant_id: str, user_id: str) -> bool:
        key = self._key(tenant_id, user_id, "storage")
        return key in self._clients

    def handle_response(self, data: dict[str, Any]):
        req_id = data.get("id")
        if req_id and req_id in self._pending_requests:
            future = self._pending_requests[req_id]
            if not future.done():
                future.set_result(data)
            return True
        return False

    @staticmethod
    def publish_worker_response(data: dict[str, Any], *, redis_url: str) -> None:
        """Complete an RPC initiated by a Celery worker through Redis."""
        req_id = str(data.get("id") or "")
        if not req_id:
            return
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        key = f"{STORAGE_RESPONSE_PREFIX}{req_id}"
        client.rpush(key, json.dumps(data, separators=(",", ":")))
        client.expire(key, STORAGE_RPC_TTL_SECONDS)

    async def send_and_await_rpc(
        self,
        tenant_id: str,
        user_id: str,
        method: str,
        params: dict[str, Any],
        timeout: float = 30.0,
        *,
        channel: str = "storage",
    ) -> Any:
        key = self._key(tenant_id, user_id, channel)
        websocket = self._clients.get(key)
        if not websocket:
            raise RuntimeError(f"No active client proxy connected for user {key[0]}/{key[1]}")

        req_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = future

        try:
            # Send RPC packet
            await websocket.send_json({
                "event": "rpc_request",
                "id": req_id,
                "method": method,
                "params": params
            })

            # Wait for response from client
            response = await asyncio.wait_for(future, timeout=timeout)
            if "error" in response and response["error"]:
                raise RuntimeError(response["error"])
            return response.get("result")
        except Exception as e:
            raise e
        finally:
            if req_id in self._pending_requests:
                del self._pending_requests[req_id]

    async def db_proxy_call(
        self,
        tenant_id: str,
        user_id: str,
        method: str,
        params: dict[str, Any],
        timeout: float = 30.0,
        *,
        channel: str = "storage",
    ) -> Any:
        """
        Sends database-specific queries to the client proxy.
        For example: method='db.chats.list', method='db.memories.search'
        """
        return await self.send_and_await_rpc(
            tenant_id,
            user_id,
            method,
            params,
            timeout=timeout,
            channel=channel,
        )

client_proxy_registry = ClientProxyRegistry()


def worker_storage_rpc_call(
    *,
    tenant_id: str,
    user_id: str,
    method: str,
    params: dict[str, Any],
    redis_url: str,
    timeout: float = 30.0,
) -> Any:
    """Use Redis only as a transient worker-to-client RPC transport.

    The request is removed by BRPOP and the response is removed by BLPOP. No
    persistent database or object-storage write is performed by this helper.
    """
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    request_id = str(uuid.uuid4())
    request_key = f"{STORAGE_REQUEST_PREFIX}{tenant_id}:{user_id}"
    response_key = f"{STORAGE_RESPONSE_PREFIX}{request_id}"
    payload = {
        "event": "rpc_request",
        "id": request_id,
        "method": method,
        "params": params,
        "transport": "redis_transient",
    }
    client.rpush(request_key, json.dumps(payload, separators=(",", ":")))
    client.expire(request_key, STORAGE_RPC_TTL_SECONDS)
    result = client.blpop(response_key, timeout=max(1, int(timeout)))
    client.delete(response_key)
    if result is None:
        raise TimeoutError(f"Client storage RPC timed out: {method}")
    response = json.loads(result[1])
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    return response.get("result")
