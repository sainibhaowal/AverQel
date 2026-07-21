from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any

from app.core.config import get_settings
from app.providers.services.base import ProviderRequestError
from app.providers.services.builtin_local_models import get_builtin_embedding_dimension
from app.providers.services.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResult,
    ProviderModelInfo,
    RerankRequest,
    RerankResponse,
    RerankResultItem,
)


class SentenceTransformersEmbeddingProvider:
    provider_name = "sentence-transformers"
    _SUPPORTED_EMBEDDING_MODELS: tuple[tuple[str, str, int], ...] = (
        ("BAAI/bge-small-en-v1.5", "BGE Small English v1.5", 384),
        ("intfloat/multilingual-e5-small", "Multilingual E5 Small", 384),
    )
    _SUPPORTED_RERANKER_MODELS: tuple[tuple[str, str], ...] = (
        ("BAAI/bge-reranker-v2-m3", "BGE Reranker v2 M3"),
        ("cross-encoder/ms-marco-MiniLM-L-12-v2", "MS MARCO MiniLM L12 v2"),
    )

    def __init__(self, *, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.local_inference_base_url).rstrip("/")
        self.timeout_seconds = settings.local_inference_timeout_seconds

    @staticmethod
    def _httpx() -> Any:
        return importlib.import_module("httpx")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        httpx_module = self._httpx()
        response = httpx_module.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=float(self.timeout_seconds),
        )
        if response.status_code >= 400:
            message: str | None = None
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                body = None
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, str):
                    message = detail
            if message is None:
                message = getattr(response, "text", None)
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=int(response.status_code),
                message=message,
            )
        payload_obj = response.json()
        if not isinstance(payload_obj, dict):
            raise RuntimeError("Local inference response must be a JSON object")
        return payload_obj

    def embed_many(self, request: EmbeddingRequest) -> EmbeddingResponse:
        payload = self._post(
            "/embed",
            {
                "model": request.model,
                "texts": request.texts,
                "batch_size": request.batch_size,
                "normalize": request.normalize,
            },
        )
        vectors: list[list[float]] = []
        for raw in payload.get("vectors", []):
            if not isinstance(raw, list):
                raise RuntimeError("Local inference returned an invalid embedding row")
            vector = [float(value) for value in raw]
            if len(vector) != request.dimension:
                raise RuntimeError("Embedding dimension mismatch")
            vectors.append(vector)
        return EmbeddingResponse(vectors=vectors)

    def list_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        return [
            ProviderModelInfo(
                name=model_name,
                kind="embedding",
                display_name=display_name,
                context_window=512,
                capabilities={
                    "runtime": "sentence-transformers",
                    "hosted_by": "averqel-backend",
                    "supports_chat": False,
                    "supports_embeddings": True,
                    "embedding_dimension": dimension,
                    "install_supported": False,
                    "selection_only": False,
                    "preinstalled": True,
                },
            )
            for model_name, display_name, dimension in self._SUPPORTED_EMBEDDING_MODELS
        ]

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return [
            ProviderModelInfo(
                name=model_name,
                kind="reranker",
                display_name=display_name,
                context_window=512,
                capabilities={
                    "runtime": "sentence-transformers-cross-encoder",
                    "hosted_by": "averqel-backend",
                    "supports_chat": False,
                    "supports_embeddings": False,
                    "supports_reranking": True,
                    "install_supported": False,
                    "selection_only": False,
                    "preinstalled": True,
                    "profile": (
                        "fast_local" if "MiniLM" in model_name else "multilingual_local"
                    ),
                },
            )
            for model_name, display_name in self._SUPPORTED_RERANKER_MODELS
        ]

    def rerank(self, request: RerankRequest) -> RerankResponse:
        payload = self._post(
            "/rerank",
            {
                "model": request.model,
                "query": request.query,
                "documents": request.documents,
                "top_n": request.top_n,
            },
        )
        results: list[RerankResultItem] = []
        for row in payload.get("results", []):
            if not isinstance(row, dict):
                continue
            index = row.get("index")
            score = row.get("score")
            if not isinstance(index, int | float) or not isinstance(score, int | float):
                continue
            results.append(RerankResultItem(index=int(index), score=float(score)))
        return RerankResponse(results=results[: request.top_n])

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status="healthy", latency_ms=0)

    @classmethod
    def get_embedding_dimension(cls, model_name: str) -> int | None:
        return get_builtin_embedding_dimension(model_name)
