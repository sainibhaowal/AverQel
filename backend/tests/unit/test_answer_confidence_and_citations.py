from __future__ import annotations

from uuid import UUID

from app.services.query.answer_service import AnswerService
from app.services.query.retrieval_service import RetrievedChunk


def test_answer_service_returns_no_result_contract() -> None:
    service = AnswerService("No relevant information found for the requested query.")
    result = service.synthesize(retrieved_chunks=[])
    assert result.answer == "No relevant information found for the requested query."
    assert result.confidence == 0.0
    assert result.citations == []


def test_answer_service_confidence_formula_and_grounded_citations() -> None:
    service = AnswerService("No relevant information found for the requested query.")
    chunks = [
        RetrievedChunk(
            document_id=UUID("11111111-1111-7111-8111-111111111111"),
            chunk_id=UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
            filename="mock.pdf",
            content="First evidence chunk",
            similarity_score=0.90,
        ),
        RetrievedChunk(
            document_id=UUID("22222222-2222-7222-8222-222222222222"),
            chunk_id=UUID("bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb"),
            filename="mock.pdf",
            content="Second evidence chunk",
            similarity_score=0.60,
        ),
        RetrievedChunk(
            document_id=UUID("33333333-3333-7333-8333-333333333333"),
            chunk_id=UUID("cccccccc-cccc-7ccc-8ccc-cccccccccccc"),
            filename="mock.pdf",
            content="Third evidence chunk",
            similarity_score=0.30,
        ),
    ]

    result = service.synthesize(retrieved_chunks=chunks)
    # Multi-factor confidence: top=0.9, avg_top3=0.6, source_bonus=1/3, agreement, spread
    # Scores: [0.9, 0.6, 0.3] → top=0.9, avg_top3=0.6, 1 unique doc → source_bonus=1/3
    # variance=(0.06), agreement=max(0,1-0.6)=0.4, spread=0.6, spread_factor=0.4
    # raw = 0.40*0.9 + 0.25*0.6 + 0.15*0.333 + 0.10*0.4 + 0.10*0.4 = 0.74
    assert abs(result.confidence - 0.74) < 0.01  # Allow small rounding tolerance
    assert len(result.citations) == 3
    assert result.citations[0].chunk_id == "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"
