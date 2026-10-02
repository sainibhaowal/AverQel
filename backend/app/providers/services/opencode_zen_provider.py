from __future__ import annotations

import hashlib
import importlib
import json
import re
import secrets
import string
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import replace
from typing import Any, Final, Literal

from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.context_window import (
    extract_context_window,
    extract_max_output_tokens,
    resolve_verified_context_window,
)
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.openai_compatible import OpenAICompatibleProvider
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
from app.providers.services.url_resolution import resolve_provider_base_url


class OpenCodeZenProvider:
    provider_name = "opencode-zen"
    DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
    _MODEL_DISCOVERY_ATTEMPTS = 3
    _MODEL_DISCOVERY_RETRY_DELAYS = (0.25, 0.5)

    # Zen routes these model families through the Responses API.  Keeping the
    # list explicit matters because the gateway returns a mixture of API
    # families from one catalogue (the old implementation sent Muse/Grok to
    # /chat/completions, which produced opaque upstream 500s).
    _GPT_MODEL_PREFIXES: Final[tuple[str, ...]] = ("gpt-", "muse-", "grok-")
    # OpenCode serves Qwen3 models through the Anthropic-compatible Messages
    # endpoint, even though their names do not start with ``claude-``.
    _CLAUDE_MODEL_PREFIXES: Final[tuple[str, ...]] = ("claude-", "qwen")
    _GEMINI_MODEL_PREFIXES: Final[tuple[str, ...]] = ("gemini-",)
    _OPENAI_COMPATIBLE_MODEL_PREFIXES: Final[tuple[str, ...]] = (
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
    BASE62_CHARS: Final[str] = string.digits + string.ascii_uppercase + string.ascii_lowercase
    OPENCODE_SESSION_RE: Final[re.Pattern[str]] = re.compile(r"^ses_[0-9a-f]{12}[0-9A-Za-z]{14}$")
    OPENCODE_REQUEST_RE: Final[re.Pattern[str]] = re.compile(r"^msg_[0-9a-f]{12}[0-9A-Za-z]{14}$")
    OPENCODE_UA: Final[str] = "opencode/1.18.31"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = resolve_provider_base_url(base_url or self.DEFAULT_BASE_URL) or (
            base_url or self.DEFAULT_BASE_URL
        )
        self.base_url = self.base_url.rstrip("/")
        self.api_key = api_key
        # OpenCode's free pool requires a client session identifier in the
        # canonical format: ses_ + 12 hex timestamp digits + 14 Base62 characters.
        self.session_id = self.generate_session_id()

    def bind(self, base_url: str, api_key: str | None = None) -> OpenCodeZenProvider:
        resolved = resolve_provider_base_url(base_url, provider_type=self.provider_name)
        self.base_url = (resolved or base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def is_free_model(model_name: str | None) -> bool:
        if not model_name:
            return False
        return "free" in model_name.strip().lower()

    @classmethod
    def generate_session_id(cls, timestamp: int | None = None) -> str:
        now_ms = int(time.time() * 1000) if timestamp is None else timestamp
        current = now_ms * 0x1000 + 1
        value = ~current
        time_hex = "".join(f"{((value >> (40 - 8 * i)) & 0xFF):02x}" for i in range(6))
        random_part = "".join(secrets.choice(cls.BASE62_CHARS) for _ in range(14))
        return f"ses_{time_hex}{random_part}"

    @classmethod
    def generate_request_id(cls, timestamp: int | None = None) -> str:
        now_ms = int(time.time() * 1000) if timestamp is None else timestamp
        current = now_ms * 0x1000 + 1
        time_hex = "".join(f"{((current >> (40 - 8 * i)) & 0xFF):02x}" for i in range(6))
        random_part = "".join(secrets.choice(cls.BASE62_CHARS) for _ in range(14))
        return f"msg_{time_hex}{random_part}"

    @classmethod
    def translate_session_id(cls, session_id: str | None) -> str:
        if session_id and cls.OPENCODE_SESSION_RE.match(session_id.strip()):
            return session_id.strip()
        raw = (session_id or "").strip()
        digest = hashlib.sha256(f"opencode\0averqel\0{raw}".encode()).digest()
        time_hex = digest[:6].hex()
        random_part = "".join(cls.BASE62_CHARS[b % 62] for b in digest[6:20])
        return f"ses_{time_hex}{random_part}"

    @classmethod
    def _normalize_user_agent(cls, downstream_ua: str | None) -> str:
        if not downstream_ua:
            return cls.OPENCODE_UA
        m = re.search(r"opencode/(\d+)\.(\d+)(?:\.(\d+))?", downstream_ua, re.IGNORECASE)
        if not m:
            return cls.OPENCODE_UA
        major = int(m.group(1))
        minor = int(m.group(2))
        if major > 1 or (major == 1 and minor >= 17):
            return downstream_ua
        return cls.OPENCODE_UA

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

    def _headers(
        self,
        api_key: str | None,
        *,
        session_id: str | None = None,
        model: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, str]:
        is_free = self.is_free_model(model)
        token = "public" if is_free and (not api_key or api_key == "public") else api_key
        if not token and is_free:
            token = "public"
        if not token:
            raise ProviderRequestError(
                provider_name=OpenCodeZenProvider.provider_name,
                status_code=401,
                message="OpenCode Zen API key is required.",
            )
        # Upstream OpenCode enforces Authorization: Bearer public for free-tier models.
        auth_header = "Bearer public" if is_free else f"Bearer {token}"
        canonical_session = self.translate_session_id(session_id or self.session_id)
        request_id = self.generate_request_id()
        ua = self._normalize_user_agent(user_agent)

        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "User-Agent": ua,
            "x-opencode-client": "desktop",
            "x-opencode-session": canonical_session,
            "x-opencode-request": request_id,
            "x-opencode-project": "global",
            "X-Session-ID": canonical_session,
        }

    def _request_headers(self, request: ChatGenerateRequest) -> dict[str, str]:
        session_id = str(request.metadata.get("conversation_id") or "").strip() or None
        extra = request.metadata.get("extra_headers") or {}
        user_agent = extra.get("User-Agent") or extra.get("user-agent")
        return self._headers(
            request.api_key,
            session_id=session_id,
            model=request.model,
            user_agent=user_agent,
        )

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
            raise ProviderCapabilityError("OpenCode Zen provider requires a configured base URL")
        return resolved.rstrip("/")

    @staticmethod
    def _is_retryable_model_discovery_error(httpx_module: Any, exc: Exception) -> bool:
        """Identify transient transport failures without hiding provider errors."""

        retryable_types = tuple(
            error_type
            for name in (
                "ConnectError",
                "TimeoutException",
                "NetworkError",
                "RemoteProtocolError",
            )
            if isinstance(error_type := getattr(httpx_module, name, None), type)
        )
        return bool(retryable_types) and isinstance(exc, retryable_types)

    def _get_model_discovery_response(self, *, base_url: str, httpx_module: Any) -> Any:
        """Retry transient DNS/connection failures from the model catalog endpoint."""

        for attempt in range(self._MODEL_DISCOVERY_ATTEMPTS):
            try:
                return httpx_module.get(
                    f"{base_url}/models",
                    headers=self._headers(self.api_key),
                    timeout=8.0,
                )
            except Exception as exc:  # noqa: BLE001 - filtered to transport errors below
                is_last_attempt = attempt == self._MODEL_DISCOVERY_ATTEMPTS - 1
                if is_last_attempt or not self._is_retryable_model_discovery_error(
                    httpx_module, exc
                ):
                    raise
                time.sleep(self._MODEL_DISCOVERY_RETRY_DELAYS[attempt])

        raise RuntimeError("OpenCode Zen model discovery exhausted its retry budget")

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
            isinstance(payload.get(key), str | int | float | bool) for key in cls._MODEL_NAME_KEYS
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
    def _extract_response_tool_calls(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []

        def append_from_item(item: dict[str, Any]) -> None:
            item_type = str(item.get("type") or "").lower()
            if "function_call" not in item_type and "tool_call" not in item_type:
                return
            name = item.get("name") or item.get("function_name") or item.get("tool_name")
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

    @classmethod
    def _convert_messages_to_input(
        cls,
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        instructions_parts: list[str] = []
        input_items: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content", "")
            if role == "system":
                text = (
                    content if isinstance(content, str) else cls._extract_text_from_content(content)
                )
                if text.strip():
                    instructions_parts.append(text.strip())
                continue
            if role == "tool":
                call_id = message.get("tool_call_id") or message.get("id") or message.get("call_id")
                if not call_id or not str(call_id).strip():
                    continue
                output = (
                    content
                    if isinstance(content, str)
                    else json.dumps(content, ensure_ascii=False) if content is not None else ""
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id).strip(),
                        "output": output,
                    }
                )
                continue

            if role == "assistant":
                text = (
                    content if isinstance(content, str) else cls._extract_text_from_content(content)
                )
                if text.strip():
                    input_items.append(
                        {
                            "role": "assistant",
                            "content": text,
                        }
                    )
                raw_tool_calls = message.get("tool_calls")
                if isinstance(raw_tool_calls, list):
                    for call in raw_tool_calls:
                        if not isinstance(call, dict):
                            continue
                        call_id = call.get("id") or call.get("call_id")
                        function = call.get("function")
                        source = function if isinstance(function, dict) else call
                        name = (
                            source.get("name")
                            or source.get("function_name")
                            or source.get("tool_name")
                        )
                        if not isinstance(name, str) or not name.strip():
                            continue
                        arguments = source.get("arguments")
                        if arguments is None:
                            arguments = source.get("input") or source.get("parameters")
                        call_id_str = (
                            str(call_id).strip()
                            if call_id and str(call_id).strip()
                            else f"call_{len(input_items)}"
                        )
                        input_items.append(
                            {
                                "type": "function_call",
                                "call_id": call_id_str,
                                "name": name.strip(),
                                "arguments": cls._normalize_arguments(arguments),
                            }
                        )
                raw_fn_call = message.get("function_call")
                if isinstance(raw_fn_call, dict) and not raw_tool_calls:
                    name = (
                        raw_fn_call.get("name")
                        or raw_fn_call.get("function_name")
                        or raw_fn_call.get("tool_name")
                    )
                    if isinstance(name, str) and name.strip():
                        call_id = (
                            message.get("tool_call_id")
                            or message.get("id")
                            or message.get("call_id")
                            or raw_fn_call.get("id")
                        )
                        call_id_str = (
                            str(call_id).strip()
                            if call_id and str(call_id).strip()
                            else f"call_{len(input_items)}"
                        )
                        arguments = raw_fn_call.get("arguments")
                        if arguments is None:
                            arguments = raw_fn_call.get("input") or raw_fn_call.get("parameters")
                        input_items.append(
                            {
                                "type": "function_call",
                                "call_id": call_id_str,
                                "name": name.strip(),
                                "arguments": cls._normalize_arguments(arguments),
                            }
                        )
                continue

            text = (
                content
                if isinstance(content, str)
                else (
                    cls._extract_text_from_content(content)
                    if isinstance(content, list)
                    else json.dumps(content, ensure_ascii=False)
                )
            )
            if not text.strip():
                continue
            input_items.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": text,
                }
            )
        instructions = "\n\n".join(part for part in instructions_parts if part).strip() or None
        return instructions, input_items

    @classmethod
    def _convert_tools_to_responses(cls, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate the shared chat-tool shape to the Responses API shape.

        DeepSpace stores tools in the OpenAI Chat Completions format so the
        same definitions can be sent to most providers. OpenCode's Responses
        endpoint flattens the function object; forwarding the nested shape
        makes the gateway reject the request with ``tools[0] missing name``.
        Invalid cached MCP entries are omitted rather than poisoning the whole
        turn.
        """

        converted: list[dict[str, Any]] = []
        for tool in tools:
            function = tool.get("function")
            source = function if isinstance(function, dict) else tool
            name = source.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            response_tool: dict[str, Any] = {
                "type": "function",
                "name": name.strip(),
            }
            for key in ("description", "parameters", "strict"):
                value = source.get(key)
                if value is not None:
                    response_tool[key] = value
            converted.append(response_tool)
        return converted

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
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens
        if instructions:
            payload["instructions"] = instructions
        if request.tools:
            payload["tools"] = cls._convert_tools_to_responses(request.tools)
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        if (
            request.reasoning_enabled
            and request.tool_choice != "required"
            and cls.model_supports_reasoning(request.model)
        ):
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
                headers=self._request_headers(request),
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
                        error_text = bytes(error_bytes).decode("utf-8", errors="replace")
                        try:
                            decoded = json.loads(error_text)
                        except json.JSONDecodeError:
                            decoded = None
                        if isinstance(decoded, dict):
                            error_payload = decoded
                    self._raise_provider_error(response, payload=error_payload, text=error_text)
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
                            delta = payload_obj.get("text") or payload_obj.get("summary")
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
                            item_id = item.get("id") or item.get("call_id") or item.get("item_id")
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

                    if "function_call_arguments.delta" in lowered or "arguments.delta" in lowered:
                        item_id = payload_obj.get("item_id") or payload_obj.get("call_id")
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
                                            "name": tool_call_name_by_id.get(item_id, ""),
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
                                    item.get("id") or item.get("call_id") or item.get("item_id")
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
                                    text = self._extract_text_from_content(item.get("content"))
                                if text.strip():
                                    yield {"type": "thinking", "text": text.strip()}
                            else:
                                text = self._extract_text_from_content(item.get("text"))
                                if not text.strip():
                                    text = self._extract_text_from_content(item.get("content"))
                                if text.strip():
                                    yield {"type": "delta", "text": text.strip()}
                        current_event = ""

    def _gpt_family_response(
        self, request: ChatGenerateRequest, *, base_url: str
    ) -> ChatGenerateResponse:
        httpx_module = self._httpx(request)
        is_free = self.is_free_model(request.model)
        # Free-tier models upstream reject stream=False with FreeTierError.
        # Streaming is mandatory for free models on OpenCode's Responses API.
        use_stream = is_free or bool(request.metadata.get("force_stream"))
        payload = self._build_responses_payload(request, stream=use_stream)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )

        if use_stream:
            content_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_call_order: list[str] = []
            tool_call_index_by_id: dict[str, int] = {}
            tool_call_name_by_id: dict[str, str] = {}
            tool_call_args_by_id: dict[str, list[str]] = {}
            usage: dict[str, Any] = {}

            with httpx_module.Client(timeout=timeout) as client:
                with client.stream(
                    "POST",
                    f"{base_url}/responses",
                    headers=self._request_headers(request),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        error_payload: dict[str, Any] | None = None
                        error_text: str | None = None
                        try:
                            error_bytes = response.read()
                            if isinstance(error_bytes, bytes | bytearray):
                                error_text = bytes(error_bytes).decode("utf-8", errors="replace")
                                decoded = json.loads(error_text)
                                if isinstance(decoded, dict):
                                    error_payload = decoded
                        except Exception:
                            pass
                        self._raise_provider_error(response, payload=error_payload, text=error_text)

                    current_event = ""
                    for raw_line in response.iter_lines():
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
                            break
                        try:
                            payload_obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        event_name = current_event or str(payload_obj.get("type") or "")
                        lowered = event_name.lower()

                        if "output_text.delta" in lowered or (
                            "output_text" in lowered and "delta" in lowered
                        ):
                            delta = payload_obj.get("delta")
                            if not isinstance(delta, str):
                                delta = payload_obj.get("text")
                            if isinstance(delta, str) and delta:
                                content_parts.append(delta)
                            current_event = ""
                            continue

                        if "reasoning" in lowered or "think" in lowered:
                            delta = payload_obj.get("delta")
                            if not isinstance(delta, str):
                                delta = payload_obj.get("text") or payload_obj.get("summary")
                            if isinstance(delta, str) and delta:
                                thinking_parts.append(delta)
                            current_event = ""
                            continue

                        if "output_item.added" in lowered or "item.added" in lowered:
                            item = payload_obj.get("item")
                            if not isinstance(item, dict):
                                item = payload_obj.get("output_item")
                            if isinstance(item, dict):
                                item_type = str(item.get("type") or "").lower()
                                if "function_call" in item_type or "tool_call" in item_type:
                                    item_id = (
                                        item.get("id") or item.get("call_id") or item.get("item_id")
                                    )
                                    if isinstance(item_id, str) and item_id.strip():
                                        if item_id not in tool_call_index_by_id:
                                            tool_call_index_by_id[item_id] = len(tool_call_order)
                                            tool_call_order.append(item_id)
                                            tool_call_args_by_id[item_id] = []
                                        fn_name = (
                                            item.get("name")
                                            or item.get("function_name")
                                            or item.get("tool_name")
                                        )
                                        if isinstance(fn_name, str) and fn_name.strip():
                                            tool_call_name_by_id[item_id] = fn_name.strip()
                            current_event = ""
                            continue

                        if (
                            "function_call_arguments.delta" in lowered
                            or "arguments.delta" in lowered
                        ):
                            item_id = payload_obj.get("item_id") or payload_obj.get("call_id")
                            if isinstance(item_id, str) and item_id in tool_call_args_by_id:
                                delta = payload_obj.get("delta")
                                if not isinstance(delta, str):
                                    delta = payload_obj.get("arguments")
                                if isinstance(delta, dict):
                                    delta = json.dumps(delta, ensure_ascii=False)
                                if isinstance(delta, str) and delta:
                                    tool_call_args_by_id[item_id].append(delta)
                            current_event = ""
                            continue

                        if "completed" in lowered or "done" in lowered:
                            resp_meta = payload_obj.get("response")
                            if isinstance(resp_meta, dict):
                                usage_meta = resp_meta.get("usage")
                                if isinstance(usage_meta, dict):
                                    usage = usage_meta

            tool_calls = []
            for item_id in tool_call_order:
                name = tool_call_name_by_id.get(item_id, "")
                args_str = "".join(tool_call_args_by_id.get(item_id, []))
                tool_calls.append(
                    {
                        "id": item_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": self._normalize_arguments(args_str or "{}"),
                        },
                    }
                )

            return ChatGenerateResponse(
                content="".join(content_parts),
                thinking_content="".join(thinking_parts).strip() or None,
                tool_calls=tool_calls if tool_calls else None,
                usage=usage,
            )

        with httpx_module.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url}/responses",
                headers=self._request_headers(request),
                json=payload,
            )
            if response.status_code >= 400:
                self._raise_provider_error(response)
            payload_obj = response.json()
            content = self._extract_response_text(payload_obj)
            thinking_content = self._extract_response_thinking(payload_obj)
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
        return family, OpenAICompatibleProvider(base_url=base_url, api_key=request.api_key)

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        base_url = self._resolve_base_url(request.base_url)
        family, provider = self._family_provider(request, base_url=base_url)
        if family == "responses":
            return self._gpt_family_response(request, base_url=base_url)
        if provider is None:
            raise ProviderCapabilityError("OpenCode Zen provider routing failed")
        headers = self._request_headers(request)
        api_key = (
            headers["Authorization"].split(" ", 1)[1]
            if "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
            else request.api_key
        )
        adapted_request = replace(
            request,
            api_key=api_key,
            base_url=base_url,
            metadata={
                **dict(request.metadata),
                "provider_type": self.provider_name,
                "extra_headers": {
                    **dict(request.metadata.get("extra_headers") or {}),
                    **headers,
                },
            },
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
            async for event in self._stream_responses_events(request, base_url=base_url):
                yield event
            return
        if provider is None:
            raise ProviderCapabilityError("OpenCode Zen provider routing failed")
        headers = self._request_headers(request)
        api_key = (
            headers["Authorization"].split(" ", 1)[1]
            if "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
            else request.api_key
        )
        adapted_request = replace(
            request,
            api_key=api_key,
            base_url=base_url,
            metadata={
                **dict(request.metadata),
                "provider_type": self.provider_name,
                "extra_headers": {
                    **dict(request.metadata.get("extra_headers") or {}),
                    **headers,
                },
            },
        )
        async for event in provider.stream_generate_events(adapted_request):
            yield event

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        base_url = self._resolve_base_url(request.base_url)
        family, provider = self._family_provider(request, base_url=base_url)
        headers = self._request_headers(request)
        api_key = (
            headers["Authorization"].split(" ", 1)[1]
            if "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
            else request.api_key
        )
        adapted_request = replace(
            request,
            api_key=api_key,
            base_url=base_url,
            metadata={
                **dict(request.metadata),
                "provider_type": self.provider_name,
                "extra_headers": {
                    **dict(request.metadata.get("extra_headers") or {}),
                    **headers,
                },
            },
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
        response = self._get_model_discovery_response(
            base_url=base_url,
            httpx_module=httpx_module,
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
            max_output_tokens = extract_max_output_tokens(item)
            verified_context_window = resolve_verified_context_window(
                model_name,
                provider_type=self.provider_name,
            )
            context_window = live_context_window or verified_context_window.context_window
            context_window_source = (
                "live_model" if live_context_window is not None else verified_context_window.source
            )
            infos.append(
                ProviderModelInfo(
                    name=model_name,
                    kind="chat",
                    context_window=context_window,
                    context_window_source=context_window_source,
                    max_output_tokens=max_output_tokens,
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
                        **(
                            {"max_output_tokens": max_output_tokens}
                            if max_output_tokens is not None
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
                        **reasoning_capabilities(self.provider_name, model_name, base_url=base_url),
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
