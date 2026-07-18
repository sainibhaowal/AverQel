from __future__ import annotations

import importlib
import json
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import replace
from typing import Any, Final, Literal

from app.services.providers.anthropic_provider import AnthropicProvider
from app.services.providers.base import ProviderCapabilityError, ProviderRequestError
from app.services.providers.context_window import (
    extract_context_window,
    resolve_verified_context_window,
)
from app.services.providers.google_provider import GoogleProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider
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
from app.services.providers.url_resolution import resolve_provider_base_url


class OpenCodeZenProvider:
    provider_name = "opencode-zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"

    _GPT_MODEL_PREFIXES: Final[tuple[str, ...]] = ("gpt-",)
    _CLAUDE_MODEL_PREFIXES: Final[tuple[str, ...]] = ("claude-",)
    _GEMINI_MODEL_PREFIXES: Final[tuple[str, ...]] = ("gemini-",)
    _OPENAI_COMPATIBLE_MODEL_PREFIXES: Final[tuple[str, ...]] = (
        "qwen",
        "minimax",
        "glm",
        "kimi",
        "big-pickle",
        "ling",
        "hy3",
        "nemotron",
    )
    _MODEL_NAME_KEYS: Final[tuple[str, ...]] = (
        "id",
        "modelKey",
        "model_key",
        "name",
        "displayName",
        "display_name",
    )
    _MODEL_PAYLOAD_KEYS: Final[tuple[str, ...]] = (
        "data",
        "models",
        "loaded_models",
        "items",
    )
    _CONTEXT_WINDOW_KEYS: Final[tuple[str, ...]] = (
        "context_window",
        "context_length",
        "contextWindow",
        "contextLength",
        "max_context_length",
        "maxContextLength",
        "max_input_tokens",
        "maxInputTokens",
        "input_token_limit",
        "inputTokenLimit",
        "n_ctx",
        "max_model_len",
        "maxModelLen",
    )

    def __init__(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> None:
        self.base_url = resolve_provider_base_url(
            base_url or self.DEFAULT_BASE_URL
        ) or (base_url or self.DEFAULT_BASE_URL)
        self.base_url = self.base_url.rstrip("/")
        self.api_key = api_key

    def bind(self, base_url: str, api_key: str | None = None) -> OpenCodeZenProvider:
        resolved = resolve_provider_base_url(base_url, provider_type=self.provider_name)
        self.base_url = (resolved or base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def model_supports_reasoning(model_name: str) -> bool:
        return model_supports_reasoning(OpenCodeZenProvider.provider_name, model_name)

    @staticmethod
    def _httpx(request: ChatGenerateRequest | None = None) -> Any:
        if request is not None:
            injected = request.metadata.get("httpx_module")
            if injected is not None:
                return injected
        return importlib.import_module("httpx")

    @staticmethod
    def _headers(api_key: str | None) -> dict[str, str]:
        if not api_key:
            raise ProviderRequestError(
                provider_name=OpenCodeZenProvider.provider_name,
                status_code=401,
                message="OpenCode Zen API key is required.",
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_provider_error_message(
        *, payload: dict[str, Any] | None = None, text: str | None = None
    ) -> str | None:
        message: str | None = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
                if isinstance(detail, str) and detail.strip():
                    message = detail.strip()
            detail = payload.get("message")
            if not message and isinstance(detail, str) and detail.strip():
                message = detail.strip()
        if not message:
            if isinstance(text, str) and text.strip():
                message = text.strip()
        return message

    @classmethod
    def _raise_provider_error(
        cls,
        response: Any,
        *,
        payload: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> None:
        if payload is None and text is None:
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                payload = None
            try:
                response_text = getattr(response, "text", None)
            except Exception:  # noqa: BLE001
                response_text = None
            if isinstance(response_text, str):
                text = response_text
        raise ProviderRequestError(
            provider_name=OpenCodeZenProvider.provider_name,
            status_code=int(response.status_code),
            message=cls._extract_provider_error_message(payload=payload, text=text),
        )

    @classmethod
    def _model_family(
        cls, model_name: str
    ) -> Literal["responses", "anthropic", "google", "openai-compatible"]:
        lowered = model_name.strip().lower()
        if any(lowered.startswith(prefix) for prefix in cls._GPT_MODEL_PREFIXES):
            return "responses"
        if any(lowered.startswith(prefix) for prefix in cls._CLAUDE_MODEL_PREFIXES):
            return "anthropic"
        if any(lowered.startswith(prefix) for prefix in cls._GEMINI_MODEL_PREFIXES):
            return "google"
        return "openai-compatible"

    def _resolve_base_url(self, base_url: str | None = None) -> str:
        resolved = resolve_provider_base_url(
            base_url or self.base_url,
            provider_type=self.provider_name,
        )
        if not resolved:
            raise ProviderCapabilityError(
                "OpenCode Zen provider requires a configured base URL"
            )
        return resolved.rstrip("/")

    @classmethod
    def _extract_model_name(cls, item: dict[str, Any]) -> str | None:
        for key in cls._MODEL_NAME_KEYS:
            name = item.get(key)
            if isinstance(name, str) and name.strip():
                return name.strip()
        details = item.get("details")
        if isinstance(details, dict):
            for key in cls._MODEL_NAME_KEYS:
                name = details.get(key)
                if isinstance(name, str) and name.strip():
                    return name.strip()
        return None

    @classmethod
    def _extract_context_window(cls, item: dict[str, Any]) -> int | None:
        return extract_context_window(item, candidate_keys=cls._CONTEXT_WINDOW_KEYS)

    @classmethod
    def _extract_model_items(cls, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in cls._MODEL_PAYLOAD_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if any(
            isinstance(payload.get(key), str | int | float | bool)
            for key in cls._MODEL_NAME_KEYS
        ):
            return [payload]
        return []

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                nested = item.get("content")
                if isinstance(nested, str):
                    parts.append(nested)
            return "".join(parts)
        return ""

    @classmethod
    def _extract_response_text(cls, payload: dict[str, Any]) -> str:
        direct_candidates = (
            payload.get("output_text"),
            payload.get("text"),
            payload.get("content"),
        )
        for candidate in direct_candidates:
            text = cls._extract_text_from_content(candidate)
            if text.strip():
                return text.strip()

        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                text = cls._extract_text_from_content(item.get("text"))
                if not text.strip():
                    text = cls._extract_text_from_content(item.get("content"))
                if item_type in {"message", "assistant_message", "output_text", "text"}:
                    if text.strip():
                        parts.append(text.strip())
            if parts:
                return "".join(parts).strip()
        return ""

    @classmethod
    def _extract_response_thinking(cls, payload: dict[str, Any]) -> str | None:
        candidates = (
            payload.get("reasoning_content"),
            payload.get("reasoning"),
            payload.get("thinking"),
            payload.get("reasoning_summary"),
            payload.get("reasoning_summary_text"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, list):
                summary_parts: list[str] = []
                for item in candidate:
                    if isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            summary_parts.append(text.strip())
                if summary_parts:
                    return "".join(summary_parts).strip()

        output = payload.get("output")
        if isinstance(output, list):
            reasoning_parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                if "reason" not in item_type and "think" not in item_type:
                    continue
                text = cls._extract_text_from_content(item.get("text"))
                if not text.strip():
                    text = cls._extract_text_from_content(item.get("content"))
                if text.strip():
                    reasoning_parts.append(text.strip())
            if reasoning_parts:
                return "".join(reasoning_parts).strip()
        return None

    @classmethod
    def _normalize_arguments(cls, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict | list):
            return json.dumps(value, ensure_ascii=False)
        if value is None:
            return ""
        return str(value)

    @classmethod
    def _extract_response_tool_calls(
        cls, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []

        def append_from_item(item: dict[str, Any]) -> None:
            item_type = str(item.get("type") or "").lower()
            if "function_call" not in item_type and "tool_call" not in item_type:
                return
            name = (
                item.get("name") or item.get("function_name") or item.get("tool_name")
            )
            call_id = item.get("id") or item.get("call_id") or item.get("item_id")
            arguments = item.get("arguments")
            if arguments is None:
                arguments = item.get("input") or item.get("parameters")
            if not isinstance(name, str) or not name.strip():
                return
            if not isinstance(call_id, str) or not call_id.strip():
                call_id = f"call_{len(tool_calls)}"
            tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name.strip(),
                        "arguments": cls._normalize_arguments(arguments),
                    },
                }
            )

        top_level_tool_calls = payload.get("tool_calls")
        if isinstance(top_level_tool_calls, list):
            for item in top_level_tool_calls:
                if isinstance(item, dict):
                    append_from_item(item)

        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, dict):
                    append_from_item(item)
        return tool_calls

    @staticmethod
    def _convert_messages_to_input(
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        instructions_parts: list[str] = []
        input_items: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content", "")
            if role == "system":
                if isinstance(content, str) and content.strip():
                    instructions_parts.append(content.strip())
                continue
            if role == "tool":
                call_id = message.get("tool_call_id") or message.get("id")
                if not isinstance(call_id, str) or not call_id.strip():
                    continue
                output = (
                    content
                    if isinstance(content, str)
                    else json.dumps(content, ensure_ascii=False)
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id.strip(),
                        "output": output,
                    }
                )
                continue
            text = (
                content
                if isinstance(content, str)
                else json.dumps(content, ensure_ascii=False)
            )
            if not text.strip():
                continue
            input_items.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": text,
                }
            )
        instructions = (
            "\n\n".join(part for part in instructions_parts if part).strip() or None
        )
        return instructions, input_items

    @classmethod
    def _build_responses_payload(
        cls,
        request: ChatGenerateRequest,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        instructions, input_items = cls._convert_messages_to_input(request.messages)
        payload: dict[str, Any] = {
            "model": request.model,
            "input": input_items,
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
            "stream": stream,
        }
        if instructions:
            payload["instructions"] = instructions
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        if request.reasoning_enabled and cls.model_supports_reasoning(request.model):
            payload["reasoning"] = {"effort": request.reasoning_effort or "medium"}
        return payload

    async def _stream_responses_events(
        self,
        request: ChatGenerateRequest,
        *,
        base_url: str,
    ) -> AsyncIterator[dict[str, Any]]:
        httpx_module = self._httpx(request)
        payload = self._build_responses_payload(request, stream=True)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )
        tool_call_order: list[str] = []
        tool_call_index_by_id: dict[str, int] = {}
        tool_call_name_by_id: dict[str, str] = {}
        async with httpx_module.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{base_url}/responses",
                headers=self._headers(request.api_key),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    error_payload: dict[str, Any] | None = None
                    error_text: str | None = None
                    try:
                        error_bytes = await response.aread()
                    except Exception:  # noqa: BLE001
                        error_bytes = None
                    if isinstance(error_bytes, bytes | bytearray):
                        error_text = bytes(error_bytes).decode(
                            "utf-8", errors="replace"
                        )
                        try:
                            decoded = json.loads(error_text)
                        except json.JSONDecodeError:
                            decoded = None
                        if isinstance(decoded, dict):
                            error_payload = decoded
                    self._raise_provider_error(
                        response, payload=error_payload, text=error_text
                    )
                current_event = ""
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
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
                    event_name = current_event or str(payload_obj.get("type") or "")
                    lowered = event_name.lower()

                    if (
                        "output_text.delta" in lowered
                        or "output_text" in lowered
                        and "delta" in lowered
                    ):
                        delta = payload_obj.get("delta")
                        if not isinstance(delta, str):
                            delta = payload_obj.get("text")
                        if isinstance(delta, str) and delta:
                            yield {"type": "delta", "text": delta}
                        current_event = ""
                        continue

                    if "reasoning" in lowered or "think" in lowered:
                        delta = payload_obj.get("delta")
                        if not isinstance(delta, str):
                            delta = payload_obj.get("text") or payload_obj.get(
                                "summary"
                            )
                        if isinstance(delta, str) and delta:
                            yield {"type": "thinking", "text": delta}
                        current_event = ""
                        continue

                    if "output_item.added" in lowered or "item.added" in lowered:
                        item = payload_obj.get("item")
                        if not isinstance(item, dict):
                            item = payload_obj.get("output_item")
                        if not isinstance(item, dict):
                            item = payload_obj
                        item_type = str(item.get("type") or "").lower()
                        if "function_call" in item_type or "tool_call" in item_type:
                            item_id = (
                                item.get("id")
                                or item.get("call_id")
                                or item.get("item_id")
                            )
                            if not isinstance(item_id, str) or not item_id.strip():
                                item_id = f"call_{len(tool_call_order)}"
                            if item_id not in tool_call_index_by_id:
                                tool_call_index_by_id[item_id] = len(tool_call_order)
                                tool_call_order.append(item_id)
                            fn_name = (
                                item.get("name")
                                or item.get("function_name")
                                or item.get("tool_name")
                            )
                            if isinstance(fn_name, str) and fn_name.strip():
                                tool_call_name_by_id[item_id] = fn_name.strip()
                            arguments = item.get("arguments")
                            if arguments is None:
                                arguments = item.get("input") or item.get("parameters")
                            normalized_arguments = self._normalize_arguments(arguments)
                            if (
                                isinstance(fn_name, str)
                                and fn_name.strip()
                                and normalized_arguments
                            ):
                                yield {
                                    "type": "tool_calls_delta",
                                    "tool_calls": [
                                        {
                                            "index": tool_call_index_by_id[item_id],
                                            "id": item_id,
                                            "function": {
                                                "name": fn_name.strip(),
                                                "arguments": normalized_arguments,
                                            },
                                        }
                                    ],
                                }
                        current_event = ""
                        continue

                    if (
                        "function_call_arguments.delta" in lowered
                        or "arguments.delta" in lowered
                    ):
                        item_id = payload_obj.get("item_id") or payload_obj.get(
                            "call_id"
                        )
                        if not isinstance(item_id, str) or not item_id.strip():
                            item_id = f"call_{len(tool_call_order)}"
                        if item_id not in tool_call_index_by_id:
                            tool_call_index_by_id[item_id] = len(tool_call_order)
                            tool_call_order.append(item_id)
                        delta = payload_obj.get("delta")
                        if not isinstance(delta, str):
                            delta = payload_obj.get("arguments")
                        if isinstance(delta, dict):
                            delta = json.dumps(delta, ensure_ascii=False)
                        if isinstance(delta, str) and delta:
                            yield {
                                "type": "tool_calls_delta",
                                "tool_calls": [
                                    {
                                        "index": tool_call_index_by_id[item_id],
                                        "id": item_id,
                                        "function": {
                                            "name": tool_call_name_by_id.get(
                                                item_id, ""
                                            ),
                                            "arguments": delta,
                                        },
                                    }
                                ],
                            }
                        current_event = ""
                        continue

                    if isinstance(payload_obj.get("output"), list):
                        for item in payload_obj["output"]:
                            if not isinstance(item, dict):
                                continue
                            item_type = str(item.get("type") or "").lower()
                            if "function_call" in item_type or "tool_call" in item_type:
                                item_id = (
                                    item.get("id")
                                    or item.get("call_id")
                                    or item.get("item_id")
                                )
                                if not isinstance(item_id, str) or not item_id.strip():
                                    item_id = f"call_{len(tool_call_order)}"
                                if item_id not in tool_call_index_by_id:
                                    tool_call_index_by_id[item_id] = len(
                                        tool_call_order
                                    )
                                    tool_call_order.append(item_id)
                                fn_name = (
                                    item.get("name")
                                    or item.get("function_name")
                                    or item.get("tool_name")
                                )
                                if isinstance(fn_name, str) and fn_name.strip():
                                    tool_call_name_by_id[item_id] = fn_name.strip()
                                arguments = item.get("arguments")
                                if arguments is None:
                                    arguments = item.get("input") or item.get(
                                        "parameters"
                                    )
                                fragment = self._normalize_arguments(arguments)
                                yield {
                                    "type": "tool_calls_delta",
                                    "tool_calls": [
                                        {
                                            "index": tool_call_index_by_id[item_id],
                                            "id": item_id,
                                            "function": {
                                                "name": (
                                                    fn_name.strip()
                                                    if isinstance(fn_name, str)
                                                    else ""
                                                ),
                                                "arguments": fragment,
                                            },
                                        }
                                    ],
                                }
                            elif "reason" in item_type or "think" in item_type:
                                text = self._extract_text_from_content(item.get("text"))
                                if not text.strip():
                                    text = self._extract_text_from_content(
                                        item.get("content")
                                    )
                                if text.strip():
                                    yield {"type": "thinking", "text": text.strip()}
                            else:
                                text = self._extract_text_from_content(item.get("text"))
                                if not text.strip():
                                    text = self._extract_text_from_content(
                                        item.get("content")
                                    )
                                if text.strip():
                                    yield {"type": "delta", "text": text.strip()}
                        current_event = ""

    def _gpt_family_response(
        self, request: ChatGenerateRequest, *, base_url: str
    ) -> ChatGenerateResponse:
        httpx_module = self._httpx(request)
        payload = self._build_responses_payload(request, stream=False)
        response = httpx_module.post(
            f"{base_url}/responses",
            headers=self._headers(request.api_key),
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        content = self._extract_response_text(payload_obj)
        thinking_content = (
            self._extract_response_thinking(payload_obj)
            if request.reasoning_enabled
            else None
        )
        tool_calls = self._extract_response_tool_calls(payload_obj)
        usage = payload_obj.get("usage", {})
        return ChatGenerateResponse(
            content=content,
            thinking_content=thinking_content,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage if isinstance(usage, dict) else {},
        )

    def _family_provider(self, request: ChatGenerateRequest, *, base_url: str) -> tuple[
        str,
        AnthropicProvider | GoogleProvider | OpenAICompatibleProvider | None,
    ]:
        family = self._model_family(request.model)
        if family == "responses":
            return family, None
        if family == "anthropic":
            return family, AnthropicProvider().bind(base_url, request.api_key)
        if family == "google":
            return family, GoogleProvider().bind(base_url, request.api_key)
        return family, OpenAICompatibleProvider(
            base_url=base_url, api_key=request.api_key
        )

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        base_url = self._resolve_base_url(request.base_url)
        family, provider = self._family_provider(request, base_url=base_url)
        if family == "responses":
            return self._gpt_family_response(request, base_url=base_url)
        if provider is None:
            raise ProviderCapabilityError("OpenCode Zen provider routing failed")
        adapted_request = replace(
            request,
            base_url=base_url,
            metadata={**dict(request.metadata), "provider_type": self.provider_name},
        )
        return provider.generate(adapted_request)

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event["type"] == "delta":
                text = event.get("text")
                if isinstance(text, str) and text:
                    yield text

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        base_url = self._resolve_base_url(request.base_url)
        family, provider = self._family_provider(request, base_url=base_url)
        if family == "responses":
            async for event in self._stream_responses_events(
                request, base_url=base_url
            ):
                yield event
            return
        if provider is None:
            raise ProviderCapabilityError("OpenCode Zen provider routing failed")
        adapted_request = replace(
            request,
            base_url=base_url,
            metadata={**dict(request.metadata), "provider_type": self.provider_name},
        )
        async for event in provider.stream_generate_events(adapted_request):
            yield event

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        base_url = self._resolve_base_url(request.base_url)
        family, provider = self._family_provider(request, base_url=base_url)
        adapted_request = replace(
            request,
            base_url=base_url,
            metadata={**dict(request.metadata), "provider_type": self.provider_name},
        )
        if family == "responses":
            result = self._gpt_family_response(request, base_url=base_url)
            if result.content:
                yield from self._chunk_text(result.content)
            return
        if provider is None:
            raise ProviderCapabilityError("OpenCode Zen provider routing failed")
        yield from provider.stream_generate_sync(adapted_request)

    def list_models(self) -> Sequence[ProviderModelInfo]:
        base_url = self._resolve_base_url()
        httpx_module = self._httpx()
        response = httpx_module.get(
            f"{base_url}/models",
            headers=self._headers(self.api_key),
            timeout=8.0,
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        discovered = self._extract_model_items(payload_obj)
        infos: list[ProviderModelInfo] = []
        for item in discovered:
            model_name = self._extract_model_name(item)
            if not model_name:
                continue
            family = self._model_family(model_name)
            live_context_window = self._extract_context_window(item)
            verified_context_window = resolve_verified_context_window(
                model_name,
                provider_type=self.provider_name,
            )
            context_window = (
                live_context_window or verified_context_window.context_window
            )
            context_window_source = (
                "live_model"
                if live_context_window is not None
                else verified_context_window.source
            )
            infos.append(
                ProviderModelInfo(
                    name=model_name,
                    kind="chat",
                    context_window=context_window,
                    context_window_source=context_window_source,
                    display_name=(
                        item.get("display_name")
                        if isinstance(item.get("display_name"), str)
                        else (
                            item.get("displayName")
                            if isinstance(item.get("displayName"), str)
                            else model_name
                        )
                    ),
                    capabilities={
                        "runtime": self.provider_name,
                        "family": family,
                        **(
                            {"context_window_source": context_window_source}
                            if context_window_source
                            else {}
                        ),
                        "endpoint": (
                            f"{base_url}/responses"
                            if family == "responses"
                            else (
                                f"{base_url}/messages"
                                if family == "anthropic"
                                else (
                                    f"{base_url}/models/{model_name}:generateContent"
                                    if family == "google"
                                    else f"{base_url}/chat/completions"
                                )
                            )
                        ),
                        **reasoning_capabilities(
                            self.provider_name, model_name, base_url=base_url
                        ),
                    },
                )
            )
        return infos

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def health_check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            models = self.list_models()
        except Exception as exc:  # noqa: BLE001
            return HealthCheckResult(
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                error_code="provider_health_failed",
                error_message_redacted=str(exc),
            )
        return HealthCheckResult(
            status="healthy" if models else "degraded",
            latency_ms=int((time.monotonic() - start) * 1000),
            metadata={"result_count": len(models)},
        )

    @staticmethod
    def _chunk_text(text: str, *, size: int = 48) -> Sequence[str]:
        normalized = text.replace("\r\n", "\n")
        chunks: list[str] = []
        cursor = 0
        while cursor < len(normalized):
            end = min(len(normalized), cursor + size)
            chunk = normalized[cursor:end]
            if chunk:
                chunks.append(chunk)
            cursor = end
        return chunks
