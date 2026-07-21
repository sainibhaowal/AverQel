import uuid

import pytest

from app.db.session import get_session_factory
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.documents.repositories.chunks import ChunksRepository
from app.services.query.retrieval_service import RetrievalService


@pytest.fixture
def db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def test_hybrid_search_rrf(db_session, settings, seed_user):
    user_data = seed_user("Hybrid Tenant", "hybrid@example.com", "pass", ("reader",))
    RetrievalService(db_session, settings)

    # 1. Create mock chunks
    # Chunk A: Semantic match for "Technical" (we'll mock embedding eventually or just check logic)
    # Chunk B: Keyword match for "Proprietary"

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        tenant_id=user_data.tenant_id,
        uploaded_by_user_id=user_data.user_id,
        filename="test_doc.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256_hash="f" * 64,
        storage_bucket="test-bucket",
        storage_object_key="test-key",
        status="completed",
        extraction_coverage_score=1.0,
    )
    db_session.add(doc)
    db_session.flush()

    chunk1 = DocumentChunk(
        id=uuid.uuid4(),
        tenant_id=user_data.tenant_id,
        document_id=doc_id,
        chunk_index=0,
        content="This is a technical document about proprietary systems.",
        char_start=0,
        char_end=50,
        chunk_metadata={"mode": "text"},
    )
    db_session.add(chunk1)
    db_session.commit()

    # 2. Verify keyword search directly
    repo = ChunksRepository(db_session)
    results = repo.search_bm25(
        tenant_id=user_data.tenant_id,
        query="proprietary",
        top_k=5,
        document_ids=None,
        created_at_from=None,
        created_at_to=None,
        source_types=None,
        min_extraction_coverage=None,
        max_extraction_coverage=None,
    )

    assert len(results) > 0
    assert "proprietary" in results[0].content.lower()


def test_structural_section_queries_prioritize_exact_unit_hits(
    db_session, settings, seed_user
):
    user_data = seed_user("Section Tenant", "section@example.com", "pass", ("reader",))
    service = RetrievalService(db_session, settings)

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        tenant_id=user_data.tenant_id,
        uploaded_by_user_id=user_data.user_id,
        filename="course-book.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        sha256_hash="a" * 64,
        storage_bucket="test-bucket",
        storage_object_key="course-book.pdf",
        status="indexed",
        extraction_coverage_score=1.0,
    )
    db_session.add(doc)
    db_session.flush()

    chunks = [
        DocumentChunk(
            id=uuid.uuid4(),
            tenant_id=user_data.tenant_id,
            document_id=doc_id,
            chunk_index=0,
            content="Introduction to the course book.",
            char_start=0,
            char_end=32,
            chunk_metadata={"mode": "ocr"},
        ),
        DocumentChunk(
            id=uuid.uuid4(),
            tenant_id=user_data.tenant_id,
            document_id=doc_id,
            chunk_index=1,
            content="Unit 2 Random Variables",
            char_start=33,
            char_end=58,
            chunk_metadata={"mode": "ocr"},
        ),
        DocumentChunk(
            id=uuid.uuid4(),
            tenant_id=user_data.tenant_id,
            document_id=doc_id,
            chunk_index=2,
            content="UNIT 2 RANDOM VARIABLES STUDY GOALS explain discrete and continuous variables.",
            char_start=59,
            char_end=142,
            chunk_metadata={"mode": "ocr"},
        ),
        DocumentChunk(
            id=uuid.uuid4(),
            tenant_id=user_data.tenant_id,
            document_id=doc_id,
            chunk_index=3,
            content="Unit 5 Inequalities and Limit Theorems",
            char_start=143,
            char_end=183,
            chunk_metadata={"mode": "ocr"},
        ),
    ]
    db_session.add_all(chunks)
    db_session.commit()

    results = service.retrieve(
        tenant_id=user_data.tenant_id,
        user_id=user_data.user_id,
        query="Explain Unit 2 from this selected document",
        top_k=5,
        document_ids=[doc_id],
        created_at_from=None,
        created_at_to=None,
        source_types=None,
        min_extraction_coverage=None,
        max_extraction_coverage=None,
        search_mode="hybrid",
        trace=None,
    )

    assert results
    primary_text = results[0].content.lower()
    assert "unit 2" in primary_text
    assert "random variables" in primary_text
