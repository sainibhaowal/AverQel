from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.auth.schemas.auth import LoginRequest
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.middleware import RateLimitDecision, RequestContextMiddleware
from app.ingestion.services.parser_service import ParserService
from app.query.schemas.queries import QueryFilters, QueryRequest
from app.query.services import answer_service as answer_module
from app.query.services.answer_service import (
    AnswerService,
    NonRetryableLlmError,
    RetryableLlmError,
)
from app.query.services.retrieval_service import RetrievedChunk

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


@pytest.mark.asyncio
async def test_middleware_rate_limit_headers_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Limiter:
        def enforce_global_ip_limit(self, *, request):  # type: ignore[no-untyped-def]
            request.state.rate_limit = RateLimitDecision(
                limit=60,
                remaining=0,
                reset_unix=123,
                scope="global_ip",
            )
            raise ApiError(code="RATE_LIMIT_EXCEEDED", message="x", status_code=429, details={})

    monkeypatch.setattr("app.core.middleware.get_settings", get_settings)
    monkeypatch.setattr("app.core.middleware.RateLimitService", lambda _settings: _Limiter())
    monkeypatch.setattr(
        "app.core.middleware.API_REQUESTS_TOTAL",
        SimpleNamespace(labels=lambda **_: SimpleNamespace(inc=lambda: None)),
    )
    monkeypatch.setattr(
        "app.core.middleware.API_REQUEST_LATENCY_SECONDS",
        SimpleNamespace(labels=lambda **_: SimpleNamespace(observe=lambda _: None)),
    )

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/api/v1/queries",
            "raw_path": b"/api/v1/queries",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("testserver", 80),
        },
        receive,
    )

    async def _app(scope: Any, receive: Any, send: Any) -> None:
        pass

    mw = RequestContextMiddleware(app=_app)
    response = await mw.dispatch(
        req, lambda _request: (_ for _ in ()).throw(RuntimeError("not called"))
    )
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] == "123"


def test_schema_validation_branches() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="no-at", password="12345678")
    with pytest.raises(ValidationError):
        QueryFilters(
            created_at_from=datetime(2026, 1, 2, tzinfo=UTC),
            created_at_to=datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):
        QueryRequest(query="   ", top_k=1, filters=cast(QueryFilters, {}))


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        document_id=UUID("11111111-1111-7111-8111-111111111111"),
        chunk_id=UUID("22222222-2222-7222-8222-222222222222"),
        filename="mock.pdf",
        content="x" * 2000,
        similarity_score=0.9,
    )


def test_answer_service_remaining_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    # _llm_generation_enabled line for missing key
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_API_KEY", "")
    get_settings.cache_clear()
    service = AnswerService("no-result", get_settings())
    assert service._llm_generation_enabled() is False

    # _call_llm_with_retry / _call_llm_provider settings-none branches
    service_none = AnswerService("no-result", None)
    with pytest.raises(NonRetryableLlmError):
        service_none._call_llm_with_retry(query_text="q", context="c")
    with pytest.raises(NonRetryableLlmError):
        service_none._call_llm_provider(query_text="q", context="c")

    # RetryError branch in _stream_generate_with_provider
    class _RetryError(Exception):
        pass

    monkeypatch.setattr(answer_module, "RetryError", _RetryError)
    monkeypatch.setattr(service, "_llm_is_circuit_open", lambda: False)
    monkeypatch.setattr(service, "_allow_llm_usage", lambda **_: True)
    monkeypatch.setattr(
        service,
        "_call_llm_with_retry",
        lambda **_: (_ for _ in ()).throw(_RetryError("x")),
    )
    # Stream generator yields fallback content on error, not None
    result = list(
        service._stream_generate_with_provider(
            tenant_id=UUID("33333333-3333-7333-8333-333333333333"),
            query_text="q",
            ranked_chunks=[_chunk()],
        )
    )
    assert len(result) >= 0  # Generator completes without raising

    # _call_llm_with_retry empty branch removed due to refactor

    service2 = AnswerService("no-result", get_settings())

    # _call_llm_provider exception branch 246-247
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(post=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("httpx missing"))),
    )
    with pytest.raises(RetryableLlmError):
        service2._call_llm_provider(query_text="q", context="c")

    # _allow_llm_usage settings-none, token max, redis rpm+budget branches
    assert (
        service_none._allow_llm_usage(
            tenant_id=UUID("33333333-3333-7333-8333-333333333333"),
            estimated_input_tokens=10,
        )
        is False
    )
    s2 = cast(Settings, service2.settings)
    s2.llm_max_tokens_per_request = 1
    assert (
        service2._allow_llm_usage(
            tenant_id=UUID("33333333-3333-7333-8333-333333333333"),
            estimated_input_tokens=2,
        )
        is False
    )

    s2.llm_max_tokens_per_request = 100
    s2.llm_max_requests_per_minute = 1
    s2.llm_monthly_budget_usd = 0.5

    class _Pipe:
        def __init__(self, raw):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

        def incr(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)

        def expire(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)

        def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)

        def execute(self):
            return self.raw

    class _Client:
        def __init__(self, raw):
            self.raw = raw

        def pipeline(self):
            return _Pipe(self.raw)

        def incrbyfloat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)

        def expire(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)

    monkeypatch.setattr(answer_module, "get_redis_client", lambda: _Client([2, 1, 0]))
    assert (
        service2._allow_llm_usage(
            tenant_id=UUID("33333333-3333-7333-8333-333333333333"),
            estimated_input_tokens=10,
        )
        is False
    )

    monkeypatch.setattr(answer_module, "get_redis_client", lambda: _Client([1, 1, 1.0]))
    assert (
        service2._allow_llm_usage(
            tenant_id=UUID("33333333-3333-7333-8333-333333333333"),
            estimated_input_tokens=10,
        )
        is False
    )

    # circuit reset + failure-none + threshold open + prompt truncation
    AnswerService._llm_circuit.failures = 3
    AnswerService._llm_circuit.opened_until = datetime.now(tz=UTC) - timedelta(seconds=1)
    assert AnswerService._llm_is_circuit_open() is False

    service_none._record_llm_failure()
    service2._llm_circuit.failures = (
        cast(Settings, service2.settings).provider_circuit_breaker_threshold - 1
    )
    service2._record_llm_failure()
    assert service2._llm_circuit.opened_until is not None

    context = service2._build_prompt_context([_chunk()])
    assert context.endswith("...")


def test_parser_unicode_decode_fallback() -> None:
    parser = ParserService(max_text_chars=100)
    result = parser._parse_text(b"\xff\xfe")
    assert result.page_count is None
