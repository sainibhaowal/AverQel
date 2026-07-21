from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.ingestion.services.embedding_service import EmbeddingService


def test_embedding_retryable_error_falls_back_to_local_embeddings() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.embedding_provider = "sentence-transformers"
    service = EmbeddingService(settings)
    vectors = service.embed_many(["__EMBED_RETRYABLE__"])
    assert len(vectors) == 1
    assert len(vectors[0]) == service.settings.embedding_dimension
    assert service._last_run_metadata is not None
    assert service._last_run_metadata.fallback_used is True
    assert service._last_run_metadata.failure_code == "EMBEDDING_PROVIDER_UNAVAILABLE"


def test_embedding_non_retryable_error_maps_to_unprocessable() -> None:
    get_settings.cache_clear()
    service = EmbeddingService(get_settings())
    with pytest.raises(ApiError) as exc_info:
        service.embed_many(["__EMBED_NONRETRYABLE__"])
    assert exc_info.value.code == "EMBEDDING_REQUEST_INVALID"


def test_embedding_circuit_breaker_opens_after_threshold() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.embedding_provider = "sentence-transformers"
    service = EmbeddingService(settings)
    threshold = settings.provider_circuit_breaker_threshold

    for _ in range(threshold):
        vectors = service.embed_many(["__EMBED_RETRYABLE__"])
        assert len(vectors[0]) == settings.embedding_dimension

    vectors = service.embed_many(["hello"])
    assert len(vectors[0]) == settings.embedding_dimension
    assert service._last_run_metadata is not None
    assert service._last_run_metadata.fallback_used is True
