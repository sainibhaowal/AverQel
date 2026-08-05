from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any

from app.providers.services.base import ProviderCapabilityError
from app.providers.services.context_window import extract_context_window
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.types import HealthCheckResult, ProviderModelInfo
from app.providers.services.url_resolution import resolve_provider_base_url


class OllamaProvider(OpenAICompatibleProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        super().__init__(supports_embeddings=True)
        self.base_url: str | None = None

    def bind(self, base_url: str, api_key: str | None = None) -> OllamaProvider:
        self.base_url = resolve_provider_base_url(base_url, provider_type=self.provider_name)
        self.api_key = api_key
        return self

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if not self.base_url:
            raise ProviderCapabilityError("ollama provider requires a configured base URL")
        httpx_module = importlib.import_module("httpx")
        response = httpx_module.get(f"{self.base_url}/api/tags", timeout=8.0)
        if response.status_code >= 400:
            raise RuntimeError(f"ollama status {response.status_code}")
        payload: dict[str, Any] = response.json()
        models = payload.get("models", [])
        infos: list[ProviderModelInfo] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                details = item.get("details")
                metadata: dict[str, Any] = {
                    "local_runtime": True,
                    "runtime": "ollama",
                    "supports_chat": True,
                    "supports_embeddings": True,
                    "install_supported": True,
                    "visible": True,
                    "installed_or_visible": "installed",
                }
                if isinstance(item.get("size"), int):
                    metadata["size_bytes"] = item["size"]
                if isinstance(details, dict):
                    family = details.get("family")
                    parameter_size = details.get("parameter_size")
                    quantization = details.get("quantization_level")
                    if isinstance(family, str) and family:
                        metadata["family"] = family
                    if isinstance(parameter_size, str) and parameter_size:
                        metadata["parameter_size"] = parameter_size
                    if isinstance(quantization, str) and quantization:
                        metadata["quantization_level"] = quantization
                infos.append(
                    ProviderModelInfo(
                        name=name,
                        kind="chat",
                        context_window=self._extract_context_window(item),
                        display_name=name,
                        capabilities=metadata,
                    )
                )
        return infos

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        embedding_models: list[ProviderModelInfo] = []
        for model in self.list_models():
            capabilities = dict(model.capabilities)
            capabilities["supports_chat"] = False
            capabilities["supports_embeddings"] = True
            embedding_models.append(
                ProviderModelInfo(
                    name=model.name,
                    kind="embedding",
                    display_name=model.display_name or model.name,
                    context_window=model.context_window,
                    capabilities=capabilities,
                )
            )
        return embedding_models

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_local_models(self) -> Sequence[ProviderModelInfo]:
        return self.list_models()

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

    def pull_model(self, model_name: str) -> HealthCheckResult:
        if not self.base_url:
            raise ProviderCapabilityError("ollama provider requires a configured base URL")
        httpx_module = importlib.import_module("httpx")
        response = httpx_module.post(
            f"{self.base_url}/api/pull",
            json={"name": model_name, "stream": False},
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"ollama status {response.status_code}")
        return HealthCheckResult(status="healthy", metadata={"pulled": model_name})

    def delete_model(self, model_name: str) -> HealthCheckResult:
        if not self.base_url:
            raise ProviderCapabilityError("ollama provider requires a configured base URL")
        httpx_module = importlib.import_module("httpx")
        response = httpx_module.request(
            "DELETE",
            f"{self.base_url}/api/delete",
            json={"name": model_name},
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"ollama status {response.status_code}")
        return HealthCheckResult(status="healthy", metadata={"deleted": model_name})
