from __future__ import annotations

import sys
from types import SimpleNamespace
from uuid import UUID

from app.core.config import get_settings
from app.query.services.answer_service import AnswerService
from app.query.services.retrieval_service import RetrievedChunk


def test_query_path_uses_provider_registry_compatibly(monkeypatch):
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_MODEL", "demo")
    monkeypatch.setenv("AKS_LLM_API_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("AKS_LLM_API_KEY", "test-key")
    get_settings.cache_clear()

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "registry answer"}}]}

    monkeypatch.setitem(
        sys.modules, "httpx", SimpleNamespace(post=lambda *a, **k: _FakeResponse())
    )

    service = AnswerService(get_settings().query_no_result_answer_text, get_settings())
    result = service.synthesize(
        retrieved_chunks=[
            RetrievedChunk(
                document_id=UUID("11111111-1111-7111-8111-111111111111"),
                chunk_id=UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
                filename="mock.pdf",
                content="Source.",
                similarity_score=0.9,
            )
        ],
        query_text="What is the answer?",
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
    )
    assert result.answer.detailed_analysis == "registry answer"
    get_settings.cache_clear()
