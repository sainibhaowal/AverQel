from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.types import (
    HealthCheckResult,
    ProviderModelInfo,
    RerankRequest,
    RerankResponse,
    RerankResultItem,
)


class CohereProvider:
    provider_name = "cohere"
    _SUPPORTED_RERANK_MODELS: tuple[tuple[str, str], ...] = (
        ("rerank-v3.5", "Cohere Rerank v3.5"),
    )

    def __init__(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> None:
        self.base_url = (
            base_url.rstrip("/") if base_url else "https://api.cohere.com/v2"
        )
        self.api_key = api_key

    def bind(self, base_url: str, api_key: str | None = None) -> CohereProvider:
        self.base_url = (
            base_url.rstrip("/") if base_url else "https://api.cohere.com/v2"
        )
        self.api_key = api_key
        return self

    @staticmethod
    def _httpx() -> Any:
        return importlib.import_module("httpx")

    @staticmethod
    def _raise_provider_error(response: Any) -> None:
        message: str | None = None
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            message_field = payload.get("message")
            if isinstance(message_field, str) and message_field.strip():
                message = message_field.strip()
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
            provider_name="cohere",
            status_code=int(response.status_code),
            message=message,
        )

    def list_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return [
            ProviderModelInfo(
                name=model_name,
                kind="reranker",
                display_name=display_name,
                capabilities={
                    "runtime": "cohere",
                    "supports_reranking": True,
                    "supports_chat": False,
                    "supports_embeddings": False,
                    "hosted_by": "cohere",
                    "profile": "high_quality_hosted",
                },
            )
            for model_name, display_name in self._SUPPORTED_RERANK_MODELS
        ]

    def rerank(self, request: RerankRequest) -> RerankResponse:
        if not self.api_key:
            raise ProviderCapabilityError("cohere reranking requires an API key")
        httpx_module = self._httpx()
        response = httpx_module.post(
            f"{self.base_url.rstrip('/')}/rerank",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": request.model,
                "query": request.query,
                "documents": request.documents,
                "top_n": request.top_n,
            },
            timeout=float(request.timeout_seconds),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        rows = payload_obj.get("results", [])
        results: list[RerankResultItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            index = row.get("index")
            score = row.get("relevance_score")
            if not isinstance(index, int):
                continue
            if not isinstance(score, int | float):
                continue
            results.append(RerankResultItem(index=index, score=float(score)))
        return RerankResponse(results=results[: request.top_n])

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            status="healthy" if self.api_key else "degraded",
            latency_ms=0,
            error_code=None if self.api_key else "missing_api_key",
            error_message_redacted=(
                None if self.api_key else "Cohere reranking requires an API key."
            ),
        )
