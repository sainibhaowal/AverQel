from __future__ import annotations

import importlib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.providers.services.base import ProviderCapabilityError
from app.providers.services.context_window import extract_context_window
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.reasoning_capabilities import normalize_reasoning_effort_value
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
        model_names = [
            item["name"]
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
        ]
        if model_names:
            with ThreadPoolExecutor(max_workers=min(8, len(model_names))) as executor:
                thinking_metadata = dict(
                    zip(
                        model_names,
                        executor.map(
                            lambda model_name: self._fetch_thinking_capabilities(
                                httpx_module, model_name
                            ),
                            model_names,
                        ),
                        strict=True,
                    )
                )
        else:
            thinking_metadata = {}
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
                metadata.update(thinking_metadata.get(name) or {})
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

    def _fetch_thinking_capabilities(
        self, httpx_module: Any, model_name: str
    ) -> dict[str, Any] | None:
        if not self.base_url:
            return None
        try:
            response = httpx_module.post(
                f"{self.base_url}/api/show",
                json={"model": model_name},
                timeout=3.0,
            )
            if response.status_code >= 400:
                return None
            payload = response.json()
        except Exception:
            # Model discovery remains usable when a server version or model
            # does not provide thinking metadata.
            return None
        thinking = payload.get("thinking") if isinstance(payload, dict) else None
        values = thinking.get("values") if isinstance(thinking, dict) else None
        if not isinstance(values, list):
            return None

        efforts: list[str] = []
        native_values: dict[str, str] = {}
        has_off = False
        for value in values:
            if value is False:
                has_off = True
                continue
            if value is True:
                # Ollama's OpenAI-compatible route translates `reasoning_effort`
                # to its native boolean `think` value for boolean-only models.
                canonical, native = "on", "high"
            elif isinstance(value, str):
                normalized = normalize_reasoning_effort_value(value)
                if normalized in {"off", "none"}:
                    has_off = True
                    native_values["off"] = value.strip()
                    continue
                if normalized is None:
                    continue
                canonical, native = normalized, value.strip()
            else:
                continue
            if canonical not in efforts and len(efforts) < 32:
                efforts.append(canonical)
                native_values[canonical] = native

        supports_reasoning = bool(efforts)
        supports_toggle = supports_reasoning and has_off
        return {
            "reasoning_capabilities_known": True,
            "supports_reasoning": supports_reasoning,
            "supports_thinking_toggle": supports_toggle,
            "supported_reasoning_efforts": efforts,
            "request_controls_on": ["reasoning_effort"] if supports_reasoning else [],
            "request_controls_off": ["reasoning_effort_none"] if supports_toggle else [],
            "reasoning_effort_values": native_values,
        }

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
