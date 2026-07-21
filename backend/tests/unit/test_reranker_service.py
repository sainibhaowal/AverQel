from __future__ import annotations

from app.core.ids import generate_uuid7_with_fallback
from app.db.session import set_db_tenant_context
from app.auth.models.tenant import Tenant
from app.repositories.documents.chunks import RetrievedChunkRow
from app.providers.services.registry import ProviderRegistry
from app.providers.services.selection_service import ProviderSelectionService
from app.providers.services.types import (
    ProviderSelectionCandidate,
    ProviderSelectionResult,
    RerankResponse,
    RerankResultItem,
)
from app.services.query.reranker_service import RerankerService


def _chunk(index: int, text: str, score: float) -> RetrievedChunkRow:
    from app.core.ids import generate_uuid7_with_fallback

    return RetrievedChunkRow(
        document_id=generate_uuid7_with_fallback(),
        chunk_id=generate_uuid7_with_fallback(),
        filename=f"doc-{index}.pdf",
        content=text,
        similarity_score=score,
        chunk_index=index,
    )


def test_reranker_service_reorders_chunks(settings, monkeypatch, db_session) -> None:
    tenant_id = generate_uuid7_with_fallback()
    db_session.add(Tenant(id=tenant_id, name="Reranker Tenant"))
    db_session.flush()
    set_db_tenant_context(db_session, tenant_id)
    service = RerankerService(db_session, settings)
    selection = ProviderSelectionResult(
        feature_scope="reranking",
        candidates=[
            ProviderSelectionCandidate(
                provider_type="sentence-transformers",
                model_name="BAAI/bge-reranker-v2-m3",
                feature_scope="reranking",
                source="env_fallback",
            )
        ],
    )
    monkeypatch.setattr(
        ProviderSelectionService,
        "resolve_reranking",
        lambda self, **_: selection,
    )

    class _FakeReranker:
        def rerank(self, request):  # type: ignore[no-untyped-def]
            assert request.documents[0] == "candidate a"
            return RerankResponse(
                results=[
                    RerankResultItem(index=1, score=0.98),
                    RerankResultItem(index=0, score=0.45),
                ]
            )

    monkeypatch.setattr(
        ProviderRegistry,
        "get_reranker_provider_from_selection",
        lambda self, _: _FakeReranker(),
    )

    result = service.rerank_chunks(
        tenant_id=tenant_id,
        workspace_id=None,
        actor_user_id=None,
        query="best match",
        chunks=[
            _chunk(0, "candidate a", 0.10),
            _chunk(1, "candidate b", 0.20),
        ],
        top_n=2,
    )
    assert [chunk.content for chunk in result.chunks] == ["candidate b", "candidate a"]
    assert result.metadata.applied is True
    assert result.metadata.model == "BAAI/bge-reranker-v2-m3"


def test_reranker_service_falls_back_when_unconfigured(
    settings, monkeypatch, db_session
) -> None:
    tenant_id = generate_uuid7_with_fallback()
    db_session.add(Tenant(id=tenant_id, name="Reranker Fallback Tenant"))
    db_session.flush()
    set_db_tenant_context(db_session, tenant_id)
    service = RerankerService(db_session, settings)
    monkeypatch.setattr(
        ProviderSelectionService,
        "resolve_reranking",
        lambda self, **_: ProviderSelectionResult(
            feature_scope="reranking",
            candidates=[],
        ),
    )
    original = [_chunk(0, "alpha", 0.9), _chunk(1, "beta", 0.8)]
    result = service.rerank_chunks(
        tenant_id=tenant_id,
        workspace_id=None,
        actor_user_id=None,
        query="alpha",
        chunks=original,
        top_n=2,
    )
    assert [chunk.content for chunk in result.chunks] == ["alpha", "beta"]
    assert result.metadata.applied is False
