from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.context_window import (
    extract_context_window,
    resolve_verified_context_window,
)
from app.providers.services.reasoning_capabilities import (
    model_supports_reasoning,
    reasoning_capabilities,
)
from app.providers.services.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    HealthCheckResult,
    ProviderModelInfo,
)


class AnthropicProvider:
    provider_name = "anthropic"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
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
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        normalized: list[dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role") or "user")
            content = msg.get("content", "")
            if role == "system":
                if isinstance(content, str) and content.strip():
                    system_parts.append(content.strip())
                continue
            if role == "tool":
                call_id = str(msg.get("tool_call_id") or msg.get("id") or "").strip()
                if call_id:
                    normalized.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": call_id,
                                    "content": (
                                        content
                                        if isinstance(content, str)
                                        else json.dumps(content, ensure_ascii=False)
                                    ),
                                }
                            ],
                        }
                    )
                continue
            if role == "assistant" and msg.get("tool_calls"):
                blocks: list[dict[str, Any]] = []
                if isinstance(content, str) and content.strip():
                    blocks.append({"type": "text", "text": content})
                for call in msg.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    raw_input = function.get("arguments", "{}")
                    try:
                        tool_input = (
                            json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                        )
                    except json.JSONDecodeError:
                        tool_input = {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": str(call.get("id") or f"anthropic_call_{len(blocks)}"),
                            "name": name.strip(),
                            "input": tool_input if isinstance(tool_input, dict) else {},
                        }
                    )
                if blocks:
                    normalized.append({"role": "assistant", "content": blocks})
                continue
            normalized.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": content if isinstance(content, str | list) else str(content),
                }
            )
        return ("\n\n".join(system_parts) or None), normalized

    @staticmethod
    def _tools_payload(request: ChatGenerateRequest) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool in request.tools or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            parameters = function.get("parameters")
            tools.append(
                {
                    "name": name.strip(),
                    "description": str(function.get("description") or "").strip(),
                    "input_schema": (
                        parameters
                        if isinstance(parameters, dict)
                        else {"type": "object", "properties": {}}
                    ),
                }
            )
        return tools

    @staticmethod
    def _tool_choice_payload(request: ChatGenerateRequest) -> dict[str, Any] | None:
        choice = request.tool_choice
        if not choice:
            return None
        if choice == "required":
            return {"type": "any"}
        if choice in {"none", "disabled"}:
            return None
        if isinstance(choice, dict):
            function = choice.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                return {"type": "tool", "name": function["name"]}
        return {"type": "auto"}

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
    def _extract_text_blocks(
        content: list[Any],
    ) -> tuple[str, str | None, list[dict[str, Any]]]:
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "tool_use":
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    tool_calls.append(
                        {
                            "id": str(item.get("id") or f"anthropic_call_{len(tool_calls)}"),
                            "type": "function",
                            "function": {
                                "name": name.strip(),
                                "arguments": json.dumps(
                                    (
                                        item.get("input")
                                        if isinstance(item.get("input"), dict)
                                        else {}
                                    ),
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    )
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                if item_type == "text":
                    text_parts.append(text)
                elif item_type in {"thinking", "redacted_thinking"}:
                    thinking_parts.append(text)
        return "".join(text_parts), "".join(thinking_parts).strip() or None, tool_calls

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
        tools = self._tools_payload(request)
        if tools:
            payload["tools"] = tools
            tool_choice = self._tool_choice_payload(request)
            if tool_choice:
                payload["tool_choice"] = tool_choice
        if (
            request.reasoning_enabled
            and request.tool_choice != "required"
            and self.model_supports_reasoning(request.model)
        ):
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
        tool_calls: list[dict[str, Any]] = []
        if isinstance(content, list):
            text, thinking_text, tool_calls = self._extract_text_blocks(content)
        return ChatGenerateResponse(
            content=text,
            thinking_content=thinking_text,
            tool_calls=tool_calls or None,
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
    ) -> AsyncIterator[dict[str, Any]]:
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
        tools = self._tools_payload(request)
        if tools:
            payload["tools"] = tools
            tool_choice = self._tool_choice_payload(request)
            if tool_choice:
                payload["tool_choice"] = tool_choice
        if (
            request.reasoning_enabled
            and request.tool_choice != "required"
            and self.model_supports_reasoning(request.model)
        ):
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
                current_tool_id: str | None = None
                tool_indexes: dict[str, int] = {}
                tool_names: dict[str, str] = {}
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
                        thinking_text = delta.get("thinking")
                        if isinstance(thinking_text, str) and thinking_text:
                            yield {"type": "thinking", "text": thinking_text}
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            yield {"type": "delta", "text": text}
                        if delta.get("type") == "input_json_delta":
                            fragment = delta.get("partial_json")
                            if (
                                isinstance(fragment, str)
                                and fragment
                                and current_tool_id is not None
                            ):
                                yield {
                                    "type": "tool_calls_delta",
                                    "tool_calls": [
                                        {
                                            "index": tool_indexes[current_tool_id],
                                            "id": current_tool_id,
                                            "function": {
                                                "name": tool_names.get(current_tool_id, ""),
                                                "arguments": fragment,
                                            },
                                        }
                                    ],
                                }
                        continue
                    if event_name == "content_block_start":
                        block = payload_obj.get("content_block", {})
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type")
                        if block_type == "tool_use":
                            current_tool_id = str(
                                block.get("id") or f"anthropic_call_{len(tool_indexes)}"
                            )
                            tool_indexes.setdefault(current_tool_id, len(tool_indexes))
                            name = block.get("name")
                            if isinstance(name, str) and name.strip():
                                tool_names[current_tool_id] = name.strip()
                            initial_input = block.get("input")
                            yield {
                                "type": "tool_calls_delta",
                                "tool_calls": [
                                    {
                                        "index": tool_indexes[current_tool_id],
                                        "id": current_tool_id,
                                        "function": {
                                            "name": tool_names.get(current_tool_id, ""),
                                            "arguments": (
                                                json.dumps(initial_input, ensure_ascii=False)
                                                if isinstance(initial_input, dict) and initial_input
                                                else ""
                                            ),
                                        },
                                    }
                                ],
                            }
                            continue
                        text = block.get("text")
                        if isinstance(text, str) and text:
                            if block_type in {
                                "thinking",
                                "redacted_thinking",
                            }:
                                yield {"type": "thinking", "text": text}
                            elif block_type == "text":
                                yield {"type": "delta", "text": text}
                        continue
                    if event_name == "content_block_stop":
                        current_tool_id = None

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        result = self.generate(request)
        if result.content:
            yield result.content

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if not self.base_url:
            raise ProviderCapabilityError("anthropic model listing requires a configured endpoint")
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
            context_window = live_context_window or verified_context_window.context_window
            context_window_source = (
                "live_model" if live_context_window is not None else verified_context_window.source
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
        raise ProviderCapabilityError("anthropic embeddings are not supported by this adapter")

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def capabilities_for_model(self, model_name: str) -> dict[str, object]:
        return reasoning_capabilities("anthropic", model_name)

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status="healthy", metadata={"provider": self.provider_name})
