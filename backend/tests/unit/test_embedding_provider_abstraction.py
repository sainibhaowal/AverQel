from __future__ import annotations

import pytest

from app.services.providers.local_deterministic_provider import (
    LocalDeterministicEmbeddingProvider,
)
from app.services.providers.sentence_transformers_provider import (
    SentenceTransformersEmbeddingProvider,
)
from app.services.providers.types import EmbeddingRequest


def test_local_deterministic_embedding_provider_returns_expected_dimensions():
    provider = LocalDeterministicEmbeddingProvider()
    response = provider.embed_many(
        EmbeddingRequest(
            texts=["alpha", "beta"],
            model="hash-fallback",
            batch_size=2,
            normalize=True,
            dimension=8,
            timeout_seconds=8,
            provider_name="local-deterministic",
        )
    )
    assert len(response.vectors) == 2
    assert len(response.vectors[0]) == 8


def test_sentence_transformers_embedding_provider_uses_loaded_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"vectors": [[0.1, 0.1, 0.1, 0.1]]}

    class _Httpx:
        @staticmethod
        def post(url: str, *, json: dict[str, object], timeout: float):
            assert url.endswith("/embed")
            assert json["texts"] == ["alpha"]
            assert timeout > 0
            return _Response()

    monkeypatch.setattr(
        SentenceTransformersEmbeddingProvider,
        "_httpx",
        staticmethod(lambda: _Httpx),
    )
    provider = SentenceTransformersEmbeddingProvider()
    response = provider.embed_many(
        EmbeddingRequest(
            texts=["alpha"],
            model="demo-model",
            batch_size=1,
            normalize=True,
            dimension=4,
            timeout_seconds=8,
            provider_name="sentence-transformers",
        )
    )
    assert response.vectors == [[0.1, 0.1, 0.1, 0.1]]
