from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.ingestion.services import embedding_service as embedding_module
from app.ingestion.services.embedding_service import (
    EmbeddingService,
    NonRetryableEmbeddingError,
    RetryableEmbeddingError,
)
from app.providers.services import EmbeddingResponse
from app.system.services.rate_limit_service import RateLimitService, _InMemoryRateStore

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class _DummyMetric:
    def labels(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return self

    def inc(self) -> None:
        return None

    def observe(self, value: float) -> None:
        _ = value
        return None


class _RetryError(Exception):
    pass


def test_rate_store_increment_and_ttl_path(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _InMemoryRateStore()
    time_seq = iter([1000.0, 1001.0, 1007.5])
    monkeypatch.setattr(
        "app.system.services.rate_limit_service.time.time", lambda: next(time_seq)
    )

    count1, ttl1 = store.increment(key="k", window_seconds=5)
    count2, ttl2 = store.increment(key="k", window_seconds=5)
    count3, ttl3 = store.increment(key="k", window_seconds=5)

    assert (count1, ttl1) == (1, 5)
    assert count2 == 2
    assert ttl2 >= 3
    assert (count3, ttl3) == (1, 5)


def test_rate_limit_service_redis_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    service = RateLimitService(settings)

    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(
        "app.system.services.rate_limit_service._get_redis_client", _boom
    )
    count, ttl = service._increment_counter(key="k", window_seconds=5)
    assert count >= 1
    assert ttl >= 0


def test_embed_many_retry_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    service = EmbeddingService(settings)
    service._state.failures = 0
    service._state.opened_until = None

    monkeypatch.setattr(embedding_module, "RetryError", _RetryError)

    def _raise_retry(_texts):  # type: ignore[no-untyped-def]
        raise _RetryError("retry exhausted")

    monkeypatch.setattr(service, "_embed_with_retry", _raise_retry)
    monkeypatch.setattr(
        embedding_module, "EMBEDDING_PROVIDER_FAILURES_TOTAL", _DummyMetric()
    )

    with pytest.raises(ApiError) as exc:
        service.embed_many(["x"])
    assert exc.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


def test_embed_many_unexpected_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    service = EmbeddingService(settings)
    service._state.failures = 0
    service._state.opened_until = None

    monkeypatch.setattr(
        embedding_module, "EMBEDDING_PROVIDER_FAILURES_TOTAL", _DummyMetric()
    )
    monkeypatch.setattr(
        service,
        "_embed_with_retry",
        lambda _texts: (_ for _ in ()).throw(RuntimeError("x")),
    )

    with pytest.raises(ApiError) as exc:
        service.embed_many(["x"])
    assert exc.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


def test_embed_with_retry_empty_retryer_hits_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    service = EmbeddingService(settings)

    class _EmptyRetrying:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)

        def __iter__(self):
            return iter(())

    monkeypatch.setattr(embedding_module, "Retrying", _EmptyRetrying)
    with pytest.raises(ApiError) as exc:
        service._embed_with_retry(["abc"])
    assert exc.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


def test_embed_provider_timeout_markers_and_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    service = EmbeddingService(settings)
    settings.provider_timeout_seconds = 1

    with pytest.raises(RetryableEmbeddingError):
        service._embed_provider_call(["__EMBED_TIMEOUT__"])

    times = iter([0.0, 10.0])
    monkeypatch.setattr(
        "app.ingestion.services.embedding_service.time.monotonic", lambda: next(times)
    )
    with pytest.raises(RetryableEmbeddingError):
        service._embed_provider_call(["normal"])


def test_sentence_transformers_error_timeout_and_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "sentence-transformers"
    settings.embedding_dimension = 4
    service = EmbeddingService(settings)

    class _ProviderError:
        def embed_many(self, request):  # type: ignore[no-untyped-def]
            _ = request
            raise RuntimeError("encode fail")

    monkeypatch.setattr(
        embedding_module.ProviderRegistry,
        "get_embedding_provider",
        lambda self, provider_type=None: _ProviderError(),
    )
    with pytest.raises(RetryableEmbeddingError):
        service._embed_provider_call(["a"])

    class _ProviderDimMismatch:
        def embed_many(self, request):  # type: ignore[no-untyped-def]
            _ = request
            return EmbeddingResponse(vectors=[[1.0]])

    monkeypatch.setattr(
        embedding_module.ProviderRegistry,
        "get_embedding_provider",
        lambda self, provider_type=None: _ProviderDimMismatch(),
    )
    with pytest.raises(NonRetryableEmbeddingError):
        service._embed_provider_call(["a"])

    class _ProviderOK:
        def embed_many(self, request):  # type: ignore[no-untyped-def]
            _ = request
            return EmbeddingResponse(vectors=[[1.0, 2.0, 3.0, 4.0]])

    monkeypatch.setattr(
        embedding_module.ProviderRegistry,
        "get_embedding_provider",
        lambda self, provider_type=None: _ProviderOK(),
    )
    monkeypatch.setattr(
        embedding_module, "EMBEDDING_PROVIDER_LATENCY_SECONDS", _DummyMetric()
    )

    times = iter([0.0, 2.0, 2.0])
    monkeypatch.setattr(
        "app.ingestion.services.embedding_service.time.monotonic", lambda: next(times)
    )
    settings.embedding_timeout_seconds = 1
    vectors = service._embed_provider_call(["a"])
    assert len(vectors) == 1

    class _ProviderSlow:
        def embed_many(self, request):  # type: ignore[no-untyped-def]
            _ = request
            return EmbeddingResponse(vectors=[[1.0, 2.0, 3.0, 4.0]])

    monkeypatch.setattr(
        embedding_module.ProviderRegistry,
        "get_embedding_provider",
        lambda self, provider_type=None: _ProviderSlow(),
    )
    times = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(
        "app.ingestion.services.embedding_service.time.monotonic", lambda: next(times)
    )
    vectors = service._embed_provider_call(["a"])
    assert len(vectors) == 1


def test_sentence_transformer_loader_cache_and_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "sentence-transformers"
    provider = embedding_module.ProviderRegistry(settings).get_embedding_provider(
        "sentence-transformers"
    )
    assert provider.provider_name == "sentence-transformers"

    class _ProviderRuntimeError:
        def embed_many(self, request):  # type: ignore[no-untyped-def]
            _ = request
            raise RuntimeError("missing")

    service = EmbeddingService(settings)
    monkeypatch.setattr(
        embedding_module.ProviderRegistry,
        "get_embedding_provider",
        lambda self, provider_type=None: _ProviderRuntimeError(),
    )
    with pytest.raises(RetryableEmbeddingError):
        service._embed_provider_call(["a"])


def test_sentence_transformer_loader_second_check_inside_lock() -> None:
    settings = get_settings()
    settings.embedding_provider = "sentence-transformers"
    provider = embedding_module.ProviderRegistry(settings).get_embedding_provider(
        "sentence-transformers"
    )
    assert provider.health_check().status == "healthy"


def test_deterministic_vector_short_chunk_and_circuit_reset() -> None:
    settings = get_settings()
    settings.embedding_dimension = 100
    service = EmbeddingService(settings)
    vector = service._deterministic_vector("abc")
    assert len(vector) == 100

    service._state.failures = 2
    service._state.opened_until = datetime.now(tz=UTC) - timedelta(seconds=1)
    service._guard_circuit_state()
    assert service._state.failures == 0
    assert service._state.opened_until is None
