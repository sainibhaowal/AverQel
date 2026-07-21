from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from app.core.config import get_settings
from app.query.schemas.structured_response import StructuredAnswerResponse
from app.query.services.answer_service import AnswerService
from app.query.services.retrieval_service import RetrievedChunk


def test_answer_service_uses_llm_provider_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("AKS_LLM_API_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AKS_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AKS_LLM_MAX_TOKENS_PER_REQUEST", "1024")
    monkeypatch.setenv("AKS_LLM_MAX_REQUESTS_PER_MINUTE", "30")
    monkeypatch.setenv("AKS_LLM_MONTHLY_BUDGET_USD", "100")
    get_settings.cache_clear()

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "choices": [{"message": {"content": "Generated answer from provider"}}]
            }

    fake_httpx = SimpleNamespace(
        post=lambda *args, **kwargs: _FakeResponse()
    )  # noqa: ARG005
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    settings = get_settings()
    service = AnswerService(settings.query_no_result_answer_text, settings)
    chunks = [
        RetrievedChunk(
            document_id=UUID("11111111-1111-7111-8111-111111111111"),
            chunk_id=UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
            filename="mock.pdf",
            content="Source content one.",
            similarity_score=0.93,
        )
    ]

    result = service.synthesize(
        retrieved_chunks=chunks,
        query_text="What is the answer?",
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
    )
    assert (
        cast(StructuredAnswerResponse, result.answer).detailed_analysis
        == "Generated answer from provider"
    )
    assert result.citations
    get_settings.cache_clear()
