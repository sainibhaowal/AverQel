from __future__ import annotations

import importlib
import re
from collections.abc import Sequence
from typing import Any, Literal
from urllib.parse import urlparse

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.context_window import extract_context_window
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.reasoning_capabilities import reasoning_capabilities
from app.providers.services.types import ChatGenerateRequest, ProviderModelInfo
from app.providers.services.url_resolution import resolve_provider_base_url


class LMStudioProvider(OpenAICompatibleProvider):
    provider_name = "lmstudio"
    _FALLBACK_CHUNK_SIZE = 16
    _EMBEDDING_MODEL_PATTERN = re.compile(
        r"(?:^|[-_/])(embed(?:ding)?|bge|e5|nomic)(?:[-_/]|$)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(supports_embeddings=True)
        self.base_url: str | None = None
        self.api_key: str | None = None

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        parsed = urlparse(normalized)
        path = parsed.path.rstrip("/")
        if path.endswith("/v1"):
            return normalized
        suffix = "/v1" if not path else f"{path}/v1"
        return parsed._replace(path=suffix).geturl().rstrip("/")

    def bind(self, base_url: str, api_key: str | None = None) -> LMStudioProvider:
        resolved_base_url = resolve_provider_base_url(base_url, provider_type=self.provider_name)
        self.base_url = self.normalize_base_url(resolved_base_url or base_url)
        self.api_key = api_key
        return self

    def list_models(self) -> Sequence[ProviderModelInfo]:
        discovered = self._fetch_model_payload()
        infos: list[ProviderModelInfo] = []
        for item in discovered:
            name = self._extract_model_name(item)
            if not name or self._looks_like_embedding_model(name):
                continue
            infos.append(self._build_model_info(item=item, name=name, kind="chat"))
        return infos

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        discovered = self._fetch_model_payload()
        embedding_models: list[ProviderModelInfo] = []
        for item in discovered:
            name = self._extract_model_name(item)
            if not name or not self._looks_like_embedding_model(name):
                continue
            embedding_models.append(self._build_model_info(item=item, name=name, kind="embedding"))
        return embedding_models

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def _fetch_model_payload(self) -> list[dict[str, Any]]:
        if not self.base_url:
            raise ProviderCapabilityError("lmstudio provider requires a configured base URL")
        httpx_module = importlib.import_module("httpx")
        headers = self._build_headers(self.api_key)
        for models_url in self._models_endpoints():
            response = httpx_module.get(models_url, headers=headers, timeout=8.0)
            if response.status_code >= 400:
                continue
            payload = response.json()
            data = self._extract_model_items(payload)
            if data:
                return data
        raise RuntimeError("lmstudio status unavailable")

    def chat_model_is_usable(self, model_name: str) -> bool:
        if not self.base_url:
            raise ProviderCapabilityError("lmstudio provider requires a configured base URL")
        httpx_module = importlib.import_module("httpx")
        headers = self._build_headers(self.api_key)
        response = httpx_module.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "ping"}],
                "temperature": 0,
                "max_tokens": 1,
                "stream": False,
            },
            timeout=20.0,
        )
        return response.status_code < 400

    @classmethod
    def _looks_like_embedding_model(cls, model_name: str) -> bool:
        return bool(cls._EMBEDDING_MODEL_PATTERN.search(model_name.lower()))

    @staticmethod
    def _extract_model_name(item: dict[str, Any]) -> str | None:
        for key in (
            "id",
            "modelKey",
            "model_key",
            "key",
            "name",
            "displayName",
            "display_name",
        ):
            name = item.get(key)
            if isinstance(name, str) and name:
                return name
        details = item.get("details")
        if isinstance(details, dict):
            for key in (
                "id",
                "modelKey",
                "model_key",
                "key",
                "name",
                "displayName",
                "display_name",
            ):
                name = details.get(key)
                if isinstance(name, str) and name:
                    return name
        return None

    @staticmethod
    def _extract_display_name(item: dict[str, Any], fallback: str) -> str:
        for key in ("displayName", "display_name", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        details = item.get("details")
        if isinstance(details, dict):
            for key in ("displayName", "display_name", "name"):
                value = details.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return fallback

    @staticmethod
    def _extract_model_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("data", "models", "loaded_models", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if any(
            isinstance(payload.get(key), str | int | float | bool)
            for key in ("id", "modelKey", "model_key", "name")
        ):
            return [payload]
        return []

    def _models_endpoints(self) -> list[str]:
        if self.base_url is None:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=500,
                message="LM Studio provider is not configured with a base URL.",
            )
        normalized = self.base_url.rstrip("/")
        parsed = urlparse(normalized)
        path = parsed.path.rstrip("/")
        if path.endswith("/api/v1"):
            root_path = path[: -len("/api/v1")]
        elif path.endswith("/v1"):
            root_path = path[: -len("/v1")]
        else:
            root_path = path
        if root_path.endswith("/"):
            root_path = root_path.rstrip("/")

        def build(path_suffix: str) -> str:
            suffix_path = f"{root_path}{path_suffix}" if root_path else path_suffix
            return parsed._replace(path=suffix_path).geturl().rstrip("/")

        candidate_urls: list[str] = []
        for candidate in (
            build("/api/v1/models"),
            build("/v1/models"),
            f"{normalized}/models",
        ):
            if candidate not in candidate_urls:
                candidate_urls.append(candidate)
        return candidate_urls

    def _build_model_info(
        self,
        *,
        item: dict[str, Any],
        name: str,
        kind: Literal["chat", "embedding", "vision", "other"],
    ) -> ProviderModelInfo:
        supports_chat = kind == "chat"
        supports_embeddings = kind == "embedding"
        metadata: dict[str, Any] = {
            "local_runtime": True,
            "runtime": "lmstudio",
            "supports_chat": supports_chat,
            "supports_embeddings": supports_embeddings,
            "install_supported": False,
            "visible": True,
            "installed_or_visible": "visible",
            "selection_only": True,
        }
        if supports_chat:
            metadata.update(reasoning_capabilities("lmstudio", name, base_url=self.base_url))
        quantization = item.get("quantization")
        quantization_name: str | None = None
        quantization_bits: int | float | None = None
        if isinstance(quantization, dict):
            raw_name = quantization.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                quantization_name = raw_name.strip()
            raw_bits = quantization.get("bits_per_weight")
            if isinstance(raw_bits, int | float) and not isinstance(raw_bits, bool):
                quantization_bits = raw_bits
        if quantization_name is None and "@" in name:
            quantization_name = name.rsplit("@", 1)[1].strip().upper() or None
        if quantization_name:
            metadata["quantization"] = quantization_name
        if quantization_bits is not None:
            metadata["quantization_bits"] = quantization_bits
        owned_by = item.get("owned_by")
        if isinstance(owned_by, str) and owned_by:
            metadata["owned_by"] = owned_by
        return ProviderModelInfo(
            name=name,
            kind=kind,
            context_window=self._extract_context_window(item),
            display_name=self._extract_display_name(item, name),
            capabilities=metadata,
        )

    @staticmethod
    def _chunk_fallback_content(text: str) -> Sequence[str]:
        normalized = text.replace("\r\n", "\n")
        chunks: list[str] = []
        cursor = 0
        size = LMStudioProvider._FALLBACK_CHUNK_SIZE
        while cursor < len(normalized):
            end = min(len(normalized), cursor + size)
            if end < len(normalized):
                window = normalized[cursor:end]
                match = re.search(r"[\s,.!?;:)\]}](?!.*[\s,.!?;:)\]}])", window)
                if match is not None and match.start() >= max(8, size // 3):
                    end = cursor + match.end()
            chunk = normalized[cursor:end]
            if chunk:
                chunks.append(chunk)
            cursor = end
        return chunks

    async def stream_generate(self, request: ChatGenerateRequest):
        try:
            async for chunk in super().stream_generate(request):
                yield chunk
            return
        except Exception:
            response = self.generate(request)
            for chunk in self._chunk_fallback_content(response.content):
                yield chunk

    async def stream_generate_events(self, request: ChatGenerateRequest):
        try:
            async for event in super().stream_generate_events(request):
                yield event
            return
        except Exception:
            response = self.generate(request)
            if response.thinking_content:
                for chunk in self._chunk_fallback_content(response.thinking_content):
                    yield {"type": "thinking", "text": chunk}
            for chunk in self._chunk_fallback_content(response.content):
                yield {"type": "delta", "text": chunk}

    def stream_generate_sync(self, request: ChatGenerateRequest):
        try:
            yield from super().stream_generate_sync(request)
            return
        except Exception:
            response = self.generate(request)
            yield from self._chunk_fallback_content(response.content)

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
