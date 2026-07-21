from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.ingestion.embedding_service import (
    EmbeddingService,
    NonRetryableEmbeddingError,
)
from app.providers.services.types import EmbeddingResponse


class _FakeEmbeddingProvider:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.requests: list[object] = []

    def embed_many(self, request) -> EmbeddingResponse:
        self.requests.append(request)
        return EmbeddingResponse(vectors=self.vectors)


def test_sentence_transformers_provider_returns_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setenv("AKS_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "384")
    get_settings.cache_clear()
    provider = _FakeEmbeddingProvider([[0.01] * 384, [0.02] * 384])
    monkeypatch.setattr(
        "app.providers.services.registry.ProviderRegistry.get_embedding_provider",
        lambda self, provider_type=None: provider,
    )

    service = EmbeddingService(get_settings())
    vectors = service.embed_many(["alpha", "beta"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(provider.requests) == 1
    get_settings.cache_clear()


def test_sentence_transformers_dimension_mismatch_falls_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "384")
    get_settings.cache_clear()
    provider = _FakeEmbeddingProvider([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(
        "app.providers.services.registry.ProviderRegistry.get_embedding_provider",
        lambda self, provider_type=None: provider,
    )

    service = EmbeddingService(get_settings())
    vectors = service.embed_many(["alpha"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    get_settings.cache_clear()


def test_sentence_transformers_provider_errors_fall_back_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "384")
    get_settings.cache_clear()

    class _FailingProvider:
        def embed_many(self, request) -> EmbeddingResponse:
            _ = request
            raise RuntimeError("local inference unavailable")

    monkeypatch.setattr(
        "app.providers.services.registry.ProviderRegistry.get_embedding_provider",
        lambda self, provider_type=None: _FailingProvider(),
    )

    service = EmbeddingService(get_settings())
    vectors = service.embed_many(["alpha"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    get_settings.cache_clear()


def test_sentence_transformers_dimension_mismatch_raises_for_local_fallback_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "384")
    get_settings.cache_clear()

    service = EmbeddingService(get_settings())
    vectors = service.embed_many(["alpha"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    get_settings.cache_clear()


def test_sentence_transformers_dimension_mismatch_becomes_non_retryable_in_provider_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "sentence-transformers")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "384")
    get_settings.cache_clear()

    provider = _FakeEmbeddingProvider([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(
        "app.providers.services.registry.ProviderRegistry.get_embedding_provider",
        lambda self, provider_type=None: provider,
    )

    service = EmbeddingService(get_settings())
    with pytest.raises(NonRetryableEmbeddingError):
        service._embed_provider_call(["alpha"])
    get_settings.cache_clear()
