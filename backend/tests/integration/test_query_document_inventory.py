from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from sqlalchemy import text

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.db.session import get_session_factory, set_db_tenant_context
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.collection import (
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
)
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.models.ingestion.ingestion_job import IngestionJob
from app.providers.services.types import ProviderSelectionCandidate
from app.services.query.answer_service import AnswerResult
from app.services.query.query_service import QueryService
from tests.conftest import SeededUser, _generate_test_collection_code


def _seed_documents(*, tenant_id, user_id, filenames: list[str]) -> None:
    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, tenant_id)
        for index, filename in enumerate(filenames, start=1):
            document_id = generate_uuid7_with_fallback()
            chunk_id = generate_uuid7_with_fallback()
            session.add(
                Document(
                    id=document_id,
                    tenant_id=tenant_id,
                    uploaded_by_user_id=user_id,
                    filename=filename,
                    content_type="application/pdf",
                    size_bytes=1024 * index,
                    sha256_hash=f"{index:064x}",
                    storage_bucket="tenant-bucket",
                    storage_object_key=f"{index}/{filename}",
                    status="indexed",
                    processing_progress=100,
                )
            )
            session.flush()
            session.add(
                DocumentChunk(
                    id=chunk_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_index=0,
                    content=f"content for {filename}",
                    char_start=0,
                    char_end=20,
                    chunk_metadata={"mode": "text"},
                )
            )
            session.flush()
            session.add(
                ChunkEmbedding(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    embedding=[0.0] * get_settings().embedding_dimension,
                    provider="sentence-transformers",
                    model="BAAI/bge-small-en-v1.5",
                )
            )
            session.add(
                IngestionJob(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=tenant_id,
                    document_id=document_id,
                    status="indexed",
                    attempt_count=1,
                    max_attempts=3,
                )
            )
        session.commit()
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


@contextmanager
def _patch_inventory_llm(service: QueryService):
    def _fake_synthesize(_self, **kwargs):
        content = kwargs["retrieved_chunks"][0].content
        marker = "Grounded workspace facts:\n"
        answer = content.split(marker, 1)[1].strip() if marker in content else content
        return AnswerResult(
            answer=answer,
            confidence=1.0,
            citations=[],
            usage={},
            provider_type="lmstudio",
            model_name="mistralai/ministral-3-3b",
            provider_source="tenant",
        )

    candidate = ProviderSelectionCandidate(
        provider_type="lmstudio",
        model_name="mistralai/ministral-3-3b",
        feature_scope="chat",
        source="tenant",
        provider_config_id=None,
        base_url="http://host.docker.internal:1234/v1",
        api_key=None,
        metadata={},
    )

    with (
        patch.object(
            type(service.provider_selection),
            "resolve_chat",
            return_value=SimpleNamespace(candidates=[candidate]),
        ),
        patch.object(type(service.answer), "synthesize", _fake_synthesize),
    ):
        yield


def test_query_inventory_questions_use_document_catalog_not_chunk_retrieval(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-inventory",
        "admin@tenant-query-inventory.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "2312.00752v2.pdf",
            "2401.09417v3.pdf",
            "2401.13660v3.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-inventory",
        )

        with _patch_inventory_llm(service):
            result = service.execute(
                auth=auth,
                query_text="Which documents do you have?",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
                conversation_id=None,
                search_mode="hybrid",
            )

        answer = str(result.answer)
        assert "You currently have 3 documents in this workspace." in answer
        assert "2312.00752v2.pdf" in answer
        assert "2401.09417v3.pdf" in answer
        assert "2401.13660v3.pdf" in answer
        assert result.citations == []
        assert result.confidence == 1.0
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


@contextmanager
def _metadata_inventory_context(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
):
    seeded = seed_user(
        "tenant-query-metadata",
        "admin@tenant-query-metadata.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "alpha-report.pdf",
            "beta-analysis.pdf",
            "gamma-notes.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        latest_doc = session.query(Document).filter_by(filename="gamma-notes.pdf").one()
        latest_doc.status = "failed"
        latest_doc.processing_progress = 40
        session.commit()

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-metadata",
        )
        yield session, service, auth
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_query_metadata_last_uploaded_document(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _metadata_inventory_context(seed_user) as (_, service, auth):
        latest_answer = _execute_inventory_question(
            service, auth, "Which document was uploaded last?"
        )
    assert "gamma-notes.pdf" in latest_answer


def test_query_metadata_status_breakdown(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _metadata_inventory_context(seed_user) as (_, service, auth):
        status_answer = _execute_inventory_question(
            service, auth, "Which documents are indexed vs failed?"
        )
    assert "- indexed: 2" in status_answer
    assert "- failed: 1" in status_answer


def test_query_metadata_embedder_listing(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _metadata_inventory_context(seed_user) as (_, service, auth):
        embedder_answer = _execute_inventory_question(
            service, auth, "Which embedding model was used per document?"
        )
    assert "sentence-transformers / BAAI/bge-small-en-v1.5" in embedder_answer


def test_query_metadata_storage_summary(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _metadata_inventory_context(seed_user) as (_, service, auth):
        storage_answer = _execute_inventory_question(
            service, auth, "What is the total storage used by my documents?"
        )
    assert "Total storage used by 3 documents:" in storage_answer


def test_query_metadata_filename_filter_answer(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _metadata_inventory_context(seed_user) as (_, service, auth):
        filter_answer = _execute_inventory_question(
            service, auth, 'Show documents named "beta"'
        )
    assert "beta-analysis.pdf" in filter_answer
    assert "alpha-report.pdf" not in filter_answer


def test_title_inside_pdf_question_does_not_route_to_inventory_metadata(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-content-title",
        "admin@tenant-query-content-title.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=["2401.13660v3.pdf"],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())

        assert (
            service._is_document_inventory_query(
                "what is the title of pdf content inside"
            )
            is False
        )
        assert (
            service._is_document_inventory_query("what is the title inside the pdf")
            is False
        )
        assert (
            service._should_route_to_document_inventory(
                query_text="tell me about table : relative training flops by model size",
                document_ids=[generate_uuid7_with_fallback()],
            )
            is False
        )
        assert (
            service._should_route_to_document_inventory(
                query_text="explain the line from the selected pdf",
                document_ids=[generate_uuid7_with_fallback()],
            )
            is False
        )
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_selected_document_scope_prefers_content_but_allows_explicit_metadata(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-selected-doc-routing",
        "admin@tenant-query-selected-doc-routing.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=["alpha-report.pdf"],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-selected-doc-routing",
        )
        document = session.query(Document).filter_by(filename="alpha-report.pdf").one()

        assert (
            service._maybe_build_document_inventory_answer(
                auth=auth,
                query_text="Tell me about table : Relative training FLOPs by model size",
                document_ids=[document.id],
                created_at_from=None,
                created_at_to=None,
            )
            is None
        )

        metadata_answer = service._maybe_build_document_inventory_answer(
            auth=auth,
            query_text="What is the embedding model used for this selected document?",
            document_ids=[document.id],
            created_at_from=None,
            created_at_to=None,
        )

        assert metadata_answer is not None
        assert "sentence-transformers / BAAI/bge-small-en-v1.5" in metadata_answer
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_heading_subheading_query_uses_outline_grounding_not_inventory(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-outline",
        "admin@tenant-query-outline.example",
        "StrongPass!1234",
        ("admin",),
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        document_id = generate_uuid7_with_fallback()
        session.add(
            Document(
                id=document_id,
                tenant_id=seeded.tenant_id,
                uploaded_by_user_id=seeded.user_id,
                filename="2401.13660v3.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256_hash=f"{1:064x}",
                storage_bucket="tenant-bucket",
                storage_object_key="1/2401.13660v3.pdf",
                status="indexed",
                processing_progress=100,
            )
        )
        session.flush()
        for idx, content in enumerate(
            [
                "Published as a conference paper at COLM 2024\nMambaByte: Token-free Selective State Space Model\n1 Introduction",
                "2 State space models and the Mamba architecture\n3 Experiments\n4 Conclusion",
            ]
        ):
            chunk_id = generate_uuid7_with_fallback()
            session.add(
                DocumentChunk(
                    id=chunk_id,
                    tenant_id=seeded.tenant_id,
                    document_id=document_id,
                    chunk_index=idx,
                    content=content,
                    char_start=0,
                    char_end=len(content),
                    chunk_metadata={"mode": "text"},
                )
            )
            session.flush()
            session.add(
                ChunkEmbedding(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=seeded.tenant_id,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    embedding=[0.0] * get_settings().embedding_dimension,
                    provider="sentence-transformers",
                    model="BAAI/bge-small-en-v1.5",
                )
            )
        session.commit()

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-outline",
        )

        with _patch_inventory_llm(service):
            result = service.execute(
                auth=auth,
                query_text="show me all headings subheading of documents",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
                conversation_id=None,
                search_mode="hybrid",
            )

        answer = str(result.answer)
        assert "MambaByte: Token-free Selective State Space Model" in answer
        assert "1 Introduction" in answer
        assert "2 State space models and the Mamba architecture" in answer
        assert "4 Conclusion" in answer
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_batched_inventory_questions_are_answered_line_by_line(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-batch",
        "admin@tenant-query-batch.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "2312.00752v2.pdf",
            "2401.09417v3.pdf",
            "2401.13660v3.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-batch",
        )

        with _patch_inventory_llm(service):
            answer = str(
                service.execute(
                    auth=auth,
                    query_text="\n".join(
                        [
                            "How many documents do you have?",
                            "Which documents do you have?",
                            'Show documents named "alpha".',
                        ]
                    ),
                    top_k=5,
                    filters={},
                    document_ids=None,
                    created_at_from=None,
                    created_at_to=None,
                    source_types=None,
                    min_extraction_coverage=None,
                    max_extraction_coverage=None,
                    conversation_id=None,
                    search_mode="hybrid",
                ).answer
            )

        assert "Q: How many documents do you have?" in answer
        assert "You currently have 3 documents in this workspace." in answer
        assert "Q: Which documents do you have?" in answer
        assert "2312.00752v2.pdf" in answer
        assert 'Q: Show documents named "alpha".' in answer
        assert 'No documents matched the filename filter "alpha".' in answer
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_named_filter_no_match_returns_natural_no_match_response(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-nomatch",
        "admin@tenant-query-nomatch.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "2312.00752v2.pdf",
            "2401.09417v3.pdf",
            "2401.13660v3.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-nomatch",
        )

        with _patch_inventory_llm(service):
            no_match_answer = str(
                service.execute(
                    auth=auth,
                    query_text='Show documents named "alpha".',
                    top_k=5,
                    filters={},
                    document_ids=None,
                    created_at_from=None,
                    created_at_to=None,
                    source_types=None,
                    min_extraction_coverage=None,
                    max_extraction_coverage=None,
                    conversation_id=None,
                    search_mode="hybrid",
                ).answer
            )
        assert 'No documents matched the filename filter "alpha".' in no_match_answer
        assert (
            "You currently have no available documents in this workspace."
            not in no_match_answer
        )

        with _patch_inventory_llm(service):
            fallback_answer = str(
                service.execute(
                    auth=auth,
                    query_text='Show documents named "mamba". If not, what documents do we have?',
                    top_k=5,
                    filters={},
                    document_ids=None,
                    created_at_from=None,
                    created_at_to=None,
                    source_types=None,
                    min_extraction_coverage=None,
                    max_extraction_coverage=None,
                    conversation_id=None,
                    search_mode="hybrid",
                ).answer
            )
        assert 'No documents matched the filename filter "mamba".' in fallback_answer
        assert "You currently have 3 documents in this workspace." in fallback_answer
        assert "2312.00752v2.pdf" in fallback_answer
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_inventory_questions_use_llm_grounding_when_chat_provider_exists(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-grounded-llm",
        "admin@tenant-query-grounded-llm.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "2312.00752v2.pdf",
            "2401.09417v3.pdf",
            "2401.13660v3.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-grounded-llm",
        )

        captured_synthesize_kwargs: dict[str, Any] = {}

        def _fake_synthesize(_self, **kwargs):
            captured_synthesize_kwargs.update(kwargs)
            return AnswerResult(
                answer=(
                    'No documents matched "mamba". '
                    "The available documents are 2312.00752v2.pdf, 2401.09417v3.pdf, and 2401.13660v3.pdf."
                ),
                confidence=0.94,
                citations=[],
                usage={},
                provider_type="lmstudio",
                model_name="mistralai/ministral-3-3b",
                provider_source="tenant",
            )

        with (
            patch.object(
                type(service.provider_selection),
                "resolve_chat",
                return_value=SimpleNamespace(
                    candidates=[
                        ProviderSelectionCandidate(
                            provider_type="lmstudio",
                            model_name="mistralai/ministral-3-3b",
                            feature_scope="chat",
                            source="tenant",
                            provider_config_id=None,
                            base_url="http://host.docker.internal:1234/v1",
                            api_key=None,
                            metadata={},
                        )
                    ]
                ),
            ),
            patch.object(type(service.answer), "synthesize", _fake_synthesize),
        ):
            result = service.execute(
                auth=auth,
                query_text='Show documents named "mamba". If not, what documents do we have?',
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
                conversation_id=None,
                search_mode="hybrid",
            )

        answer = str(result.answer)
        assert 'No documents matched "mamba".' in answer
        assert "2312.00752v2.pdf" in answer
        assert captured_synthesize_kwargs
        assert (
            "workspace metadata snapshot"
            in captured_synthesize_kwargs["retrieved_chunks"][0].content.lower()
        )
        assert (
            "workspace metadata snapshot only"
            in captured_synthesize_kwargs["query_text"].lower()
        )
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_inventory_questions_fall_back_to_grounded_system_answer_without_chat_provider(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-query-grounded-fallback",
        "admin@tenant-query-grounded-fallback.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "2312.00752v2.pdf",
            "2401.09417v3.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-grounded-fallback",
        )

        with patch.object(
            type(service.provider_selection),
            "resolve_chat",
            return_value=SimpleNamespace(candidates=[]),
        ):
            result = service.execute(
                auth=auth,
                query_text="How many documents do we have? Give me full details separately.",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
                conversation_id=None,
                search_mode="hybrid",
            )

        answer = str(result.answer)
        assert "You currently have 2 documents in this workspace." in answer
        assert "2312.00752v2.pdf" in answer
        assert "2401.09417v3.pdf" in answer
        assert result.confidence == 1.0
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def test_broad_inventory_prompt_with_about_them_does_not_trigger_content_filter(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _metadata_inventory_context(seed_user) as (_, service, auth):
        with patch.object(
            type(service.provider_selection),
            "resolve_chat",
            return_value=SimpleNamespace(candidates=[]),
        ):
            answer = str(
                service.execute(
                    auth=auth,
                    query_text=(
                        "how many documents do we have, give me full end to end information "
                        "about them and what they have, make sure i need information separately"
                    ),
                    top_k=5,
                    filters={},
                    document_ids=None,
                    created_at_from=None,
                    created_at_to=None,
                    source_types=None,
                    min_extraction_coverage=None,
                    max_extraction_coverage=None,
                    conversation_id=None,
                    search_mode="hybrid",
                ).answer
            )

    assert "No documents in the current filtered set matched" not in answer
    assert "alpha-report.pdf" in answer
    assert "beta-analysis.pdf" in answer


@contextmanager
def _advanced_inventory_context(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
):
    seeded = seed_user(
        "tenant-query-advanced",
        "admin@tenant-query-advanced.example",
        "StrongPass!1234",
        ("admin",),
    )
    _seed_documents(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        filenames=[
            "alpha-report.pdf",
            "beta-analysis.pdf",
            "gamma-notes.pdf",
        ],
    )

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)

        docs = {
            doc.filename: doc
            for doc in session.query(Document)
            .filter_by(tenant_id=seeded.tenant_id)
            .all()
        }
        jobs = {
            job.document_id: job
            for job in session.query(IngestionJob)
            .filter_by(tenant_id=seeded.tenant_id)
            .all()
        }
        chunks = {
            chunk.document_id: chunk
            for chunk in session.query(DocumentChunk)
            .filter_by(tenant_id=seeded.tenant_id)
            .all()
        }

        alpha = docs["alpha-report.pdf"]
        alpha.extraction_ocr_used = True
        alpha.extraction_method = "ocr_pipeline"
        alpha.extraction_coverage_score = 0.91
        alpha.information_yield = 96.0
        alpha.processing_progress = 100

        beta = docs["beta-analysis.pdf"]
        beta.status = "failed"
        beta.processing_progress = 45
        beta.extraction_coverage_score = 0.34
        beta.information_yield = 42.0
        beta.quarantined = True
        beta.extraction_warnings = ["Sparse extractable text", "Low parser confidence"]
        jobs[beta.id].status = "failed"
        jobs[beta.id].attempt_count = 2
        jobs[beta.id].max_attempts = 3
        jobs[beta.id].last_error_code = "EMBEDDING_PROVIDER_UNAVAILABLE"
        jobs[beta.id].last_error_message = "Embedding backend timed out while indexing."
        chunks[beta.id].content = (
            "beta analysis discusses retrieval failures and chunk drift"
        )

        gamma = docs["gamma-notes.pdf"]
        gamma.extraction_vision_used = True
        gamma.extraction_method = "layout_vision"
        gamma.extraction_coverage_score = 0.44
        gamma.information_yield = 68.0
        gamma.extraction_warnings = ["Layout blocks were incomplete"]
        chunks[gamma.id].content = (
            "gamma notes mention adaptive retrieval and evaluation"
        )

        research_collection = DocumentCollection(
            id=generate_uuid7_with_fallback(),
            tenant_id=seeded.tenant_id,
            name="Research",
            description="Research source papers",
            connection_code=_generate_test_collection_code(),
        )
        session.add(research_collection)
        session.flush()
        session.add(
            CollectionDocument(
                collection_id=research_collection.id,
                document_id=alpha.id,
            )
        )
        session.add(
            CollectionDocument(
                collection_id=research_collection.id,
                document_id=gamma.id,
            )
        )
        session.add(
            CollectionPermission(
                collection_id=research_collection.id,
                user_id=seeded.user_id,
                role="owner",
            )
        )
        ops_collection = DocumentCollection(
            id=generate_uuid7_with_fallback(),
            tenant_id=seeded.tenant_id,
            name="Operations",
            description="Operational notes",
            connection_code=_generate_test_collection_code(),
        )
        session.add(ops_collection)
        session.flush()
        session.add(
            CollectionDocument(
                collection_id=ops_collection.id,
                document_id=beta.id,
            )
        )
        session.add(
            CollectionPermission(
                collection_id=ops_collection.id,
                user_id=seeded.user_id,
                role="owner",
            )
        )
        session.commit()

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-query-advanced",
        )
        yield session, service, auth
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
        session.close()


def _execute_inventory_question(
    service: QueryService, auth: AuthContext, query_text: str
) -> str:
    with _patch_inventory_llm(service):
        result = service.execute(
            auth=auth,
            query_text=query_text,
            top_k=5,
            filters={},
            document_ids=None,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            conversation_id=None,
            search_mode="hybrid",
        )
    return str(result.answer)


def test_query_advanced_document_intelligence_collections_and_failures(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _advanced_inventory_context(seed_user) as (_, service, auth):
        collection_answer = _execute_inventory_question(
            service, auth, 'Which documents are in collection "Research"?'
        )
        failure_answer = _execute_inventory_question(
            service, auth, 'Why did document named "beta-analysis" fail?'
        )

    assert 'Documents in collection "Research":' in collection_answer
    assert "alpha-report.pdf" in collection_answer
    assert "gamma-notes.pdf" in collection_answer
    assert "beta-analysis.pdf" not in collection_answer
    assert "beta-analysis.pdf (failed)" in failure_answer
    assert "EMBEDDING_PROVIDER_UNAVAILABLE" in failure_answer
    assert "Embedding backend timed out while indexing." in failure_answer


def test_query_advanced_document_intelligence_ocr_answer(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _advanced_inventory_context(seed_user) as (_, service, auth):
        ocr_answer = _execute_inventory_question(
            service, auth, "Which documents use OCR?"
        )
    assert "alpha-report.pdf (OCR)" in ocr_answer
    assert "coverage 91%" in ocr_answer


def test_query_advanced_document_intelligence_quality_answer(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _advanced_inventory_context(seed_user) as (_, service, auth):
        quality_answer = _execute_inventory_question(
            service, auth, "Which documents are low quality?"
        )
    assert "beta-analysis.pdf: quarantined, yield 42%, coverage 34%" in quality_answer
    assert "gamma-notes.pdf: yield 68%, coverage 44%" in quality_answer


def test_query_advanced_document_intelligence_failed_chunk_drift_answer(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _advanced_inventory_context(seed_user) as (_, service, auth):
        mixed_answer = _execute_inventory_question(
            service, auth, 'Which failed documents mention "chunk drift"?'
        )
    assert 'Documents matching "chunk drift"' in mixed_answer
    assert "beta-analysis.pdf (failed)" in mixed_answer
    assert "Evidence" in mixed_answer
    assert "alpha-report.pdf" not in mixed_answer


def test_query_advanced_document_intelligence_model_filtered_answer(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _advanced_inventory_context(seed_user) as (_, service, auth):
        model_filtered_answer = _execute_inventory_question(
            service,
            auth,
            "Which indexed documents use embedding model BAAI/bge-small-en-v1.5?",
        )
    assert "- indexed: 2" in model_filtered_answer
    assert "alpha-report.pdf" in model_filtered_answer
    assert "gamma-notes.pdf" in model_filtered_answer
    assert "beta-analysis.pdf" not in model_filtered_answer


def test_query_advanced_document_intelligence_comparison_and_collections(
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    with _advanced_inventory_context(seed_user) as (_, service, auth):
        comparison_answer = _execute_inventory_question(
            service, auth, "Compare alpha-report.pdf vs gamma-notes.pdf"
        )
        collection_summary = _execute_inventory_question(
            service, auth, 'Summarize collection "Research"'
        )
        best_collection_answer = _execute_inventory_question(
            service,
            auth,
            'Which collection has the strongest coverage for "adaptive retrieval"?',
        )

    assert "Compared 2 documents across content evidence" in comparison_answer
    assert "Healthiest overall:" in comparison_answer
    assert "Most at risk:" in comparison_answer
    assert "alpha-report.pdf: status indexed" in comparison_answer
    assert "gamma-notes.pdf: status indexed" in comparison_answer
    assert 'Collection summary for "Research":' in collection_summary
    assert "Average document health:" in collection_summary
    assert "alpha-report.pdf" in collection_summary
    assert "gamma-notes.pdf" in collection_summary
    assert (
        'The strongest collection for "adaptive retrieval" is Research.'
        in best_collection_answer
    )
    assert "Runner-up: Operations" in best_collection_answer
