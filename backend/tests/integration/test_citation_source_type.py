import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services.query.answer_service import AnswerResult
from app.services.query.retrieval_service import RetrievedChunk


def test_citation_source_type_propagation(client: TestClient, seed_user):
    # 1. Seed a user with correct permissions
    user = seed_user("Test Tenant", "cite@example.com", "Password123!", ("admin",))

    # 2. Login to get token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "cite@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(user.tenant_id)}

    # 3. Mock retrieval and persistence
    mock_chunks = [
        RetrievedChunk(
            document_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            filename="mock.pdf",
            content="Text based content",
            similarity_score=0.9,
            source_type="text",
        ),
        RetrievedChunk(
            document_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            filename="mock.pdf",
            content="OCR based content",
            similarity_score=0.8,
            source_type="ocr",
        ),
    ]

    mock_query_row = MagicMock()
    mock_query_row.id = uuid.uuid4()

    with patch(
        "app.services.query.query_service.QueriesRepository.create_query",
        return_value=mock_query_row,
    ):
        with patch(
            "app.services.query.query_service.QueriesRepository.create_citations",
            return_value=None,
        ):
            with patch(
                "app.services.query.query_service.RetrievalService.retrieve",
                return_value=mock_chunks,
            ):
                with patch(
                    "app.services.query.query_service.RetrievalService.get_document_references",
                    return_value=[],
                ):
                    with patch(
                        "app.services.query.query_service.AnswerService.synthesize"
                    ) as mock_synth:
                        from app.services.query.answer_service import AnswerCitation

                        mock_synth.return_value = AnswerResult(
                            answer="Final answer",
                            confidence=0.95,
                            citations=[
                                AnswerCitation(
                                    document_id=str(mock_chunks[0].document_id),
                                    chunk_id=str(mock_chunks[0].chunk_id),
                                    filename="mock.pdf",
                                    snippet="Text snippet",
                                    similarity_score=0.9,
                                    source_type="text",
                                ),
                                AnswerCitation(
                                    document_id=str(mock_chunks[1].document_id),
                                    chunk_id=str(mock_chunks[1].chunk_id),
                                    filename="mock.pdf",
                                    snippet="OCR snippet",
                                    similarity_score=0.8,
                                    source_type="ocr",
                                ),
                            ],
                        )

                        response = client.post(
                            "/api/v1/queries",
                            headers=headers,
                            json={"query": "test query", "top_k": 5},
                        )

            assert response.status_code == 200
            data = response.json()

            assert "citations" in data
            # Check if source_type is present and correct for all citations
            source_types = [c["source_type"] for c in data["citations"]]
            assert "text" in source_types
            assert "ocr" in source_types
