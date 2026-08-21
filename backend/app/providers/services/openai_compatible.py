from __future__ import annotations

import importlib
import json
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import replace
from typing import Any, cast

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.context_window import (
    extract_context_window,
    resolve_verified_context_window,
)
from app.providers.services.reasoning_capabilities import (
    model_supports_reasoning,
    reasoning_capabilities,
    supports_required_tool_choice,
    uses_enable_thinking_controls,
    uses_gemma_think_trigger,
    uses_groq_reasoning_api,
    uses_slash_think_controls,
)
from app.providers.services.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResult,
    ProviderModelInfo,
)
from app.providers.services.url_resolution import resolve_provider_base_url


class OpenAICompatibleProvider:
    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        supports_embeddings: bool = False,
        base_url: str | None = None,
        api_key: str | None = None,
        provider_name: str | None = None,
    ) -> None:
        # Registry-created instances use this to retain the concrete catalog
        # provider (Groq, OpenRouter, vLLM, custom, …) while sharing the
        # OpenAI-compatible transport and stream parser.
        self.provider_name = provider_name or type(self).provider_name
        self.supports_embeddings = supports_embeddings
        self.base_url = resolve_provider_base_url(base_url)
        self.api_key = api_key

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
    def _build_headers(api_key: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

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
            provider_name="openai",
            status_code=int(response.status_code),
            message=cls._extract_provider_error_message(payload=payload, text=text),
        )

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
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
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": messages,
        }
        if request.tools:
            payload["tools"] = request.tools
        effective_tool_choice = self._effective_tool_choice(request)
        if effective_tool_choice:
            payload["tool_choice"] = effective_tool_choice

        self._apply_reasoning_request_settings(payload, request)
        response = httpx_module.post(
            f"{base_url}/chat/completions",
            headers=self._build_headers(request.api_key),
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        choices = payload_obj.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("provider response missing choices")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        # Capture reasoning whenever the provider returns it. The request flag
        # controls provider-side generation settings, not response visibility.
        thinking_content = self._extract_reasoning_text(message)
        if not isinstance(content, str):
            raise RuntimeError("provider response missing message content")
        if not thinking_content:
            extracted_thinking, extracted_content = self._extract_tagged_reasoning_content(
                content,
                enabled=self._reasoning_observation_enabled(request),
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

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event["type"] == "delta":
                text = event.get("text")
                if isinstance(text, str) and text:
                    yield text

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
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
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
        effective_tool_choice = self._effective_tool_choice(request)
        if effective_tool_choice:
            payload["tool_choice"] = effective_tool_choice
        self._apply_reasoning_request_settings(payload, request)
        timeout = httpx_module.Timeout(
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
            read=float(request.metadata.get("read_timeout_seconds", 300.0)),
        )
        async with httpx_module.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=self._build_headers(request.api_key),
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
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        delta = {}
                    thinking = self._extract_reasoning_text(delta)
                    if thinking:
                        thinking_delta = self._stream_text_suffix(
                            emitted_thinking_text,
                            thinking,
                        )
                        if thinking_delta:
                            emitted_thinking_text += thinking_delta
                            yield {"type": "thinking", "text": thinking_delta}
                    content = self._extract_stream_text(choice=choice, delta=delta)
                    if isinstance(content, str) and content:
                        parsed_events, stream_state = self._split_stream_content_for_reasoning(
                            content,
                            state=stream_state,
                            enabled=self._reasoning_observation_enabled(request),
                            model=request.model,
                        )
                        for event_type, text in parsed_events:
                            if not text:
                                continue
                            if event_type == "thinking":
                                thinking_delta = self._stream_text_suffix(
                                    emitted_thinking_text,
                                    text,
                                )
                                if thinking_delta:
                                    emitted_thinking_text += thinking_delta
                                    yield {"type": event_type, "text": thinking_delta}
                                continue
                            if event_type == "delta":
                                answer_delta = self._stream_text_suffix(
                                    emitted_answer_text,
                                    text,
                                )
                                if answer_delta:
                                    emitted_answer_text += answer_delta
                                    yield {"type": event_type, "text": answer_delta}
                                continue
                            yield {"type": event_type, "text": text}

                    # Handle Tool Calls deltas
                    tool_calls_delta = delta.get("tool_calls")
                    if isinstance(tool_calls_delta, list):
                        yield {
                            "type": "tool_calls_delta",
                            "tool_calls": tool_calls_delta,
                        }

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
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
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
            f"{base_url}/chat/completions",
            headers=self._build_headers(request.api_key),
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
                        enabled=self._reasoning_observation_enabled(request),
                        model=request.model,
                    )
                    for event_type, text in parsed_events:
                        if event_type == "delta" and text:
                            yield text

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if not self.base_url:
            raise ProviderCapabilityError("model listing requires a configured provider endpoint")
        httpx_module = self._httpx()
        response = httpx_module.get(
            f"{self.base_url}/models",
            headers=self._build_headers(self.api_key),
            timeout=8.0,
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        data = payload_obj.get("data", [])
        infos: list[ProviderModelInfo] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_name = item.get("id")
            if not isinstance(model_name, str) or not model_name:
                continue
            if not self._is_chat_model_name(model_name):
                continue
            live_context_window = self._extract_context_window(item)
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
                    display_name=None,
                    capabilities={
                        "object": item.get("object", "model"),
                        **(
                            {"context_window_source": context_window_source}
                            if context_window_source
                            else {}
                        ),
                        **reasoning_capabilities(
                            self.provider_name, model_name, base_url=self.base_url
                        ),
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
        httpx_module = self._httpx()
        response = httpx_module.get(
            f"{self.base_url}/models",
            headers=self._build_headers(self.api_key),
            timeout=8.0,
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        data = payload_obj.get("data", [])
        models: list[ProviderModelInfo] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_name = item.get("id")
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
        payload = {"model": request.model, "input": request.texts}
        response = httpx_module.post(
            f"{base_url}/embeddings",
            headers=self._build_headers(str(request.metadata.get("api_key") or "") or None),
            json=payload,
            timeout=float(request.timeout_seconds),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"provider status {response.status_code}")
        payload_obj: dict[str, Any] = response.json()
        data = payload_obj.get("data")
        if not isinstance(data, list):
            raise RuntimeError("provider response missing embedding data")
        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list):
                raise RuntimeError("provider response missing embedding vector")
            vectors.append([float(value) for value in embedding])
        return EmbeddingResponse(vectors=vectors)

    def health_check(self) -> HealthCheckResult:
        start = time.monotonic()
        try:
            self.list_models()
        except ProviderCapabilityError:
            return HealthCheckResult(
                status="healthy", latency_ms=0, metadata={"listing": "unsupported"}
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
        return model_supports_reasoning(self.provider_name, model_name)

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
        if isinstance(candidate, str):
            return candidate if candidate else None
        if isinstance(candidate, list):
            parts: list[str] = []
            for item in candidate:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                nested_text = item.get("content")
                if isinstance(nested_text, str):
                    parts.append(nested_text)
            combined = "".join(parts)
            return combined if combined else None
        return None

    @classmethod
    def _prepare_messages(cls, request: ChatGenerateRequest) -> list[dict[str, Any]]:
        messages = [dict(message) for message in request.messages]
        if not messages:
            return messages
        reasoning_enabled = cls._reasoning_enabled_for_request(request)
        if (
            cls._uses_slash_think_controls(request)
            and request.metadata.get("reasoning_mode") != "auto"
        ):
            command = "/think" if reasoning_enabled else "/no_think"
            for index in range(len(messages) - 1, -1, -1):
                if messages[index].get("role") != "user":
                    continue

                content = str(messages[index].get("content", ""))
                normalized = cls._strip_slash_think_commands(content).strip()
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
                                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
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
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                        }
                        for img_b64 in request.images
                    ],
                ]
                break
        if reasoning_enabled == request.reasoning_enabled:
            return cls._prepare_gemma_thinking(messages, request)
        return cls._prepare_gemma_thinking(
            messages, replace(request, reasoning_enabled=reasoning_enabled)
        )

    @staticmethod
    def _reasoning_enabled_for_request(request: ChatGenerateRequest) -> bool:
        """Avoid an unsupported forced-tool/reasoning combination.

        Some upstream OpenAI-compatible gateways reject
        ``tool_choice=required`` when reasoning controls are present. Tool
        execution remains required; only provider-side reasoning controls are
        omitted for that planning round. Any reasoning or thinking events
        emitted naturally are still parsed.
        """
        if request.tool_choice == "required":
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
        if choice == "required" and not supports_required_tool_choice(
            str(request.metadata.get("provider_type") or ""), request.model
        ):
            # DeepSeek V4 rejects forced choice in its always-thinking mode;
            # keep the tools available and let the model select them.
            return "auto"
        return choice

    @classmethod
    def _prepare_gemma_thinking(
        cls,
        messages: list[dict[str, Any]],
        request: ChatGenerateRequest,
    ) -> list[dict[str, Any]]:
        if not request.reasoning_enabled or not uses_gemma_think_trigger(request.model):
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
        if self._uses_groq_reasoning_api(request):
            if reasoning_enabled:
                payload["reasoning_effort"] = request.reasoning_effort or "medium"
                payload["include_reasoning"] = True
            else:
                payload["include_reasoning"] = False
                payload.pop("reasoning_effort", None)
            return
        if not self.model_supports_reasoning(request.model):
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

    @staticmethod
    def _uses_groq_reasoning_api(request: ChatGenerateRequest) -> bool:
        return uses_groq_reasoning_api(
            str(request.metadata.get("provider_type") or ""),
            request.model,
            base_url=request.base_url,
        )

    @classmethod
    def _uses_slash_think_controls(cls, request: ChatGenerateRequest) -> bool:
        return uses_slash_think_controls(
            str(request.metadata.get("provider_type") or cls.provider_name),
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
        return lowered.startswith("text-embedding") or "embedding" in lowered

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
