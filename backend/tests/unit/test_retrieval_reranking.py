from __future__ import annotations

from app.core.ids import generate_uuid7_with_fallback
from app.documents.repositories.chunks import RetrievedChunkRow
from app.query.services.retrieval_service import RetrievalService, RetrievedChunk


def _row(index: int, text: str, score: float) -> RetrievedChunkRow:
    document_id = generate_uuid7_with_fallback()
    return RetrievedChunkRow(
        document_id=document_id,
        chunk_id=generate_uuid7_with_fallback(),
        filename="doc.pdf",
        content=text,
        similarity_score=score,
        chunk_index=index,
    )


def test_retrieval_service_applies_reranker_after_hybrid_fusion(
    settings, monkeypatch, db_session
) -> None:
    service = RetrievalService(db_session, settings)
    settings.reranking_top_k_answer = 2
    settings.reranking_top_k_rerank = 2
    settings.reranking_top_k_retrieve = 2

    accessible_doc_id = generate_uuid7_with_fallback()
    vector_rows = [
        RetrievedChunkRow(
            document_id=accessible_doc_id,
            chunk_id=generate_uuid7_with_fallback(),
            filename="doc.pdf",
            content="vector first",
            similarity_score=0.9,
            chunk_index=0,
        ),
        RetrievedChunkRow(
            document_id=accessible_doc_id,
            chunk_id=generate_uuid7_with_fallback(),
            filename="doc.pdf",
            content="vector second",
            similarity_score=0.7,
            chunk_index=1,
        ),
    ]

    monkeypatch.setattr(
        service.documents,
        "get_accessible_document_ids_global",
        lambda **_: {accessible_doc_id},
    )
    monkeypatch.setattr(service.embeddings, "embed_many", lambda *_, **__: [[0.1] * 384])
    monkeypatch.setattr(
        service.chunks,
        "search_top_k_global",
        lambda **_: list(vector_rows),
    )
    monkeypatch.setattr(
        service.chunks,
        "search_bm25_global",
        lambda **_: list(vector_rows),
    )
    monkeypatch.setattr(
        service,
        "_expand_and_cluster",
        lambda base_results: [
            RetrievedChunk(
                document_id=row.document_id,
                chunk_id=row.chunk_id,
                filename=row.filename,
                content=row.content,
                similarity_score=row.similarity_score,
            )
            for row in base_results
        ],
    )

    def _fake_rerank(**kwargs):  # type: ignore[no-untyped-def]
        reordered = [kwargs["chunks"][1], kwargs["chunks"][0]]
        return type(
            "_Result",
            (),
            {
                "chunks": reordered,
                "metadata": type(
                    "_Meta",
                    (),
                    {
                        "applied": True,
                        "provider": "sentence-transformers",
                        "model": "BAAI/bge-reranker-v2-m3",
                        "latency_ms": 12.0,
                        "candidate_count": len(kwargs["chunks"]),
                        "selected_count": len(reordered),
                        "failure_reason": None,
                    },
                )(),
            },
        )()

    monkeypatch.setattr(service.reranker, "rerank_chunks", _fake_rerank)

    results = service.retrieve(
        tenant_id=generate_uuid7_with_fallback(),
        user_id=generate_uuid7_with_fallback(),
        query="best result",
        top_k=2,
        document_ids=[accessible_doc_id],
        created_at_from=None,
        created_at_to=None,
        source_types=None,
        min_extraction_coverage=None,
        max_extraction_coverage=None,
        search_mode="hybrid",
        trace=None,
    )

    assert [row.content for row in results] == ["vector second", "vector first"]


def test_retrieval_service_uses_adaptive_depth_plan_for_broad_queries(
    settings, monkeypatch, db_session
) -> None:
    service = RetrievalService(db_session, settings)
    settings.reranking_top_k_answer = 5
    settings.reranking_top_k_rerank = 8
    settings.reranking_top_k_retrieve = 12
    settings.query_top_k_max = 25

    accessible_doc_id = generate_uuid7_with_fallback()
    vector_rows = [_row(index, f"vector {index}", 0.9 - (index * 0.01)) for index in range(30)]
    search_top_ks: list[int] = []
    rerank_inputs: list[dict[str, int]] = []

    monkeypatch.setattr(
        service.documents,
        "get_accessible_document_ids_global",
        lambda **_: {accessible_doc_id},
    )
    monkeypatch.setattr(service.embeddings, "embed_many", lambda *_, **__: [[0.1] * 384])

    def _fake_search_top_k(**kwargs):  # type: ignore[no-untyped-def]
        search_top_ks.append(kwargs["top_k"])
        return list(vector_rows[: kwargs["top_k"]])

    monkeypatch.setattr(service.chunks, "search_top_k_global", _fake_search_top_k)
    monkeypatch.setattr(service.chunks, "search_bm25_global", lambda **_: [])
    monkeypatch.setattr(
        service,
        "_expand_and_cluster",
        lambda base_results: [
            RetrievedChunk(
                document_id=row.document_id,
                chunk_id=row.chunk_id,
                filename=row.filename,
                content=row.content,
                similarity_score=row.similarity_score,
            )
            for row in base_results
        ],
    )

    def _fake_rerank(**kwargs):  # type: ignore[no-untyped-def]
        rerank_inputs.append(
            {
                "candidate_count": len(kwargs["chunks"]),
                "top_n": kwargs["top_n"],
            }
        )
        return type(
            "_Result",
            (),
            {
                "chunks": list(kwargs["chunks"][: kwargs["top_n"]]),
                "metadata": type(
                    "_Meta",
                    (),
                    {
                        "applied": True,
                        "provider": "sentence-transformers",
                        "model": "BAAI/bge-reranker-v2-m3",
                        "latency_ms": 7.0,
                        "candidate_count": len(kwargs["chunks"]),
                        "selected_count": kwargs["top_n"],
                        "failure_reason": None,
                    },
                )(),
            },
        )()

    monkeypatch.setattr(service.reranker, "rerank_chunks", _fake_rerank)

    results = service.retrieve(
        tenant_id=generate_uuid7_with_fallback(),
        user_id=generate_uuid7_with_fallback(),
        query="Compare and synthesize the main differences across these documents",
        top_k=5,
        document_ids=[accessible_doc_id],
        created_at_from=None,
        created_at_to=None,
        source_types=None,
        min_extraction_coverage=None,
        max_extraction_coverage=None,
        search_mode="semantic",
        trace=None,
    )

    assert search_top_ks == [22]
    assert rerank_inputs == [{"candidate_count": 17, "top_n": 9}]
    assert len(results) == 9
