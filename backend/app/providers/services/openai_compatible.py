from __future__ import annotations

import importlib
import json
import math
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import replace
from typing import Any, cast
from urllib.parse import quote, urlsplit, urlunsplit

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.context_window import (
    extract_context_window,
    extract_max_output_tokens,
    resolve_verified_context_window,
)
from app.providers.services.image_inputs import image_data_url
from app.providers.services.openai_compatible_config import (
    OpenAICompatibleEndpointSettings,
    openai_compatible_settings,
    set_json_path,
)
from app.providers.services.reasoning_capabilities import (
    is_deepseek_v4_model,
    merge_reasoning_capabilities,
    model_supports_reasoning,
    supports_required_tool_choice,
    uses_deepseek_reasoning_protocol,
    uses_enable_thinking_controls,
    uses_gemma_think_trigger,
    uses_groq_reasoning_api,
    uses_slash_think_controls,
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
from app.providers.services.url_resolution import resolve_provider_base_url

_STREAM_USAGE_AUTO_PROVIDERS = frozenset(
    {
        "openai",
        "deepseek",
        "larprouter",
        "nvidia-nim",
        "mistral",
        "openrouter",
        "lmstudio",
        "vllm",
    }
)


class _UnsupportedStreamUsageOptionError(Exception):
    """Internal signal to retry a stream without optional usage metadata."""


class OpenAICompatibleProvider:
    provider_name = "openai-compatible"
    MAX_MODEL_LISTING_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        *,
        supports_embeddings: bool = False,
        base_url: str | None = None,
        api_key: str | None = None,
        provider_name: str | None = None,
        provider_metadata: dict[str, object] | None = None,
        model_listing_timeout_seconds: float = 8.0,
    ) -> None:
        # Registry-created instances use this to retain the concrete catalog
        # provider (Groq, OpenRouter, vLLM, custom, …) while sharing the
        # OpenAI-compatible transport and stream parser.
        self.provider_name = provider_name or type(self).provider_name
        self.supports_embeddings = supports_embeddings
        self.base_url = resolve_provider_base_url(base_url)
        self.api_key = api_key
        self.provider_metadata = dict(provider_metadata or {})
        self.model_listing_timeout_seconds = min(
            max(float(model_listing_timeout_seconds), 1.0),
            self.MAX_MODEL_LISTING_TIMEOUT_SECONDS,
        )
        self.endpoint_settings = openai_compatible_settings(
            self.provider_metadata, provider_type=self.provider_name
        )

    @property
    def supports_model_listing(self) -> bool:
        return self.endpoint_settings.models_path is not None

    def bind(self, base_url: str, api_key: str | None = None) -> OpenAICompatibleProvider:
        self.base_url = resolve_provider_base_url(base_url)
        self.api_key = api_key
        return self

    @staticmethod
    def _httpx(request: ChatGenerateRequest | None = None) -> Any:
        if request is not None:
            injected = request.metadata.get("httpx_module")
            if injected is not None:
                return injected
        return importlib.import_module("httpx")

    @staticmethod
    def _build_headers(
        api_key: str | None,
        extra_headers: dict[str, str] | None = None,
        *,
        settings: OpenAICompatibleEndpointSettings | None = None,
    ) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            header_name = settings.auth_header_name if settings else "Authorization"
            auth_value = (
                f"Bearer {api_key}"
                if settings is None or settings.auth_scheme == "bearer"
                else api_key
            )
            headers[header_name] = auth_value
        if extra_headers:
            headers.update(
                {
                    str(name): str(value)
                    for name, value in extra_headers.items()
                    if str(name).strip() and str(value).strip()
                }
            )
        return headers

    def _endpoint_url(
        self,
        base_url: str | None,
        path: str | None,
        *,
        model: str | None = None,
    ) -> str:
        resolved_base = resolve_provider_base_url(base_url)
        if not resolved_base:
            raise ProviderCapabilityError("provider request requires a configured base URL")
        if not path:
            raise ProviderCapabilityError("this OpenAI-compatible endpoint is disabled in settings")
        parsed = urlsplit(resolved_base)
        base_path = parsed.path.rstrip("/")
        # Accept a commonly pasted full endpoint URL without duplicating its
        # final route when using a different operation on the same API root.
        known_suffixes = {
            "/chat/completions",
            "/responses",
            "/embeddings",
            "/models",
            *(
                candidate
                for candidate in (
                    self.endpoint_settings.chat_completions_path,
                    self.endpoint_settings.responses_path,
                    self.endpoint_settings.models_path,
                    self.endpoint_settings.embeddings_path,
                )
                if candidate
            ),
        }
        for known_suffix in sorted(known_suffixes, key=len, reverse=True):
            if base_path.endswith(known_suffix):
                base_path = base_path[: -len(known_suffix)].rstrip("/")
                break
        route = path
        if model is not None and "{model}" in route:
            route = route.replace("{model}", quote(model, safe=""))
        joined_path = f"{base_path}/{route.lstrip('/')}" if base_path else route
        return urlunsplit((parsed.scheme, parsed.netloc, joined_path, parsed.query, ""))

    @staticmethod
    def _extract_context_window(item: dict[str, Any]) -> int | None:
        candidate_keys = (
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
        return extract_context_window(item, candidate_keys=candidate_keys)

    @staticmethod
    def _safe_model_metadata(item: dict[str, Any]) -> dict[str, Any]:
        """Keep useful vendor model metadata without persisting arbitrary payloads."""
        allowed = {
            "object",
            "owned_by",
            "created",
            "context_length",
            "context_window",
            "supports_image_in",
            "supports_image_input",
            "supportsImageIn",
            "supportsImageInput",
            "supports_vision",
            "supportsVision",
            "supports_video_in",
            "supports_reasoning",
            "reasoning_capabilities_known",
            "max_output_tokens",
            "supported_reasoning_efforts",
            "default_reasoning_effort",
            "reasoning_effort_values",
            "reasoning_visibility",
            "supports_thinking_summary_stream",
            "supports_thinking_toggle",
            "request_controls_on",
            "request_controls_off",
            "input_modalities",
            "inputModalities",
            "modalities",
            "output_modalities",
        }
        result: dict[str, Any] = {}
        for key in allowed:
            value = item.get(key)
            if isinstance(value, bool | int | float):
                result[key] = value
            elif isinstance(value, str) and len(value) <= 256:
                result[key] = value
            elif isinstance(value, list) and len(value) <= 32:
                safe_values = [
                    entry
                    for entry in value
                    if isinstance(entry, bool | int | float)
                    or (isinstance(entry, str) and len(entry) <= 128)
                    or (
                        isinstance(entry, dict)
                        and key == "reasoning_effort_values"
                        and len(entry) <= 16
                    )
                ]
                if safe_values:
                    result[key] = safe_values
        image_flag_keys = (
            "supports_image_in",
            "supports_vision",
            "supports_image_input",
            "supportsImageIn",
            "supportsVision",
            "supportsImageInput",
        )
        image_flag_sources = [item]
        for key in ("capabilities", "architecture", "model_capabilities"):
            nested = item.get(key)
            if isinstance(nested, dict):
                image_flag_sources.append(nested)
        explicit_image_support = next(
            (
                source[flag]
                for source in image_flag_sources
                for flag in image_flag_keys
                if isinstance(source.get(flag), bool)
            ),
            None,
        )
        if isinstance(explicit_image_support, bool):
            result.setdefault("supports_image_in", explicit_image_support)
        # Model catalogs such as OpenRouter put modality information under
        # ``architecture.input_modalities``. Normalize that common shape so
        # selection-time capability checks can use the cached model record
        # without making a probe request during a chat turn.
        raw_modalities = item.get("input_modalities")
        if not isinstance(raw_modalities, list) or not raw_modalities:
            raw_modalities = item.get("inputModalities")
        if not isinstance(raw_modalities, list) or not raw_modalities:
            raw_modalities = item.get("modalities")
        if not isinstance(raw_modalities, list) or not raw_modalities:
            architecture = item.get("architecture")
            if isinstance(architecture, dict):
                raw_modalities = (
                    architecture.get("input_modalities")
                    or architecture.get("inputModalities")
                    or architecture.get("modalities")
                )
        if not isinstance(raw_modalities, list) or not raw_modalities:
            capabilities = item.get("capabilities")
            if isinstance(capabilities, dict):
                raw_modalities = (
                    capabilities.get("input_modalities")
                    or capabilities.get("inputModalities")
                    or capabilities.get("modalities")
                )
        if not isinstance(raw_modalities, list) or not raw_modalities:
            model_capabilities = item.get("model_capabilities")
            if isinstance(model_capabilities, dict):
                raw_modalities = (
                    model_capabilities.get("input_modalities")
                    or model_capabilities.get("inputModalities")
                    or model_capabilities.get("modalities")
                )
        if isinstance(raw_modalities, list) and len(raw_modalities) <= 32:
            modalities: list[str] = []
            for entry in raw_modalities:
                value = entry
                if isinstance(entry, dict):
                    value = entry.get("type") or entry.get("modality") or entry.get("name")
                if isinstance(value, str) and len(value) <= 64:
                    normalized = value.strip().casefold()
                    if normalized and normalized not in modalities:
                        modalities.append(normalized)
            if modalities:
                result["input_modalities"] = modalities
                if not any(isinstance(result.get(flag), bool) for flag in image_flag_keys):
                    result["supports_image_in"] = any(
                        modality in {"image", "images", "vision"} for modality in modalities
                    )
        nested = item.get("capabilities")
        if isinstance(nested, dict):
            safe_nested: dict[str, Any] = {}
            for key, value in list(nested.items())[:32]:
                if isinstance(value, bool | int | float) or (
                    isinstance(value, str) and len(value) <= 256
                ):
                    safe_nested[str(key)[:64]] = value
                elif (
                    str(key)
                    in {
                        "supported_reasoning_efforts",
                        "supported_efforts",
                        "request_controls_on",
                        "request_controls_off",
                    }
                    and isinstance(value, list)
                    and len(value) <= 32
                ):
                    safe_nested[str(key)[:64]] = [
                        item for item in value if isinstance(item, str) and len(item) <= 128
                    ]
            if safe_nested:
                result["capabilities"] = safe_nested
        return result

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
        if not message:
            if isinstance(text, str) and text.strip():
                message = text.strip()
        return message

    @staticmethod
    def _unwrap_success_envelope(payload: Any, *, operation: str) -> Any:
        """Unwrap gateways that return successful results inside ``data``."""
        if not isinstance(payload, dict) or "success" not in payload:
            return payload
        if payload.get("success") is not True:
            raise RuntimeError(f"{operation} endpoint reported an unsuccessful response")
        if "data" not in payload:
            raise RuntimeError(f"{operation} endpoint returned a success envelope without data")
        return payload["data"]

    def _raise_provider_error(
        self,
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
            provider_name=self.provider_name,
            status_code=int(response.status_code),
            message=self._extract_provider_error_message(payload=payload, text=text),
        )

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        if self.endpoint_settings.api_mode == "responses":
            return self._generate_responses(request)
        httpx_module = self._httpx(request)
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or ""),
        )
        if not base_url:
            raise ProviderCapabilityError("provider request requires a configured base URL")
        messages = self._prepare_messages(request)
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
        }
        self._apply_common_generation_limits(payload, request)
        tools = unique_tool_definitions(request.tools)
        if tools:
            payload["tools"] = tools
        effective_tool_choice = self._effective_tool_choice(request)
        if effective_tool_choice:
            payload["tool_choice"] = effective_tool_choice

        self._apply_reasoning_request_settings(payload, request)
        response = httpx_module.post(
            self._endpoint_url(
                base_url, self.endpoint_settings.chat_completions_path, model=request.model
            ),
            headers=self._build_headers(
                request.api_key,
                request.metadata.get("extra_headers"),
                settings=self.endpoint_settings,
            ),
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj = self._unwrap_success_envelope(response.json(), operation="Chat Completions")
        if not isinstance(payload_obj, dict):
            raise RuntimeError("Chat Completions endpoint returned an invalid response object")
        if isinstance(payload_obj.get("error"), dict):
            self._raise_provider_error(response, payload=payload_obj)
        choices = payload_obj.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("provider response missing choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError("provider response contains an invalid choice")
        message = choice.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("provider response contains an invalid message")
        content = message.get("content", "")
        # Capture reasoning whenever the provider returns it. The request flag
        # controls provider-side generation settings, not response visibility.
        thinking_content = (
            self._extract_reasoning_text(message) if self._response_reasoning_is_visible() else None
        )
        content_text, content_thinking = self._split_text_and_reasoning(content)
        if content_text is not None:
            content = content_text
        elif isinstance(content, list) and content_thinking:
            content = ""
        if not thinking_content and self._response_reasoning_is_visible():
            thinking_content = content_thinking
        if content is None and isinstance(message.get("tool_calls"), list):
            content = ""
        if not isinstance(content, str):
            raise RuntimeError("provider response missing message content")
        if not thinking_content:
            extracted_thinking, extracted_content = self._extract_tagged_reasoning_content(
                content,
                enabled=(
                    self._reasoning_observation_enabled(request)
                    and self._response_reasoning_is_visible()
                ),
                model=request.model,
            )
            if extracted_content is not None:
                content = extracted_content
            if extracted_thinking:
                thinking_content = extracted_thinking
        usage = payload_obj.get("usage", {})
        tool_calls = message.get("tool_calls")

        return ChatGenerateResponse(
            content=content,
            thinking_content=thinking_content,
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            usage=usage if isinstance(usage, dict) else {},
        )

    def _apply_common_generation_limits(
        self, payload: dict[str, Any], request: ChatGenerateRequest
    ) -> None:
        if self.endpoint_settings.send_temperature:
            payload["temperature"] = request.temperature
        max_tokens_parameter = self.endpoint_settings.max_tokens_parameter or (
            "max_output_tokens" if self.endpoint_settings.api_mode == "responses" else "max_tokens"
        )
        if self.endpoint_settings.send_max_tokens and request.max_tokens is not None:
            payload[max_tokens_parameter] = request.max_tokens

    def _generate_responses(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        httpx_module = self._httpx(request)
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or ""),
        )
        payload = self._build_responses_payload(request, stream=False)
        response = httpx_module.post(
            self._endpoint_url(
                base_url, self.endpoint_settings.responses_path, model=request.model
            ),
            headers=self._build_headers(
                request.api_key,
                request.metadata.get("extra_headers"),
                settings=self.endpoint_settings,
            ),
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        response_payload = self._unwrap_success_envelope(response.json(), operation="Responses")
        if not isinstance(response_payload, dict):
            raise RuntimeError("Responses endpoint returned an invalid response object")
        return self._parse_responses_result(response_payload)

    def _build_responses_payload(
        self, request: ChatGenerateRequest, *, stream: bool
    ) -> dict[str, Any]:
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or self.provider_name),
        )
        if not base_url:
            raise ProviderCapabilityError("provider request requires a configured base URL")
        payload: dict[str, Any] = {
            "model": request.model,
            "input": self._chat_messages_to_responses_input(self._prepare_messages(request)),
        }
        if self.provider_name == "meta":
            # Use the stateless Responses mode. AverQel sends the conversation
            # history explicitly and does not need a vendor-stored response ID.
            payload["store"] = False
        if stream:
            payload["stream"] = True
        self._apply_common_generation_limits(payload, request)
        tools = unique_tool_definitions(request.tools)
        if tools:
            payload["tools"] = self._chat_tools_to_responses_tools(tools)
        effective_tool_choice = self._effective_tool_choice(request)
        if effective_tool_choice:
            payload["tool_choice"] = self._chat_tool_choice_to_responses(effective_tool_choice)
        self._apply_reasoning_request_settings(payload, request)
        return payload

    @classmethod
    def _chat_messages_to_responses_input(
        cls, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role == "tool":
                tool_call_id = message.get("tool_call_id")
                if isinstance(tool_call_id, str) and tool_call_id:
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call_id,
                            "output": cls._responses_text(content),
                        }
                    )
                continue
            if role not in {"system", "developer", "user", "assistant"}:
                continue
            tool_calls = message.get("tool_calls")
            if role == "assistant" and isinstance(tool_calls, list):
                if cls._responses_text(content).strip():
                    items.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": cls._responses_content(content, role="assistant"),
                        }
                    )
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    call_id = call.get("id")
                    name = function.get("name")
                    if not isinstance(call_id, str) or not isinstance(name, str):
                        continue
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": name,
                            "arguments": str(function.get("arguments") or "{}"),
                        }
                    )
                continue
            items.append(
                {
                    "type": "message",
                    "role": role,
                    "content": cls._responses_content(content, role=role),
                }
            )
        return items

    @staticmethod
    def _responses_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
        return ""

    @classmethod
    def _responses_content(cls, content: Any, *, role: str) -> str | list[dict[str, Any]]:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        converted: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind in {"text", "input_text", "output_text"} and isinstance(item.get("text"), str):
                converted.append(
                    {
                        "type": "output_text" if role == "assistant" else "input_text",
                        "text": item["text"],
                    }
                )
            elif kind in {"image_url", "input_image"}:
                image_url = item.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                if isinstance(image_url, str) and image_url:
                    converted.append({"type": "input_image", "image_url": image_url})
        return converted

    @staticmethod
    def _chat_tools_to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") != "function":
                converted.append(tool)
                continue
            function = tool.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                continue
            converted_tool = {
                "type": "function",
                "name": function["name"],
                "parameters": function.get("parameters", {"type": "object"}),
            }
            for key in ("description", "strict"):
                if key in function:
                    converted_tool[key] = function[key]
            converted.append(converted_tool)
        return converted

    @staticmethod
    def _chat_tool_choice_to_responses(
        choice: str | dict[str, Any],
    ) -> str | dict[str, Any]:
        if isinstance(choice, str):
            return choice
        if choice.get("type") == "function":
            function = choice.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                return {"type": "function", "name": function["name"]}
        return choice

    def _parse_responses_result(self, payload: dict[str, Any]) -> ChatGenerateResponse:
        if isinstance(payload.get("error"), dict):
            error = payload["error"]
            message = error.get("message")
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message=message if isinstance(message, str) else None,
            )
        if payload.get("status") == "failed":
            error = payload.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message=(
                    message
                    if isinstance(message, str)
                    else "Responses endpoint reported a failure."
                ),
            )
        output = payload.get("output")
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "message":
                    content = item.get("content")
                    if isinstance(content, str):
                        content_parts.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if not isinstance(part, dict):
                                continue
                            text = part.get("text")
                            if isinstance(text, str) and part.get("type") in {
                                "output_text",
                                "text",
                            }:
                                content_parts.append(text)
                            elif isinstance(text, str) and part.get("type") == "refusal":
                                content_parts.append(text)
                elif item_type == "function_call":
                    call_id = item.get("call_id") or item.get("id")
                    name = item.get("name")
                    if isinstance(call_id, str) and isinstance(name, str):
                        tool_calls.append(
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": str(item.get("arguments") or "{}"),
                                },
                            }
                        )
                elif (
                    item_type == "reasoning"
                    and self._response_reasoning_is_visible()
                    and self.endpoint_settings.reasoning.expose_response_reasoning
                ):
                    summary = item.get("summary")
                    if isinstance(summary, list):
                        thinking_parts.extend(
                            part["text"]
                            for part in summary
                            if isinstance(part, dict) and isinstance(part.get("text"), str)
                        )
        if not content_parts and isinstance(payload.get("output_text"), str):
            content_parts.append(payload["output_text"])
        return ChatGenerateResponse(
            content="".join(content_parts),
            thinking_content="".join(thinking_parts) or None,
            tool_calls=tool_calls or None,
            usage=self._normalize_responses_usage(payload.get("usage")),
        )

    @staticmethod
    def _normalize_responses_usage(usage: Any) -> dict[str, int]:
        if not isinstance(usage, dict):
            return {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        normalized: dict[str, int] = {}
        if isinstance(input_tokens, int):
            normalized["prompt_tokens"] = input_tokens
        if isinstance(output_tokens, int):
            normalized["completion_tokens"] = output_tokens
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            normalized["total_tokens"] = input_tokens + output_tokens
        return normalized

    async def _stream_responses_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        httpx_module = self._httpx(request)
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or self.provider_name),
        )
        payload = self._build_responses_payload(request, stream=True)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )
        async with httpx_module.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                self._endpoint_url(
                    base_url, self.endpoint_settings.responses_path, model=request.model
                ),
                headers=self._build_headers(
                    request.api_key,
                    request.metadata.get("extra_headers"),
                    settings=self.endpoint_settings,
                ),
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    error_bytes = await response.aread()
                    error_text = bytes(error_bytes).decode("utf-8", errors="replace")
                    try:
                        error_payload = json.loads(error_text)
                    except json.JSONDecodeError:
                        error_payload = None
                    self._raise_provider_error(
                        response,
                        payload=error_payload if isinstance(error_payload, dict) else None,
                        text=error_text,
                    )
                call_ids: dict[int, str] = {}
                call_names: dict[int, str] = {}
                accumulated_arguments: dict[int, str] = {}
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    for normalized in self._normalize_responses_stream_event(
                        event,
                        call_ids=call_ids,
                        call_names=call_names,
                        accumulated_arguments=accumulated_arguments,
                        request=request,
                    ):
                        yield normalized

    def _stream_responses_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        httpx_module = self._httpx(request)
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or self.provider_name),
        )
        payload = self._build_responses_payload(request, stream=True)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )
        with httpx_module.stream(
            "POST",
            self._endpoint_url(
                base_url, self.endpoint_settings.responses_path, model=request.model
            ),
            headers=self._build_headers(
                request.api_key,
                request.metadata.get("extra_headers"),
                settings=self.endpoint_settings,
            ),
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                self._raise_provider_error(response)
            call_ids: dict[int, str] = {}
            call_names: dict[int, str] = {}
            accumulated_arguments: dict[int, str] = {}
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                for normalized in self._normalize_responses_stream_event(
                    event,
                    call_ids=call_ids,
                    call_names=call_names,
                    accumulated_arguments=accumulated_arguments,
                    request=request,
                ):
                    if normalized.get("type") == "delta" and isinstance(
                        normalized.get("text"), str
                    ):
                        yield normalized["text"]

    def _normalize_responses_stream_event(
        self,
        event: dict[str, Any],
        *,
        call_ids: dict[int, str],
        call_names: dict[int, str],
        accumulated_arguments: dict[int, str],
        request: ChatGenerateRequest,
    ) -> list[dict[str, Any]]:
        event_type = event.get("type")
        if isinstance(event.get("error"), dict) and event_type not in {
            "error",
            "response.failed",
        }:
            error = event["error"]
            message = error.get("message")
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message=message if isinstance(message, str) else None,
            )
        if event_type in {"error", "response.failed"}:
            response = event.get("response")
            error = event.get("error")
            if isinstance(response, dict) and isinstance(response.get("error"), dict):
                error = response["error"]
            message = error.get("message") if isinstance(error, dict) else None
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message=(
                    message
                    if isinstance(message, str)
                    else "Responses endpoint reported a failure."
                ),
            )
        if event_type in {"response.output_text.delta", "response.refusal.delta"}:
            text = event.get("delta")
            return [{"type": "delta", "text": text}] if isinstance(text, str) and text else []
        if event_type in {"response.reasoning_summary_text.delta", "response.reasoning_text.delta"}:
            text = event.get("delta")
            if (
                isinstance(text, str)
                and text
                and self.endpoint_settings.reasoning.expose_response_reasoning
                and self._reasoning_observation_enabled(request)
            ):
                return [{"type": "thinking", "text": text}]
            return []
        if event_type == "response.output_item.added":
            item = event.get("item")
            output_index = event.get("output_index")
            if (
                not isinstance(item, dict)
                or item.get("type") != "function_call"
                or not isinstance(output_index, int)
            ):
                return []
            call_id = item.get("call_id") or item.get("id")
            name = item.get("name")
            if isinstance(call_id, str):
                call_ids[output_index] = call_id
            if isinstance(name, str):
                call_names[output_index] = name
            arguments = item.get("arguments")
            initial_arguments = arguments if isinstance(arguments, str) else ""
            accumulated_arguments[output_index] = initial_arguments
            return [
                {
                    "type": "tool_calls_delta",
                    "tool_calls": [
                        {
                            "index": output_index,
                            **({"id": call_ids[output_index]} if output_index in call_ids else {}),
                            "type": "function",
                            "function": {
                                **(
                                    {"name": call_names[output_index]}
                                    if output_index in call_names
                                    else {}
                                ),
                                "arguments": initial_arguments,
                            },
                        }
                    ],
                }
            ]
        if event_type == "response.function_call_arguments.delta":
            output_index = event.get("output_index")
            delta = event.get("delta")
            if not isinstance(output_index, int) or not isinstance(delta, str) or not delta:
                return []
            accumulated_arguments[output_index] = (
                accumulated_arguments.get(output_index, "") + delta
            )
            tool_call: dict[str, Any] = {
                "index": output_index,
                "function": {"arguments": delta},
            }
            if output_index in call_ids:
                tool_call["id"] = call_ids[output_index]
            if output_index in call_names:
                tool_call["function"]["name"] = call_names[output_index]
            return [{"type": "tool_calls_delta", "tool_calls": [tool_call]}]
        if event_type == "response.function_call_arguments.done":
            output_index = event.get("output_index")
            arguments = event.get("arguments")
            if not isinstance(output_index, int) or not isinstance(arguments, str):
                return []
            previous = accumulated_arguments.get(output_index, "")
            suffix = arguments[len(previous) :] if arguments.startswith(previous) else ""
            if not suffix:
                return []
            accumulated_arguments[output_index] = arguments
            tool_call = {
                "index": output_index,
                "function": {"arguments": suffix},
            }
            if output_index in call_ids:
                tool_call["id"] = call_ids[output_index]
            if output_index in call_names:
                tool_call["function"]["name"] = call_names[output_index]
            return [{"type": "tool_calls_delta", "tool_calls": [tool_call]}]
        if event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                return [
                    {
                        "type": "usage",
                        "usage": self._normalize_responses_usage(response["usage"]),
                    }
                ]
        return []

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event["type"] == "delta":
                text = event.get("text")
                if isinstance(text, str) and text:
                    yield text

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        if self.endpoint_settings.api_mode == "responses":
            async for event in self._stream_responses_events(request):
                yield event
            return
        httpx_module = self._httpx(request)
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or ""),
        )
        if not base_url:
            raise ProviderCapabilityError("provider request requires a configured base URL")
        messages = self._prepare_messages(request)
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        usage_policy = self.endpoint_settings.stream_usage
        usage_provider = (
            str(request.metadata.get("provider_type") or self.provider_name).strip().lower()
        )
        if usage_policy == "enabled" or (
            usage_policy == "auto" and usage_provider in _STREAM_USAGE_AUTO_PROVIDERS
        ):
            # Chat Completions providers that document this standard option
            # return exact completion-token usage in the final stream event.
            # Custom endpoints can opt in through validated provider metadata.
            payload["stream_options"] = {"include_usage": True}
        self._apply_common_generation_limits(payload, request)
        tools = unique_tool_definitions(request.tools)
        if tools:
            payload["tools"] = tools
        effective_tool_choice = self._effective_tool_choice(request)
        if effective_tool_choice:
            payload["tool_choice"] = effective_tool_choice
        self._apply_reasoning_request_settings(payload, request)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )
        async with httpx_module.AsyncClient(timeout=timeout) as client:
            try:
                async for event in self._stream_chat_completion_events(
                    client, request=request, base_url=base_url, payload=payload
                ):
                    yield event
            except _UnsupportedStreamUsageOptionError:
                # Some older or partially compatible OpenAI endpoints reject
                # stream_options. Retry only this explicit optional-parameter
                # rejection, before any stream event has been exposed.
                payload.pop("stream_options", None)
                async for event in self._stream_chat_completion_events(
                    client, request=request, base_url=base_url, payload=payload
                ):
                    yield event

    async def _stream_chat_completion_events(
        self,
        client: Any,
        *,
        request: ChatGenerateRequest,
        base_url: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        async with client.stream(
            "POST",
            self._endpoint_url(
                base_url, self.endpoint_settings.chat_completions_path, model=request.model
            ),
            headers=self._build_headers(
                request.api_key,
                request.metadata.get("extra_headers"),
                settings=self.endpoint_settings,
            ),
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
                diagnostic_text = error_text or json.dumps(error_payload or {})
                lowered_error = diagnostic_text.casefold()
                unsupported_markers = (
                    "unknown",
                    "unsupported",
                    "unrecognized",
                    "unexpected",
                    "not allowed",
                    "not permitted",
                    "extra inputs",
                    "invalid",
                )
                if (
                    "stream_options" in lowered_error
                    and response.status_code in {400, 422}
                    and any(marker in lowered_error for marker in unsupported_markers)
                ):
                    raise _UnsupportedStreamUsageOptionError
                self._raise_provider_error(response, payload=error_payload, text=error_text)
            stream_state = "answer"
            emitted_answer_text = ""
            emitted_thinking_text = ""
            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("error"), dict):
                    error = chunk["error"]
                    message = error.get("message")
                    raise ProviderRequestError(
                        provider_name=self.provider_name,
                        status_code=400,
                        message=message if isinstance(message, str) else None,
                    )
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    yield {"type": "usage", "usage": usage}
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = choice.get("delta", {})
                if not isinstance(delta, dict):
                    delta = {}
                continuation = delta.get("reasoning_content")
                if (
                    uses_deepseek_reasoning_protocol(
                        str(request.metadata.get("provider_type") or self.provider_name),
                        request.model,
                    )
                    and isinstance(continuation, str)
                    and continuation
                ):
                    # DeepSeek requires this exact opaque field on the next
                    # tool/clarification request. DeepSpace consumes this
                    # private event for encrypted replay; it is not exposed.
                    yield {
                        "type": "provider_continuation",
                        "reasoning_content": continuation,
                    }
                thinking = (
                    self._extract_reasoning_text(delta)
                    if self._response_reasoning_is_visible()
                    else None
                )
                if thinking:
                    thinking_delta = self._stream_text_suffix(emitted_thinking_text, thinking)
                    if thinking_delta:
                        emitted_thinking_text += thinking_delta
                        yield {"type": "thinking", "text": thinking_delta}
                content = self._extract_stream_text(choice=choice, delta=delta)
                if isinstance(content, str) and content:
                    parsed_events, stream_state = self._split_stream_content_for_reasoning(
                        content,
                        state=stream_state,
                        enabled=(
                            self._reasoning_observation_enabled(request)
                            and self._response_reasoning_is_visible()
                        ),
                        model=request.model,
                    )
                    for event_type, text in parsed_events:
                        if not text:
                            continue
                        if event_type == "thinking":
                            thinking_delta = self._stream_text_suffix(emitted_thinking_text, text)
                            if thinking_delta:
                                emitted_thinking_text += thinking_delta
                                yield {"type": event_type, "text": thinking_delta}
                            continue
                        if event_type == "delta":
                            answer_delta = self._stream_text_suffix(emitted_answer_text, text)
                            if answer_delta:
                                emitted_answer_text += answer_delta
                                yield {"type": event_type, "text": answer_delta}
                            continue
                        yield {"type": event_type, "text": text}

                tool_calls_delta = delta.get("tool_calls")
                if isinstance(tool_calls_delta, list):
                    yield {"type": "tool_calls_delta", "tool_calls": tool_calls_delta}

    @staticmethod
    def _stream_text_suffix(previous: str, incoming: str) -> str:
        """Normalize strict deltas and cumulative snapshots into one clean delta."""
        if not incoming:
            return ""
        if not previous:
            return incoming
        if incoming.startswith(previous):
            return incoming[len(previous) :]
        if previous.startswith(incoming):
            return ""

        max_overlap = min(len(previous), len(incoming))
        for size in range(max_overlap, 0, -1):
            if previous.endswith(incoming[:size]):
                return incoming[size:]
        return incoming

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        if self.endpoint_settings.api_mode == "responses":
            yield from self._stream_responses_sync(request)
            return
        httpx_module = self._httpx(request)
        base_url = resolve_provider_base_url(
            request.base_url,
            provider_type=str(request.metadata.get("provider_type") or ""),
        )
        if not base_url:
            raise ProviderCapabilityError("provider request requires a configured base URL")
        messages = self._prepare_messages(request)
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        self._apply_common_generation_limits(payload, request)
        tools = unique_tool_definitions(request.tools)
        if tools:
            payload["tools"] = tools
        effective_tool_choice = self._effective_tool_choice(request)
        if effective_tool_choice:
            payload["tool_choice"] = effective_tool_choice
        self._apply_reasoning_request_settings(payload, request)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )
        with httpx_module.stream(
            "POST",
            self._endpoint_url(
                base_url, self.endpoint_settings.chat_completions_path, model=request.model
            ),
            headers=self._build_headers(
                request.api_key,
                request.metadata.get("extra_headers"),
                settings=self.endpoint_settings,
            ),
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                error_payload: dict[str, Any] | None = None
                error_text: str | None = None
                try:
                    error_bytes = response.read()
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
            stream_state = "answer"
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("error"), dict):
                    error = chunk["error"]
                    message = error.get("message")
                    raise ProviderRequestError(
                        provider_name=self.provider_name,
                        status_code=400,
                        message=message if isinstance(message, str) else None,
                    )
                choices = chunk.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = choice.get("delta", {})
                if not isinstance(delta, dict):
                    delta = {}
                content = self._extract_stream_text(choice=choice, delta=delta)
                if isinstance(content, str) and content:
                    parsed_events, stream_state = self._split_stream_content_for_reasoning(
                        content,
                        state=stream_state,
                        enabled=(
                            self._reasoning_observation_enabled(request)
                            and self._response_reasoning_is_visible()
                        ),
                        model=request.model,
                    )
                    for event_type, text in parsed_events:
                        if event_type == "delta" and text:
                            yield text

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if self.endpoint_settings.models_path is None:
            raise ProviderCapabilityError("model discovery is disabled for this endpoint")
        if not self.base_url:
            raise ProviderCapabilityError("model listing requires a configured provider endpoint")
        data = self._fetch_model_listing_items()
        infos: list[ProviderModelInfo] = []
        for item in data:
            model_name = item.get("id") or item.get("name") or item.get("model")
            if not isinstance(model_name, str) or not model_name:
                continue
            if self.provider_name == "meta" and self._is_meta_non_chat_model(model_name):
                continue
            is_custom_chat_model = (
                self.provider_name == "custom" and not self._is_embedding_model_name(model_name)
            )
            if not is_custom_chat_model and not self._is_chat_model_name(model_name):
                continue
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
                    display_name=None,
                    capabilities={
                        **self._safe_model_metadata(item),
                        "object": item.get("object", "model"),
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
                        **self._reasoning_capabilities_for_model(item),
                    },
                )
            )
        return infos

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        if not self.supports_embeddings:
            raise ProviderCapabilityError(
                "embedding model listing requires an embedding-capable provider"
            )
        if not self.base_url:
            raise ProviderCapabilityError("model listing requires a configured provider endpoint")
        if self.endpoint_settings.models_path is None:
            raise ProviderCapabilityError("model discovery is disabled for this endpoint")
        data = self._fetch_model_listing_items()
        models: list[ProviderModelInfo] = []
        for item in data:
            model_name = item.get("id") or item.get("name") or item.get("model")
            if not isinstance(model_name, str) or not model_name:
                continue
            if not self._is_embedding_model_name(model_name):
                continue
            models.append(
                ProviderModelInfo(
                    name=model_name,
                    kind="embedding",
                    context_window=None,
                    capabilities={"object": item.get("object", "model")},
                    display_name=None,
                )
            )
        return [
            ProviderModelInfo(
                name=model.name,
                kind="embedding",
                context_window=model.context_window,
                capabilities=dict(model.capabilities),
                display_name=model.display_name,
            )
            for model in models
        ]

    def _fetch_model_listing_items(self) -> list[dict[str, Any]]:
        httpx_module = self._httpx()
        listing_api_key = None if self.provider_name == "cline" else self.api_key
        try:
            response = httpx_module.get(
                self._endpoint_url(self.base_url, self.endpoint_settings.models_path),
                headers=self._build_headers(listing_api_key, settings=self.endpoint_settings),
                timeout=self.model_listing_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            timeout_exception = getattr(httpx_module, "TimeoutException", None)
            if isinstance(timeout_exception, type) and isinstance(exc, timeout_exception):
                raise ProviderRequestError(
                    provider_name=self.provider_name,
                    status_code=504,
                    message="Provider model listing timed out.",
                ) from exc
            raise
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj = self._unwrap_success_envelope(response.json(), operation="Model listing")
        if isinstance(payload_obj, dict) and isinstance(payload_obj.get("error"), dict):
            self._raise_provider_error(response, payload=payload_obj)
        if isinstance(payload_obj, list):
            raw_items = payload_obj
        elif isinstance(payload_obj, dict):
            raw_items = payload_obj.get("data", payload_obj.get("models", []))
        else:
            raise RuntimeError("model listing response must be a JSON object or array")
        if not isinstance(raw_items, list):
            raise RuntimeError("model listing response must contain a model array")
        return [
            item if isinstance(item, dict) else {"id": item}
            for item in raw_items
            if isinstance(item, dict) or isinstance(item, str)
        ]

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def embed_many(self, request: EmbeddingRequest) -> EmbeddingResponse:
        if not self.supports_embeddings:
            raise ProviderCapabilityError("embeddings not supported by this provider adapter")
        httpx_module = self._httpx()
        base_url = resolve_provider_base_url(
            str(request.metadata.get("base_url") or ""),
            provider_type=request.provider_name,
        )
        if not base_url:
            raise ProviderCapabilityError("embedding request requires a configured base URL")
        if self.endpoint_settings.embeddings_path is None:
            raise ProviderCapabilityError("embeddings are disabled for this endpoint")
        payload: dict[str, Any] = {"model": request.model, "input": request.texts}
        if request.provider_name == "nvidia-nim" and request.input_type in {"query", "passage"}:
            if any(
                token in request.model.casefold()
                for token in ("embedqa", "nemoretriever", "nemotron-embed", "nv-embed-v")
            ):
                payload["input_type"] = request.input_type
        if self.endpoint_settings.send_embedding_dimensions:
            payload["dimensions"] = request.dimension
        response = httpx_module.post(
            self._endpoint_url(
                base_url, self.endpoint_settings.embeddings_path, model=request.model
            ),
            headers=self._build_headers(
                str(request.metadata.get("api_key") or "") or None,
                request.metadata.get("extra_headers"),
                settings=self.endpoint_settings,
            ),
            json=payload,
            timeout=float(request.timeout_seconds),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj = self._unwrap_success_envelope(response.json(), operation="Embedding")
        if not isinstance(payload_obj, dict):
            raise RuntimeError("embedding endpoint returned an invalid response object")
        if isinstance(payload_obj.get("error"), dict):
            self._raise_provider_error(response, payload=payload_obj)
        data = payload_obj.get("data")
        if not isinstance(data, list):
            raise RuntimeError("provider response missing embedding data")
        if len(data) != len(request.texts):
            raise RuntimeError("provider returned a different number of embeddings than requested")
        if all(isinstance(item, dict) and isinstance(item.get("index"), int) for item in data):
            data = sorted(data, key=lambda item: item["index"])
        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list):
                raise RuntimeError("provider response missing embedding vector")
            if any(
                isinstance(value, bool) or not isinstance(value, int | float) for value in embedding
            ):
                raise RuntimeError("provider returned a non-numeric embedding value")
            vector = [float(value) for value in embedding]
            if any(not math.isfinite(value) for value in vector):
                raise RuntimeError("provider returned a non-finite embedding value")
            if request.dimension > 0 and len(vector) != request.dimension:
                raise RuntimeError(
                    f"provider returned {len(vector)} embedding dimensions; "
                    f"AverQel expects {request.dimension}"
                )
            vectors.append(vector)
        return EmbeddingResponse(vectors=vectors)

    def health_check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            discovered = list(self.list_models())
            if not discovered and self.supports_embeddings:
                discovered = list(self.list_embedding_models())
            if self.provider_name == "cline" and discovered:
                return HealthCheckResult(
                    status="degraded",
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error_code="chat_access_not_verified",
                    error_message_redacted=(
                        "Cline's public model catalog is reachable; chat access was not probed."
                    ),
                    metadata={
                        "listing": "public_catalog",
                        "chat_probe": "not_run",
                        "model_count": len(discovered),
                    },
                )
            if not discovered:
                return HealthCheckResult(
                    status="degraded",
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error_code="provider_models_unavailable",
                    error_message_redacted="The endpoint returned no discoverable models.",
                    metadata={"listing": "empty", "chat_probe": "not_run"},
                )
        except ProviderCapabilityError:
            return HealthCheckResult(
                status="degraded",
                latency_ms=0,
                error_code="model_listing_unsupported",
                error_message_redacted=(
                    "Model discovery is disabled; chat connectivity was not probed."
                ),
                metadata={"listing": "unsupported", "chat_probe": "not_run"},
            )
        except Exception as exc:  # noqa: BLE001
            return HealthCheckResult(
                status="unhealthy",
                latency_ms=int((time.monotonic() - start) * 1000),
                error_code="provider_health_failed",
                error_message_redacted=str(exc),
            )
        return HealthCheckResult(
            status="healthy", latency_ms=int((time.monotonic() - start) * 1000)
        )

    def model_supports_reasoning(self, model_name: str) -> bool:
        if self.provider_name == "custom":
            return bool(self.endpoint_settings.reasoning.supported_efforts)
        return model_supports_reasoning(self.provider_name, model_name)

    def _reasoning_capabilities_for_model(self, model_info: dict[str, Any]) -> dict[str, Any]:
        if self.provider_name != "custom":
            return merge_reasoning_capabilities(
                self.provider_name,
                str(model_info.get("id") or ""),
                base_url=self.base_url,
                advertised=model_info,
            )
        configured = self.endpoint_settings.reasoning
        advertised_efforts = self._advertised_reasoning_efforts(model_info)
        efforts = [
            effort
            for effort in configured.supported_efforts
            if effort in configured.effort_values
            and (advertised_efforts is None or effort in advertised_efforts)
        ]
        if not configured.effort_parameter:
            efforts = []
        return {
            "supports_reasoning": bool(efforts or configured.toggle_parameter),
            "reasoning_capabilities_known": True,
            "reasoning_visibility": "provider_exposed" if efforts else "hidden",
            "supports_thinking_summary_stream": bool(efforts)
            and configured.expose_response_reasoning,
            "supported_reasoning_efforts": efforts,
            "supports_thinking_toggle": bool(
                configured.toggle_parameter or configured.effort_off_value is not None
            ),
            "request_controls_on": (
                [configured.effort_parameter] if configured.effort_parameter else []
            )
            + ([configured.toggle_parameter] if configured.toggle_parameter else []),
            "request_controls_off": (
                [configured.toggle_parameter] if configured.toggle_parameter else []
            )
            + ([configured.effort_parameter] if configured.effort_off_value is not None else []),
            "response_formats": (
                ["reasoning_content"] if configured.expose_response_reasoning else []
            ),
        }

    @staticmethod
    def _advertised_reasoning_efforts(model_info: dict[str, Any]) -> list[str] | None:
        capabilities = merge_reasoning_capabilities(
            "openai-compatible",
            str(model_info.get("id") or ""),
            advertised=model_info,
        )
        if capabilities.get("reasoning_capabilities_known") is not True:
            return None
        efforts = capabilities.get("supported_reasoning_efforts")
        return list(efforts) if isinstance(efforts, list) else []

    def _response_reasoning_is_visible(self) -> bool:
        if self.provider_name == "meta":
            return False
        return (
            self.provider_name != "custom"
            or self.endpoint_settings.reasoning.expose_response_reasoning
        )

    @staticmethod
    def _extract_reasoning_text(payload: dict[str, Any]) -> str | None:
        candidates = (
            payload.get("reasoning_content"),
            payload.get("reasoning"),
            payload.get("thinking"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
            if isinstance(candidate, list):
                parts = [
                    item.get("text", "")
                    for item in candidate
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ]
                text = "".join(parts).strip()
                if text:
                    return text
        _, content_reasoning = OpenAICompatibleProvider._split_text_and_reasoning(
            payload.get("content")
        )
        if content_reasoning and content_reasoning.strip():
            return content_reasoning
        return None

    @classmethod
    def _extract_stream_text(cls, *, choice: dict[str, Any], delta: dict[str, Any]) -> str | None:
        direct_candidates = (
            delta.get("content"),
            delta.get("text"),
            choice.get("text"),
        )
        for candidate in direct_candidates:
            normalized = cls._normalize_text_candidate(candidate)
            if normalized:
                return normalized

        message = choice.get("message")
        if isinstance(message, dict):
            normalized = cls._normalize_text_candidate(message.get("content"))
            if normalized:
                return normalized

        return None

    @staticmethod
    def _normalize_text_candidate(candidate: Any) -> str | None:
        text, _ = OpenAICompatibleProvider._split_text_and_reasoning(candidate)
        return text

    @staticmethod
    def _split_text_and_reasoning(candidate: Any) -> tuple[str | None, str | None]:
        """Separate typed reasoning blocks from user-facing text blocks."""
        if isinstance(candidate, str):
            return candidate or None, None
        if isinstance(candidate, list):
            text_parts: list[str] = []
            reasoning_parts: list[str] = []
            for item in candidate:
                if isinstance(item, str):
                    text_parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                block_type = str(item.get("type") or "").lower()
                reasoning_value = item.get("thinking", item.get("reasoning"))
                if reasoning_value is None and block_type in {"thinking", "reasoning"}:
                    reasoning_value = item.get("text", item.get("content"))
                if isinstance(reasoning_value, str):
                    reasoning_parts.append(reasoning_value)
                elif isinstance(reasoning_value, list):
                    nested_reasoning, _ = OpenAICompatibleProvider._split_text_and_reasoning(
                        reasoning_value
                    )
                    if nested_reasoning:
                        reasoning_parts.append(nested_reasoning)
                if block_type not in {"thinking", "reasoning"}:
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        text_parts.append(text_value)
                    nested_text = item.get("content")
                    if isinstance(nested_text, str):
                        text_parts.append(nested_text)
            text = "".join(text_parts)
            reasoning = "".join(reasoning_parts)
            return text or None, reasoning or None
        return None, None

    def _prepare_messages(self, request: ChatGenerateRequest) -> list[dict[str, Any]]:
        messages = [dict(message) for message in request.messages]
        if not messages:
            return messages
        reasoning_enabled = self._reasoning_enabled_for_request(request)
        if (
            self._uses_slash_think_controls(request)
            and request.metadata.get("reasoning_mode") != "auto"
        ):
            command = "/think" if reasoning_enabled else "/no_think"
            for index in range(len(messages) - 1, -1, -1):
                if messages[index].get("role") != "user":
                    continue

                content = str(messages[index].get("content", ""))
                normalized = self._strip_slash_think_commands(content).strip()
                final_text = f"{command}\n{normalized}".strip() if normalized else command

                if request.images:
                    # Convert content to list format for multimodal
                    multimodal_content: list[dict[str, Any]] = [
                        {"type": "text", "text": final_text},
                    ]
                    for img_b64 in request.images:
                        multimodal_content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": self._image_input_url(img_b64)},
                            }
                        )
                    messages[index]["content"] = cast(Any, multimodal_content)
                else:
                    messages[index]["content"] = final_text
                break
        elif request.images:
            # DeepSpace may attach an image after a tool call even when the
            # selected model does not use slash-think controls. Keep this
            # provider-local and additive: requests without images are
            # unchanged.
            for index in range(len(messages) - 1, -1, -1):
                if messages[index].get("role") != "user":
                    continue
                content = messages[index].get("content", "")
                text = content if isinstance(content, str) else str(content)
                messages[index]["content"] = [
                    {"type": "text", "text": text},
                    *[
                        {
                            "type": "image_url",
                            "image_url": {"url": self._image_input_url(img_b64)},
                        }
                        for img_b64 in request.images
                    ],
                ]
                break
        if reasoning_enabled == request.reasoning_enabled:
            return self._prepare_gemma_thinking(messages, request)
        return self._prepare_gemma_thinking(
            messages, replace(request, reasoning_enabled=reasoning_enabled)
        )

    @staticmethod
    def _image_input_url(image: str) -> str:
        if image.startswith("https://"):
            return image
        try:
            return image_data_url(image)
        except ValueError as exc:
            raise ProviderCapabilityError(str(exc)) from exc

    def _reasoning_enabled_for_request(self, request: ChatGenerateRequest) -> bool:
        """Avoid an unsupported forced-tool/reasoning combination.

        Some upstream OpenAI-compatible gateways reject
        ``tool_choice=required`` when reasoning controls are present. Tool
        execution remains required; only provider-side reasoning controls are
        omitted for that planning round. Any reasoning or thinking events
        emitted naturally are still parsed.
        """
        provider_type = str(request.metadata.get("provider_type") or self.provider_name).lower()
        if request.tool_choice == "required":
            if provider_type == "larprouter" and model_supports_reasoning(
                provider_type, request.model
            ):
                return request.reasoning_enabled
            if provider_type == "ollama":
                return request.reasoning_enabled
            capabilities = request.metadata.get("model_reasoning_capabilities")
            if not (
                provider_type == "lmstudio"
                and isinstance(capabilities, dict)
                and capabilities.get("reasoning_capabilities_known") is True
                and capabilities.get("supports_reasoning") is True
                and capabilities.get("request_controls_on")
            ):
                return False
        return request.reasoning_enabled

    @staticmethod
    def _reasoning_observation_enabled(request: ChatGenerateRequest) -> bool:
        """Observe provider-emitted reasoning without forcing request controls."""
        return bool(request.reasoning_enabled or request.metadata.get("reasoning_mode") == "auto")

    @staticmethod
    def _effective_tool_choice(
        request: ChatGenerateRequest,
    ) -> str | dict[str, Any] | None:
        choice = request.tool_choice
        if is_deepseek_v4_model(
            request.model
        ) and OpenAICompatibleProvider._reasoning_observation_enabled(request):
            # DeepSeek V4 rejects tool_choice while thinking is on; omitting it
            # leaves the advertised tool list available to the model.
            return None
        if choice == "required" and not supports_required_tool_choice(
            str(request.metadata.get("provider_type") or ""), request.model
        ):
            # DeepSeek V4 rejects forced choice in its always-thinking mode;
            # keep the tools available and let the model select them.
            return "auto"
        return choice

    def _prepare_gemma_thinking(
        self,
        messages: list[dict[str, Any]],
        request: ChatGenerateRequest,
    ) -> list[dict[str, Any]]:
        provider_type = str(request.metadata.get("provider_type") or self.provider_name).lower()
        if (
            not request.reasoning_enabled
            or provider_type in {"custom", "openai-compatible"}
            or not uses_gemma_think_trigger(request.model)
        ):
            return messages
        prepared = [dict(message) for message in messages]
        for message in prepared:
            if message.get("role") != "system":
                continue
            content = str(message.get("content") or "")
            if "<|think|>" in content:
                return prepared
            message["content"] = f"<|think|>\n{content}".strip() if content.strip() else "<|think|>"
            return prepared
        prepared.insert(0, {"role": "system", "content": "<|think|>"})
        return prepared

    @staticmethod
    def _strip_slash_think_commands(content: str) -> str:
        lines = [line for line in content.splitlines() if line.strip()]
        filtered_lines = [line for line in lines if line.strip() not in {"/think", "/no_think"}]
        return "\n".join(filtered_lines)

    def _apply_reasoning_request_settings(
        self, payload: dict[str, Any], request: ChatGenerateRequest
    ) -> None:
        reasoning_enabled = self._reasoning_enabled_for_request(request)
        if request.metadata.get("reasoning_mode") == "auto" and not reasoning_enabled:
            # Auto mode observes provider-emitted reasoning without sending a
            # provider-specific enable/disable switch. This preserves model
            # defaults and avoids forcing unsupported thinking combinations.
            return
        model_capabilities = request.metadata.get("model_reasoning_capabilities")
        if (
            isinstance(model_capabilities, dict)
            and model_capabilities.get("reasoning_capabilities_known") is True
            and model_capabilities.get("supports_reasoning") is not True
        ):
            return
        if self.provider_name == "custom":
            self._apply_custom_reasoning_settings(payload, request, enabled=reasoning_enabled)
            return
        provider_type = str(request.metadata.get("provider_type") or self.provider_name).lower()
        if provider_type == "larprouter":
            self._apply_discovered_reasoning_settings(
                payload,
                request,
                reasoning_enabled=reasoning_enabled,
            )
            return
        if provider_type == "nvidia-nim":
            lowered_model = request.model.casefold().replace("_", "-")
            # Nemotron's NIM API documents reasoning together with tool calls;
            # retain the user's choice when the generic tool guard suppresses
            # reasoning fields for less capable compatible gateways.
            reasoning_enabled = request.reasoning_enabled
            if "nemotron-3-ultra" in lowered_model:
                payload["reasoning_effort"] = (
                    "none"
                    if not reasoning_enabled
                    else {"medium": "medium", "high": "high"}.get(
                        request.reasoning_effort or "high", "high"
                    )
                )
            elif "nemotron-3-super" in lowered_model:
                payload["reasoning_effort"] = (
                    "none"
                    if not reasoning_enabled
                    else {"low": "low", "high": "high"}.get(
                        request.reasoning_effort or "high", "high"
                    )
                )
            elif "nemotron-3-nano-30b-a3b" in lowered_model:
                set_json_path(
                    payload,
                    "chat_template_kwargs.enable_thinking",
                    bool(reasoning_enabled),
                )
            else:
                self._apply_discovered_reasoning_settings(
                    payload,
                    request,
                    reasoning_enabled=reasoning_enabled,
                )
            return
        if provider_type == "moonshot":
            lowered_model = request.model.casefold()
            if "kimi-k3" in lowered_model:
                if reasoning_enabled:
                    payload["reasoning_effort"] = {
                        "low": "low",
                        "medium": "high",
                        "high": "high",
                        "very_high": "max",
                        "extreme_high": "max",
                    }.get(request.reasoning_effort or "extreme_high", "max")
                # K3 always reasons. Omitting this field preserves its default
                # when AverQel's reasoning switch is off.
                return
            if "kimi-k2.7-code" in lowered_model:
                # K2.7-Code cannot disable thinking and rejects a disable value.
                return
            if "kimi-k2.6" in lowered_model:
                payload["thinking"] = {"type": "enabled" if reasoning_enabled else "disabled"}
                return
            self._apply_discovered_reasoning_settings(
                payload,
                request,
                reasoning_enabled=reasoning_enabled,
            )
            return
        if provider_type == "zai":
            lowered_model = request.model.casefold()
            if "glm-5.3" in lowered_model:
                if reasoning_enabled:
                    payload["reasoning_effort"] = {
                        "low": "low",
                        "medium": "high",
                        "high": "high",
                        "very_high": "max",
                        "extreme_high": "max",
                    }.get(request.reasoning_effort or "extreme_high", "max")
                # GLM-5.3 has no thinking toggle and always reasons.
                return
            if "glm-5.2" in lowered_model:
                if reasoning_enabled:
                    payload["thinking"] = {"type": "enabled"}
                    payload["reasoning_effort"] = {
                        "low": "low",
                        "medium": "medium",
                        "high": "high",
                        "very_high": "xhigh",
                        "extreme_high": "max",
                    }.get(request.reasoning_effort or "medium", "medium")
                else:
                    payload["thinking"] = {"type": "disabled"}
                    payload["reasoning_effort"] = "none"
                return
            if any(
                token in lowered_model
                for token in ("glm-5.1", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5")
            ):
                payload["thinking"] = {"type": "enabled" if reasoning_enabled else "disabled"}
                return
            self._apply_discovered_reasoning_settings(
                payload,
                request,
                reasoning_enabled=reasoning_enabled,
            )
            return
        if provider_type in {"mistral", "meta"} and not self.model_supports_reasoning(
            request.model
        ):
            self._apply_discovered_reasoning_settings(
                payload,
                request,
                reasoning_enabled=reasoning_enabled,
            )
            return
        if provider_type == "mistral":
            is_zai = "zai-glm-5-3" in request.model.casefold()
            if reasoning_enabled:
                if is_zai:
                    payload["reasoning_effort"] = {
                        "low": "low",
                        "high": "high",
                        "extreme_high": "max",
                    }.get(request.reasoning_effort or "low", "low")
                else:
                    payload["reasoning_effort"] = {
                        "low": "low",
                        "medium": "medium",
                        "high": "high",
                        "very_high": "xhigh",
                        "extreme_high": "xhigh",
                    }.get(request.reasoning_effort or "medium", "medium")
            else:
                if is_zai:
                    payload.pop("reasoning_effort", None)
                else:
                    payload["reasoning_effort"] = "none"
            return
        if provider_type == "meta":
            # Meta's Muse Spark API accepts reasoning_effort but documents no
            # "none" value. Omit the field when the user selects Off.
            if reasoning_enabled:
                effort = {
                    "low": "low",
                    "medium": "medium",
                    "high": "high",
                    "very_high": "xhigh",
                    "extreme_high": (
                        "xhigh"
                        if "contributor" in request.model.casefold()
                        or "muse-spark-1.3" not in request.model.casefold()
                        else "max"
                    ),
                }.get(request.reasoning_effort or "medium", "medium")
                if self.endpoint_settings.api_mode == "responses":
                    set_json_path(payload, "reasoning.effort", effort)
                else:
                    payload["reasoning_effort"] = effort
            return
        if self._uses_groq_reasoning_api(request):
            if reasoning_enabled:
                payload["reasoning_effort"] = request.reasoning_effort or "medium"
                payload["include_reasoning"] = True
            else:
                payload["include_reasoning"] = False
                payload.pop("reasoning_effort", None)
            return
        if str(request.metadata.get("provider_type") or "").lower() == "deepseek":
            if reasoning_enabled:
                deepseek_effort = {
                    "low": "low",
                    "medium": "high",
                    "high": "high",
                    "very_high": "max",
                    "extreme_high": "max",
                }.get(request.reasoning_effort or "medium", "high")
                payload["thinking"] = {"type": "enabled"}
                payload["reasoning_effort"] = deepseek_effort
            else:
                payload["thinking"] = {"type": "disabled"}
                payload["reasoning_effort"] = "none"
            return
        if str(request.metadata.get("provider_type") or "").lower() == "lmstudio":
            model_capabilities = request.metadata.get("model_reasoning_capabilities")
            if (
                isinstance(model_capabilities, dict)
                and model_capabilities.get("reasoning_capabilities_known") is True
                and model_capabilities.get("request_controls_on")
            ):
                self._apply_discovered_reasoning_settings(
                    payload,
                    request,
                    reasoning_enabled=reasoning_enabled,
                )
                return
            payload["reasoning"] = (
                request.reasoning_effort or "medium" if reasoning_enabled else "off"
            )
            if self._uses_enable_thinking_controls(request):
                payload["enable_thinking"] = bool(reasoning_enabled)
                if reasoning_enabled:
                    payload["reasoning_effort"] = request.reasoning_effort or "medium"
                else:
                    payload.pop("reasoning_effort", None)
            return
        if not self.model_supports_reasoning(request.model):
            self._apply_discovered_reasoning_settings(
                payload,
                request,
                reasoning_enabled=reasoning_enabled,
            )
            return
        if self._uses_enable_thinking_controls(request):
            payload["enable_thinking"] = bool(reasoning_enabled)
            if reasoning_enabled:
                payload["reasoning_effort"] = request.reasoning_effort or "medium"
            else:
                payload.pop("reasoning_effort", None)
        if not reasoning_enabled:
            return
        payload["reasoning"] = {"effort": request.reasoning_effort or "medium"}

    def _apply_discovered_reasoning_settings(
        self,
        payload: dict[str, Any],
        request: ChatGenerateRequest,
        *,
        reasoning_enabled: bool,
    ) -> None:
        """Apply provider-advertised controls for models without a name profile."""
        capabilities = request.metadata.get("model_reasoning_capabilities")
        if not isinstance(capabilities, dict):
            return
        provider_type = str(request.metadata.get("provider_type") or self.provider_name).lower()
        if (
            request.tool_choice == "required"
            and provider_type not in {"ollama", "lmstudio"}
            and not (
                provider_type == "larprouter"
                and model_supports_reasoning(provider_type, request.model)
            )
        ):
            return
        if capabilities.get("reasoning_capabilities_known") is not True:
            return
        if capabilities.get("supports_reasoning") is not True:
            return

        raw_efforts = capabilities.get("supported_reasoning_efforts")
        efforts = (
            [item for item in raw_efforts if isinstance(item, str)]
            if isinstance(raw_efforts, list)
            else []
        )
        raw_values = capabilities.get("reasoning_effort_values")
        effort_values = raw_values if isinstance(raw_values, dict) else {}
        controls_key = "request_controls_on" if reasoning_enabled else "request_controls_off"
        raw_controls = capabilities.get(controls_key)
        controls = (
            {item for item in raw_controls if isinstance(item, str)}
            if isinstance(raw_controls, list)
            else set()
        )
        if not controls and reasoning_enabled and efforts:
            # The catalog gives us exact supported levels but some OpenAI-style
            # catalogs omit the field name. Use only the documented dialects
            # whose provider adapter owns this mapping.
            if provider_type in {
                "openai",
                "nvidia-nim",
                "groq",
                "groq-openai-compatible",
                "lmstudio",
                "mistral",
                "moonshot",
                "zai",
            }:
                controls = {"reasoning_effort"}
                if provider_type in {"groq", "groq-openai-compatible"}:
                    controls.add("include_reasoning")
            elif provider_type == "openrouter":
                controls = {"reasoning"}
            elif provider_type == "meta":
                controls = (
                    {"reasoning"}
                    if self.endpoint_settings.api_mode == "responses"
                    else {"reasoning_effort"}
                )
        if (
            not reasoning_enabled
            and not controls
            and capabilities.get("supports_thinking_toggle") is True
        ):
            if provider_type in {"openai", "nvidia-nim", "mistral", "moonshot", "zai"}:
                controls = {"reasoning_effort_none"}
                if provider_type in {"moonshot", "zai"}:
                    controls.add("thinking_disabled")
            elif provider_type == "lmstudio":
                controls = {"reasoning_effort_none"}
            elif provider_type in {"groq", "groq-openai-compatible"}:
                controls = {"include_reasoning_false"}

        if reasoning_enabled:
            effort = request.reasoning_effort
            if efforts and effort not in efforts:
                return
            if not effort and efforts:
                effort = efforts[0]
            native_effort = effort_values.get(effort, effort) if effort else None
            if "reasoning_effort" in controls and native_effort:
                payload["reasoning_effort"] = native_effort
            if "reasoning" in controls and native_effort:
                set_json_path(payload, "reasoning.effort", native_effort)
            if "thinking_enabled" in controls:
                payload["thinking"] = {"type": "enabled"}
            if "enable_thinking_true" in controls:
                payload["enable_thinking"] = True
            if "include_reasoning" in controls:
                payload["include_reasoning"] = True
            return

        if "reasoning_effort_none" in controls:
            payload["reasoning_effort"] = effort_values.get("off", "none")
        if "enable_thinking_false" in controls:
            payload["enable_thinking"] = False
        if "thinking_disabled" in controls:
            payload["thinking"] = {"type": "disabled"}
        if "include_reasoning_false" in controls:
            payload["include_reasoning"] = False
        if "omit_reasoning_effort" in controls:
            payload.pop("reasoning_effort", None)

    def _apply_custom_reasoning_settings(
        self,
        payload: dict[str, Any],
        request: ChatGenerateRequest,
        *,
        enabled: bool,
    ) -> None:
        settings = self.endpoint_settings.reasoning
        if enabled:
            effort = request.reasoning_effort
            if (
                settings.effort_parameter
                and effort in settings.supported_efforts
                and effort in settings.effort_values
            ):
                set_json_path(payload, settings.effort_parameter, settings.effort_values[effort])
            if settings.toggle_parameter:
                set_json_path(payload, settings.toggle_parameter, settings.toggle_enabled_value)
            return
        if settings.toggle_parameter:
            set_json_path(payload, settings.toggle_parameter, settings.toggle_disabled_value)
        if settings.effort_parameter and settings.effort_off_value is not None:
            set_json_path(payload, settings.effort_parameter, settings.effort_off_value)

    @staticmethod
    def _uses_groq_reasoning_api(request: ChatGenerateRequest) -> bool:
        return uses_groq_reasoning_api(
            str(request.metadata.get("provider_type") or ""),
            request.model,
            base_url=request.base_url,
        )

    def _uses_slash_think_controls(self, request: ChatGenerateRequest) -> bool:
        return uses_slash_think_controls(
            str(request.metadata.get("provider_type") or self.provider_name),
            request.model,
        )

    @classmethod
    def _uses_enable_thinking_controls(cls, request: ChatGenerateRequest) -> bool:
        return uses_enable_thinking_controls(
            str(request.metadata.get("provider_type") or cls.provider_name),
            request.model,
        )

    @classmethod
    def _extract_tagged_reasoning_content(
        cls,
        content: str,
        *,
        enabled: bool,
        model: str | None = None,
    ) -> tuple[str | None, str | None]:
        if (
            "<think>" not in content
            and "</think>" not in content
            and not cls._contains_gemma_channel_reasoning(content)
        ):
            return None, None
        state = "answer"
        parsed_events, _ = cls._split_stream_content_for_reasoning(
            content,
            state=state,
            enabled=enabled,
            model=model,
        )
        answer_parts: list[str] = []
        thinking_parts: list[str] = []
        for event_type, text in parsed_events:
            if event_type == "thinking":
                thinking_parts.append(text)
            elif event_type == "delta":
                answer_parts.append(text)
        answer = "".join(answer_parts).strip()
        thinking = "".join(thinking_parts).strip() or None
        return thinking, answer

    _GEMMA_CHANNEL_THOUGHT = "<|channel>thought"
    _GEMMA_CHANNEL_END = "<channel|>"

    @classmethod
    def _contains_gemma_channel_reasoning(cls, content: str) -> bool:
        return cls._GEMMA_CHANNEL_THOUGHT in content or cls._GEMMA_CHANNEL_END in content

    @classmethod
    def _split_stream_content_for_reasoning(
        cls,
        content: str,
        *,
        state: str,
        enabled: bool,
        model: str | None = None,
    ) -> tuple[list[tuple[str, str]], str]:
        if state == "gemma_thought" or cls._contains_gemma_channel_reasoning(content):
            return cls._split_gemma_channel_content(
                content,
                state=state,
                enabled=enabled,
            )
        return cls._split_stream_content_by_reasoning_tags(
            content,
            state=state,
            enabled=enabled,
        )

    @classmethod
    def _split_gemma_channel_content(
        cls,
        content: str,
        *,
        state: str,
        enabled: bool,
    ) -> tuple[list[tuple[str, str]], str]:
        if state == "answer" and not cls._contains_gemma_channel_reasoning(content):
            return ([("delta", content)] if content else []), state

        events: list[tuple[str, str]] = []
        cursor = 0
        mode = state if state in {"answer", "gemma_thought"} else "answer"
        while cursor < len(content):
            if mode == "answer":
                start = content.find(cls._GEMMA_CHANNEL_THOUGHT, cursor)
                if start == -1:
                    remaining = content[cursor:]
                    if remaining:
                        events.append(("delta", remaining))
                    break
                answer_text = content[cursor:start]
                if answer_text:
                    events.append(("delta", answer_text))
                cursor = start + len(cls._GEMMA_CHANNEL_THOUGHT)
                if cursor < len(content) and content[cursor] == "\n":
                    cursor += 1
                mode = "gemma_thought"
                continue

            end = content.find(cls._GEMMA_CHANNEL_END, cursor)
            if end == -1:
                reasoning_text = content[cursor:]
                if reasoning_text:
                    events.append(("thinking", reasoning_text))
                cursor = len(content)
                break
            reasoning_text = content[cursor:end]
            if reasoning_text:
                events.append(("thinking", reasoning_text.rstrip()))
            cursor = end + len(cls._GEMMA_CHANNEL_END)
            if cursor < len(content) and content[cursor] == "\n":
                cursor += 1
            mode = "answer"
        return events, mode

    @classmethod
    def _split_stream_content_by_reasoning_tags(
        cls,
        content: str,
        *,
        state: str,
        enabled: bool,
    ) -> tuple[list[tuple[str, str]], str]:
        if state == "answer" and not cls._should_parse_tagged_reasoning(content):
            return ([("delta", content)] if content else []), state
        events: list[tuple[str, str]] = []

        cursor = 0
        mode = state
        while cursor < len(content):
            if mode == "answer":
                start = content.find("<think>", cursor)
                if start == -1:
                    remaining = content[cursor:]
                    if remaining:
                        events.append(("delta", remaining))
                    break
                answer_text = content[cursor:start]
                if answer_text:
                    events.append(("delta", answer_text))
                cursor = start + len("<think>")
                mode = "thinking"
                continue
            end = content.find("</think>", cursor)
            if end == -1:
                reasoning_text = content[cursor:]
                if reasoning_text:
                    events.append(("thinking", reasoning_text))
                cursor = len(content)
                break
            reasoning_text = content[cursor:end]
            if reasoning_text:
                events.append(("thinking", reasoning_text.rstrip()))
            cursor = end + len("</think>")
            mode = "answer"
        return events, mode

    @classmethod
    def _should_parse_tagged_reasoning(cls, content: str) -> bool:
        return "<think>" in content or "</think>" in content

    @staticmethod
    def _is_embedding_model_name(model_name: str) -> bool:
        lowered = model_name.lower()
        return lowered.startswith("text-embedding") or "embed" in lowered

    @staticmethod
    def _is_meta_non_chat_model(model_name: str) -> bool:
        lowered = model_name.casefold().replace("_", "-")
        return any(
            token in lowered for token in ("muse-image", "muse-voice", "sam-", "segment-anything")
        )

    @classmethod
    def _is_chat_model_name(cls, model_name: str) -> bool:
        lowered = model_name.lower()
        if cls._is_embedding_model_name(lowered):
            return False
        excluded = (
            "moderation",
            "tts",
            "transcribe",
            "transcription",
            "realtime",
            "audio",
            "image",
            "dall",
            "whisper",
            "sora",
            "rerank",
        )
        if any(token in lowered for token in excluded):
            return False
        return True
