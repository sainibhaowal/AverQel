from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, Literal, cast

import redis

from app.core.config import get_settings
from app.deepspace.integrations.codex_proxy import (
    CODEX_ENQUEUE_CANCEL_SCRIPT,
    CODEX_ENQUEUE_REQUEST_SCRIPT,
    CODEX_MAX_PENDING_REQUESTS,
    CODEX_STREAM_TTL_SECONDS,
    codex_online_key,
    codex_request_key,
    codex_response_key,
)
from app.providers.services.base import (
    ChatProvider,
    EmbeddingProvider,
    ModelDiscoveryProvider,
    ModelInstallProvider,
    ProviderCapabilityError,
    ProviderRequestError,
)
from app.providers.services.tool_definitions import unique_tool_definitions
from app.providers.services.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResult,
    ProviderModelInfo,
)

logger = logging.getLogger(__name__)


def _close(client: redis.Redis) -> None:
    client.close()  # type: ignore[no-untyped-call]


class LocalDesktopRuntimeProvider(
    ChatProvider,
    EmbeddingProvider,
    ModelDiscoveryProvider,
    ModelInstallProvider,
):
    """LM Studio/Ollama access through the signed-in user's Electron runtime."""

    request_timeout_seconds = 300

    def __init__(
        self,
        *,
        provider_type: str,
        tenant_id: str | None,
        owner_user_id: str | None,
        base_url: str | None,
    ) -> None:
        if provider_type not in {"lmstudio", "ollama"}:
            raise ValueError("Unsupported local desktop provider")
        self.provider_name = provider_type
        self.provider_type = provider_type
        self.tenant_id = tenant_id
        self.owner_user_id = owner_user_id
        self.base_url = base_url or (
            "http://127.0.0.1:1234/v1" if provider_type == "lmstudio" else "http://127.0.0.1:11434"
        )

    def _identity(self, request_metadata: dict[str, Any] | None = None) -> tuple[str, str]:
        metadata = request_metadata or {}
        tenant_id = str(metadata.get("tenant_id") or self.tenant_id or "")
        user_id = str(metadata.get("user_id") or self.owner_user_id or "")
        if not tenant_id or not user_id:
            raise ProviderRequestError(
                self.provider_name, 503, "The desktop runtime owner could not be identified."
            )
        return tenant_id, user_id

    def health_check(self) -> HealthCheckResult:
        try:
            self._identity()
        except ProviderRequestError as exc:
            return HealthCheckResult(
                status="unhealthy",
                error_code="local_runtime_identity_missing",
                error_message_redacted=exc.message,
            )
        started = time.monotonic()
        try:
            result = self._rpc("health", {}, timeout_seconds=15)
        except ProviderRequestError as exc:
            status: Literal["degraded", "unhealthy"] = (
                "degraded" if exc.status_code in {429, 503, 504} else "unhealthy"
            )
            return HealthCheckResult(
                status=status,
                error_code="local_runtime_unavailable",
                error_message_redacted=exc.message,
                metadata={"runtime": "electron", "provider": self.provider_type},
            )
        return HealthCheckResult(
            status="healthy",
            latency_ms=round((time.monotonic() - started) * 1000),
            metadata={"runtime": "electron", "provider": self.provider_type, **result},
        )

    def _enqueue(
        self, *, operation: str, request: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> tuple[redis.Redis, str, str, str]:
        tenant_id, user_id = self._identity(metadata)
        client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        request_id = str(uuid.uuid4())
        response_key = codex_response_key(request_id)
        packet = json.dumps(
            {
                "event": "local_infer" if operation == "chat" else "local_operation",
                "id": request_id,
                "params": {
                    "provider_type": self.provider_type,
                    "base_url": self.base_url,
                    "operation": operation,
                    "request": request,
                },
            },
            separators=(",", ":"),
        )
        try:
            client.delete(response_key)
            queued = cast(
                int,
                client.eval(
                    CODEX_ENQUEUE_REQUEST_SCRIPT,
                    2,
                    codex_online_key(tenant_id, user_id),
                    codex_request_key(tenant_id, user_id),
                    packet,
                    str(CODEX_STREAM_TTL_SECONDS),
                    str(CODEX_MAX_PENDING_REQUESTS),
                ),
            )
        except redis.RedisError as exc:
            _close(client)
            raise ProviderRequestError(
                self.provider_name,
                503,
                "The desktop local runtime relay is temporarily unavailable.",
            ) from exc
        if queued == 0:
            _close(client)
            raise ProviderRequestError(
                self.provider_name,
                503,
                "Open AverQel Desktop and keep it online to use this local provider.",
            )
        if queued < 0:
            _close(client)
            raise ProviderRequestError(
                self.provider_name,
                429,
                "The desktop local runtime queue is full. Wait for an active request to finish.",
            )
        return client, request_id, response_key, codex_request_key(tenant_id, user_id)

    def _rpc(
        self,
        operation: str,
        request: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        client, request_id, response_key, request_key = self._enqueue(
            operation=operation, request=request, metadata=metadata
        )
        tenant_id, user_id = self._identity(metadata)
        last_id = "0-0"
        started = time.monotonic()
        try:
            deadline = timeout_seconds or self.request_timeout_seconds
            while time.monotonic() - started < deadline:
                rows = cast(
                    list[tuple[str, list[tuple[str, dict[str, str]]]]],
                    client.xread({response_key: last_id}, count=32, block=1000),
                )
                for _key, events in rows or []:
                    for event_id, fields in events:
                        last_id = event_id
                        frame = json.loads(fields.get("frame") or "{}")
                        if frame.get("kind") == "error":
                            data = frame.get("data") if isinstance(frame.get("data"), dict) else {}
                            raise ProviderRequestError(
                                self.provider_name,
                                int(data.get("http_status") or 502),
                                str(data.get("message") or "Local runtime request failed."),
                            )
                        if frame.get("kind") == "event" and isinstance(frame.get("data"), dict):
                            data = frame["data"]
                            if data.get("type") == "result":
                                return (
                                    data.get("result")
                                    if isinstance(data.get("result"), dict)
                                    else {}
                                )
                        if frame.get("kind") == "closed":
                            raise ProviderRequestError(
                                self.provider_name,
                                502,
                                "The local runtime ended before returning a result.",
                            )
                if not client.exists(codex_online_key(tenant_id, user_id)):
                    raise ProviderRequestError(
                        self.provider_name,
                        503,
                        "The AverQel Desktop local runtime connection closed.",
                    )
            raise ProviderRequestError(
                self.provider_name, 504, "The local runtime request timed out."
            )
        finally:
            try:
                client.expire(response_key, 1)
            except redis.RedisError:
                pass
            _close(client)

    def list_models(self) -> Sequence[ProviderModelInfo]:
        result = self._rpc("models", {})
        models = result.get("models")
        if not isinstance(models, list):
            return []
        return [
            ProviderModelInfo(
                name=item["name"],
                kind="chat",
                display_name=item.get("display_name") or item["name"],
                capabilities=dict(item.get("capabilities") or {}),
            )
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
        ]

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        # Both runtimes expose embedding models through their model endpoint;
        # callers may still assign a discovered name explicitly for embeddings.
        return [
            ProviderModelInfo(
                name=model.name,
                kind="embedding",
                display_name=model.display_name,
                capabilities={**model.capabilities, "local": True},
            )
            for model in self.list_models()
        ]

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_local_models(self) -> Sequence[ProviderModelInfo]:
        return self.list_models()

    def chat_model_is_usable(self, model_name: str) -> bool:
        """Discovery already came from the user's local runtime; avoid a duplicate probe."""
        return isinstance(model_name, str) and bool(model_name.strip())

    def pull_model(self, model_name: str) -> HealthCheckResult:
        result = self._rpc("pull", {"model": model_name})
        return HealthCheckResult(status="healthy", metadata=result)

    def delete_model(self, model_name: str) -> HealthCheckResult:
        raise ProviderCapabilityError("Model deletion must be managed in the local runtime.")

    def embed_many(self, request: EmbeddingRequest) -> EmbeddingResponse:
        result = self._rpc(
            "embed", {"model": request.model, "input": request.texts}, request.metadata
        )
        vectors = result.get("embeddings")
        if not isinstance(vectors, list):
            vectors = []
        return EmbeddingResponse(vectors=[vector for vector in vectors if isinstance(vector, list)])

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        raise ProviderCapabilityError("Local desktop providers require DeepSpace streaming.")

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        raise ProviderCapabilityError(
            "Local desktop providers require asynchronous DeepSpace streaming."
        )

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event.get("type") == "delta" and isinstance(event.get("text"), str):
                yield event["text"]

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        metadata = dict(request.metadata)
        tenant_id, user_id = self._identity(metadata)
        client, request_id, response_key, request_key = self._enqueue(
            operation="chat", request=self._chat_payload(request), metadata=metadata
        )
        last_id = "0-0"
        started = time.monotonic()
        completed = False
        try:
            while time.monotonic() - started < self.request_timeout_seconds:
                rows = cast(
                    list[tuple[str, list[tuple[str, dict[str, str]]]]],
                    await asyncio.to_thread(
                        client.xread, {response_key: last_id}, count=32, block=1000
                    ),
                )
                if not rows:
                    if not await asyncio.to_thread(
                        client.exists, codex_online_key(tenant_id, user_id)
                    ):
                        raise ProviderRequestError(
                            self.provider_name,
                            503,
                            "The AverQel Desktop local runtime connection closed during the response.",
                        )
                    continue
                for _key, events in rows:
                    for event_id, fields in events:
                        last_id = event_id
                        frame = json.loads(fields.get("frame") or "{}")
                        kind, data = frame.get("kind"), frame.get("data")
                        if kind == "error":
                            detail = data if isinstance(data, dict) else {}
                            raise ProviderRequestError(
                                self.provider_name,
                                int(detail.get("http_status") or 502),
                                str(detail.get("message") or "Local runtime request failed."),
                            )
                        if kind == "event" and isinstance(data, dict):
                            if data.get("type") == "completed":
                                completed = True
                            if data.get("type") != "result":
                                yield data
                        if kind == "closed":
                            if completed:
                                return
                            raise ProviderRequestError(
                                self.provider_name,
                                502,
                                "The local runtime ended before the response completed.",
                            )
            raise ProviderRequestError(
                self.provider_name, 504, "The local runtime response timed out."
            )
        finally:
            if not completed:
                try:
                    removed = await asyncio.to_thread(
                        client.lrem,
                        request_key,
                        1,
                        json.dumps(
                            {"event": "local_infer", "id": request_id}, separators=(",", ":")
                        ),
                    )
                    if not removed:
                        await asyncio.to_thread(
                            client.eval,
                            CODEX_ENQUEUE_CANCEL_SCRIPT,
                            2,
                            codex_online_key(tenant_id, user_id),
                            request_key,
                            json.dumps(
                                {"event": "local_cancel", "id": request_id}, separators=(",", ":")
                            ),
                            str(CODEX_STREAM_TTL_SECONDS),
                        )
                except redis.RedisError:
                    logger.debug("Local runtime cancellation could not be relayed", exc_info=True)
            await asyncio.to_thread(client.expire, response_key, 1)
            _close(client)

    @staticmethod
    def _chat_payload(request: ChatGenerateRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        tools = unique_tool_definitions(request.tools)
        if tools:
            payload["tools"] = tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        if request.reasoning_effort:
            payload["reasoning_effort"] = request.reasoning_effort
        return payload
