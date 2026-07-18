from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.query.structured_response import StructuredAnswerResponse
from app.services.query.answer_service import AnswerService
from app.services.query.query_classifier import QueryClassifier, QueryType
from app.services.query.query_service import QueryService
from app.services.query.retrieval_service import RetrievedChunk


@pytest.fixture
def mock_settings():
    settings = Settings()
    settings.query_no_result_answer_text = "No result"
    settings.ai_integration_scope = "embeddings_and_generation"
    settings.llm_provider = "openai"
    settings.llm_api_key = "test-sk-123"
    return settings


@pytest.fixture
def query_service(mock_settings):
    db_session_mock = MagicMock()
    service = QueryService(db=db_session_mock, settings=mock_settings)

    # Mock retrieval to return dummy chunks
    service.retrieval.retrieve_chunks = MagicMock(
        return_value=[
            RetrievedChunk(
                document_id=uuid4(),
                chunk_id=uuid4(),
                filename="test.pdf",
                content="This is relevant content containing the answer.",
                similarity_score=0.95,
                source_type="text",
                section_header="Testing",
                page_number=1,
            )
        ]
    )

    return service


def test_query_classifier_integration():
    q_type = QueryClassifier.classify("Compare the two models")
    assert q_type == QueryType.COMPARISON


@patch.object(AnswerService, "_call_llm_with_retry")
def test_synthesize_structured_json(mock_llm, query_service):
    # Mock LLM returning valid JSON
    mock_llm.return_value = (
        '{"key_findings": ["Finding 1"], "detailed_analysis": "Detailed logic.", "limitations": "None."}',
        {},
    )

    retrieved_chunks = query_service.retrieval.retrieve_chunks()
    result = query_service.answer.synthesize(
        retrieved_chunks=retrieved_chunks,
        query_text="What is this about?",
        tenant_id=uuid4(),
        query_type=QueryType.FACTUAL,
    )

    assert isinstance(result.answer, StructuredAnswerResponse)
    assert result.answer.key_findings == ["Finding 1"]
    assert result.answer.detailed_analysis == "Detailed logic."
    assert len(result.citations) == 1


@patch.object(AnswerService, "_call_llm_with_retry")
def test_synthesize_fallback_markdown(mock_llm, query_service):
    # Mock LLM returning plain text (failure to emit JSON)
    mock_llm.return_value = ("This is simply text, no json.", {})

    retrieved_chunks = query_service.retrieval.retrieve_chunks()
    result = query_service.answer.synthesize(
        retrieved_chunks=retrieved_chunks,
        query_text="What is this about?",
        tenant_id=uuid4(),
        query_type=QueryType.FACTUAL,
    )

    assert isinstance(result.answer, StructuredAnswerResponse)
    assert result.answer.key_findings == []
    assert result.answer.detailed_analysis == "This is simply text, no json."
    assert result.answer.limitations == ""
