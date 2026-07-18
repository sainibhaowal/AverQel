from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from app.services.providers.base import ProviderCapabilityError, ProviderRequestError
from app.services.providers.context_window import (
    extract_context_window,
    resolve_verified_context_window,
)
from app.services.providers.reasoning_capabilities import (
    model_supports_reasoning,
    reasoning_capabilities,
)
from app.services.providers.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    HealthCheckResult,
    ProviderModelInfo,
)


class AnthropicProvider:
    provider_name = "anthropic"

    def __init__(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    def bind(self, base_url: str, api_key: str | None = None) -> AnthropicProvider:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def model_supports_reasoning(model_name: str) -> bool:
        return model_supports_reasoning("anthropic", model_name)

    @staticmethod
    def _httpx() -> Any:
        return importlib.import_module("httpx")

    @staticmethod
    def _system_and_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str | None, list[dict[str, str]]]:
        system = None
        normalized: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system" and system is None:
                system = msg.get("content")
                continue
            normalized.append(
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            )
        return system, normalized

    @staticmethod
    def _build_thinking_payload(max_tokens: int) -> dict[str, Any]:
        budget_tokens = max(1024, min(max_tokens // 2, 4096))
        return {"type": "enabled", "budget_tokens": budget_tokens}

    @staticmethod
    def _raise_provider_error(response: Any) -> None:
        message: str | None = None
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
                if isinstance(detail, str) and detail.strip():
                    message = detail.strip()
        if not message:
            text = getattr(response, "text", None)
            if isinstance(text, str) and text.strip():
                message = text.strip()
        raise ProviderRequestError(
            provider_name="anthropic",
            status_code=int(response.status_code),
            message=message,
        )

    @staticmethod
    def _extract_text_blocks(content: list[Any]) -> tuple[str, str | None]:
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                if item_type == "text":
                    text_parts.append(text)
                elif item_type in {"thinking", "redacted_thinking"}:
                    thinking_parts.append(text)
        return "".join(text_parts), "".join(thinking_parts).strip() or None

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        httpx_module = self._httpx()
        system, messages = self._system_and_messages(request.messages)
        headers = {
            "Content-Type": "application/json",
            "x-api-key": request.api_key or "",
            "anthropic-version": "2023-06-01",
        }
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if request.reasoning_enabled and self.model_supports_reasoning(request.model):
            payload["thinking"] = self._build_thinking_payload(request.max_tokens)
        response = httpx_module.post(
            f"{request.base_url.rstrip('/')}/messages",
            headers=headers,
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        content = payload_obj.get("content", [])
        text = ""
        thinking_text: str | None = None
        if isinstance(content, list):
            text, thinking_text = self._extract_text_blocks(content)
        return ChatGenerateResponse(
            content=text,
            thinking_content=thinking_text if request.reasoning_enabled else None,
            usage=payload_obj.get("usage", {}),
        )

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event["type"] == "delta":
                text = event.get("text")
                if isinstance(text, str) and text:
                    yield text

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, str]]:
        httpx_module = self._httpx()
        system, messages = self._system_and_messages(request.messages)
        headers = {
            "Content-Type": "application/json",
            "x-api-key": request.api_key or "",
            "anthropic-version": "2023-06-01",
        }
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if request.reasoning_enabled and self.model_supports_reasoning(request.model):
            payload["thinking"] = self._build_thinking_payload(request.max_tokens)
        async with httpx_module.AsyncClient(
            timeout=float(request.metadata.get("timeout_seconds", 8.0))
        ) as client:
            async with client.stream(
                "POST",
                f"{request.base_url.rstrip('/')}/messages",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    self._raise_provider_error(response)
                event_name = "message"
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_name = line.split(":", 1)[1].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line.split(":", 1)[1].strip()
                    if data == "[DONE]":
                        return
                    try:
                        payload_obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event_name == "content_block_delta":
                        delta = payload_obj.get("delta", {})
                        if not isinstance(delta, dict):
                            continue
                        if request.reasoning_enabled:
                            thinking_text = delta.get("thinking")
                            if isinstance(thinking_text, str) and thinking_text:
                                yield {"type": "thinking", "text": thinking_text}
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            yield {"type": "delta", "text": text}
                        continue
                    if event_name == "content_block_start":
                        block = payload_obj.get("content_block", {})
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type")
                        text = block.get("text")
                        if isinstance(text, str) and text:
                            if request.reasoning_enabled and block_type in {
                                "thinking",
                                "redacted_thinking",
                            }:
                                yield {"type": "thinking", "text": text}
                            elif block_type == "text":
                                yield {"type": "delta", "text": text}

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        result = self.generate(request)
        if result.content:
            yield result.content

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if not self.base_url:
            raise ProviderCapabilityError(
                "anthropic model listing requires a configured endpoint"
            )
        httpx_module = self._httpx()
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }
        response = httpx_module.get(
            f"{self.base_url.rstrip('/')}/models",
            headers=headers,
            timeout=8.0,
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        rows = payload_obj.get("data", [])
        models: list[ProviderModelInfo] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            model_name = item.get("id")
            if not isinstance(model_name, str) or not model_name:
                continue
            live_context_window = extract_context_window(
                item,
                candidate_keys=(
                    "context_window",
                    "context_length",
                    "contextWindow",
                    "contextLength",
                    "input_token_limit",
                    "inputTokenLimit",
                ),
            )
            verified_context_window = resolve_verified_context_window(
                model_name,
                provider_type="anthropic",
            )
            context_window = (
                live_context_window or verified_context_window.context_window
            )
            context_window_source = (
                "live_model"
                if live_context_window is not None
                else verified_context_window.source
            )
            models.append(
                ProviderModelInfo(
                    name=model_name,
                    kind="chat",
                    display_name=(
                        item.get("display_name")
                        if isinstance(item.get("display_name"), str)
                        else None
                    ),
                    context_window=context_window,
                    context_window_source=context_window_source,
                    capabilities={
                        "runtime": "anthropic",
                        **(
                            {"context_window_source": context_window_source}
                            if context_window_source
                            else {}
                        ),
                        **reasoning_capabilities("anthropic", model_name),
                    },
                )
            )
        return models

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        raise ProviderCapabilityError(
            "anthropic embeddings are not supported by this adapter"
        )

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def capabilities_for_model(self, model_name: str) -> dict[str, object]:
        return reasoning_capabilities("anthropic", model_name)

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status="healthy", metadata={"provider": self.provider_name}
        )
