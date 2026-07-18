from __future__ import annotations

from app.core.config import get_settings
from app.services.ingestion.embedding_service import EmbeddingService


def test_embedding_path_uses_registry_compatibly(monkeypatch):
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "16")
    get_settings.cache_clear()
    EmbeddingService._state.failures = 0
    EmbeddingService._state.opened_until = None
    service = EmbeddingService(get_settings())
    vectors = service.embed_many(["alpha", "beta"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 16
    get_settings.cache_clear()
