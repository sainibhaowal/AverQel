from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any
from urllib.parse import quote

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


class GoogleProvider:
    provider_name = "google"

    def __init__(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    def bind(self, base_url: str, api_key: str | None = None) -> GoogleProvider:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def model_supports_reasoning(model_name: str) -> bool:
        return model_supports_reasoning("google", model_name)

    @staticmethod
    def _httpx() -> Any:
        return importlib.import_module("httpx")

    @staticmethod
    def _extract_candidate_parts(candidate: dict[str, Any]) -> tuple[str, str | None]:
        parts = candidate.get("content", {}).get("parts", [])
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        for item in parts:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text:
                continue
            if bool(item.get("thought")) or bool(item.get("thoughtSignature")):
                thinking_parts.append(text)
            else:
                text_parts.append(text)
        return "".join(text_parts), "".join(thinking_parts).strip() or None

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
            provider_name="google",
            status_code=int(response.status_code),
            message=message,
        )

    @classmethod
    def _build_generation_config(cls, request: ChatGenerateRequest) -> dict[str, Any]:
        generation_config: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        if cls.model_supports_reasoning(request.model):
            if request.reasoning_enabled:
                generation_config["thinkingConfig"] = {"includeThoughts": True}
            else:
                generation_config["thinkingConfig"] = {
                    "includeThoughts": False,
                    "thinkingBudget": 0,
                }
        return generation_config

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        httpx_module = self._httpx()
        user_parts = []
        for msg in request.messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                user_parts.append(f"System: {content}")
            else:
                user_parts.append(content)
        generation_config = self._build_generation_config(request)
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": "\n\n".join(user_parts)}]}],
            "generationConfig": generation_config,
        }
        api_key = request.api_key or ""
        model = quote(request.model, safe="")
        response = httpx_module.post(
            f"{request.base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        candidates = payload_obj.get("candidates", [])
        text = ""
        thinking_text: str | None = None
        if isinstance(candidates, list) and candidates:
            text, thinking_text = self._extract_candidate_parts(candidates[0])
        return ChatGenerateResponse(
            content=text,
            thinking_content=thinking_text,
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
        user_parts = []
        for msg in request.messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                user_parts.append(f"System: {content}")
            else:
                user_parts.append(content)
        generation_config = self._build_generation_config(request)
        payload = {
            "contents": [{"parts": [{"text": "\n\n".join(user_parts)}]}],
            "generationConfig": generation_config,
        }
        api_key = request.api_key or ""
        model = quote(request.model, safe="")
        async with httpx_module.AsyncClient(
            timeout=float(request.metadata.get("timeout_seconds", 8.0))
        ) as client:
            async with client.stream(
                "POST",
                f"{request.base_url.rstrip('/')}/models/{model}:streamGenerateContent?alt=sse&key={api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    self._raise_provider_error(response)
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.split(":", 1)[1].strip()
                    try:
                        payload_obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    candidates = payload_obj.get("candidates", [])
                    if not isinstance(candidates, list) or not candidates:
                        continue
                    text, thinking_text = self._extract_candidate_parts(candidates[0])
                    if thinking_text:
                        yield {"type": "thinking", "text": thinking_text}
                    if text:
                        yield {"type": "delta", "text": text}

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        result = self.generate(request)
        if result.content:
            yield result.content

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if not self.base_url:
            raise ProviderCapabilityError(
                "google model listing requires a configured endpoint"
            )
        httpx_module = self._httpx()
        next_page_token: str | None = None
        models: list[ProviderModelInfo] = []
        seen: set[str] = set()
        while True:
            suffix = (
                f"&pageToken={quote(next_page_token, safe='')}"
                if next_page_token
                else ""
            )
            response = httpx_module.get(
                f"{self.base_url.rstrip('/')}/models?key={self.api_key or ''}{suffix}",
                headers={"Content-Type": "application/json"},
                timeout=8.0,
            )
            if response.status_code >= 400:
                self._raise_provider_error(response)
            payload_obj: dict[str, Any] = response.json()
            rows = payload_obj.get("models", [])
            for item in rows:
                if not isinstance(item, dict):
                    continue
                if not self._is_supported_chat_model(item):
                    continue
                model_name = self._canonical_model_name(item)
                if model_name in seen:
                    continue
                seen.add(model_name)
                live_context_window = extract_context_window(
                    item,
                    candidate_keys=(
                        "inputTokenLimit",
                        "input_token_limit",
                        "context_window",
                        "context_length",
                    ),
                )
                verified_context_window = resolve_verified_context_window(
                    model_name,
                    provider_type="google",
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
                            item.get("displayName")
                            if isinstance(item.get("displayName"), str)
                            else None
                        ),
                        context_window=context_window,
                        context_window_source=context_window_source,
                        capabilities={
                            "runtime": "google",
                            **(
                                {"context_window_source": context_window_source}
                                if context_window_source
                                else {}
                            ),
                            **reasoning_capabilities(
                                "google", model_name, base_url=self.base_url
                            ),
                        },
                    )
                )
            next_page_token = payload_obj.get("nextPageToken")
            if not isinstance(next_page_token, str) or not next_page_token:
                break
        return models

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        raise ProviderCapabilityError(
            "google embeddings are not supported by this adapter"
        )

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def capabilities_for_model(self, model_name: str) -> dict[str, object]:
        return reasoning_capabilities("google", model_name)

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status="healthy", metadata={"provider": self.provider_name}
        )

    @staticmethod
    def _canonical_model_name(item: dict[str, Any]) -> str:
        base_model_id = item.get("baseModelId")
        if isinstance(base_model_id, str) and base_model_id:
            return base_model_id
        name = item.get("name")
        if isinstance(name, str) and name:
            return name.split("/", 1)[-1]
        return ""

    @classmethod
    def _is_supported_chat_model(cls, item: dict[str, Any]) -> bool:
        methods = item.get("supportedGenerationMethods")
        if not isinstance(methods, list) or "generateContent" not in methods:
            return False
        model_name = cls._canonical_model_name(item).lower()
        if not model_name:
            return False
        excluded = ("embedding", "aqa", "imagen", "veo", "tts", "transcribe")
        return not any(token in model_name for token in excluded)
