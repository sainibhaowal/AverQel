from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.documents.chunks import RetrievedChunkRow
from app.providers.services import ProviderRegistry, RerankRequest
from app.providers.services.selection_service import ProviderSelectionService

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class RerankRunMetadata:
    enabled: bool
    applied: bool
    provider: str | None = None
    model: str | None = None
    source: str | None = None
    provider_config_id: uuid.UUID | None = None
    candidate_count: int = 0
    selected_count: int = 0
    latency_ms: float | None = None
    failure_reason: str | None = None
    selection_notes: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class RerankRunResult:
    chunks: list[RetrievedChunkRow]
    metadata: RerankRunMetadata


class RerankerService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.registry = ProviderRegistry(settings)
        self.selection = ProviderSelectionService(db, settings)

    def rerank_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        query: str,
        chunks: list[RetrievedChunkRow],
        top_n: int,
    ) -> RerankRunResult:
        if not self.settings.reranking_enabled or not chunks or top_n <= 0:
            return RerankRunResult(
                chunks=chunks[:top_n] if top_n > 0 else [],
                metadata=RerankRunMetadata(
                    enabled=bool(self.settings.reranking_enabled),
                    applied=False,
                    candidate_count=len(chunks),
                    selected_count=min(len(chunks), max(top_n, 0)),
                    failure_reason=(
                        None
                        if self.settings.reranking_enabled
                        else "reranking_disabled"
                    ),
                ),
            )

        if self.settings.reranking_provider == "disabled":
            return RerankRunResult(
                chunks=chunks[:top_n],
                metadata=RerankRunMetadata(
                    enabled=False,
                    applied=False,
                    candidate_count=len(chunks),
                    selected_count=min(len(chunks), top_n),
                    failure_reason="reranking_provider_disabled",
                ),
            )

        selection = self.selection.resolve_reranking(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        if not selection.candidates:
            return RerankRunResult(
                chunks=chunks[:top_n],
                metadata=RerankRunMetadata(
                    enabled=True,
                    applied=False,
                    candidate_count=len(chunks),
                    selected_count=min(len(chunks), top_n),
                    failure_reason="reranker_not_configured",
                    selection_notes=list(selection.selection_notes),
                ),
            )

        candidate = selection.candidates[0]
        provider = self.registry.get_reranker_provider_from_selection(candidate)
        started = time.perf_counter()
        try:
            response = provider.rerank(
                RerankRequest(
                    query=query,
                    documents=[chunk.content for chunk in chunks],
                    model=candidate.model_name,
                    top_n=min(top_n, len(chunks)),
                    timeout_seconds=self.settings.reranking_timeout_seconds,
                    provider_name=candidate.provider_type,
                    metadata={
                        "base_url": candidate.base_url,
                        "api_key": candidate.api_key,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reranking failed; falling back to first-stage retrieval order.",
                exc_info=True,
            )
            return RerankRunResult(
                chunks=chunks[:top_n],
                metadata=RerankRunMetadata(
                    enabled=True,
                    applied=False,
                    provider=candidate.provider_type,
                    model=candidate.model_name,
                    source=candidate.source,
                    provider_config_id=candidate.provider_config_id,
                    candidate_count=len(chunks),
                    selected_count=min(len(chunks), top_n),
                    failure_reason=type(exc).__name__,
                    selection_notes=list(selection.selection_notes),
                ),
            )

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        index_to_score = {
            item.index: float(item.score)
            for item in response.results
            if 0 <= item.index < len(chunks)
        }
        scored_rows = [
            (index, chunks[index], score) for index, score in index_to_score.items()
        ]
        scored_rows.sort(key=lambda item: item[2], reverse=True)
        reranked = [row for _, row, _ in scored_rows]
        if len(reranked) < top_n:
            reranked_ids = {row.chunk_id for row in reranked}
            reranked.extend(row for row in chunks if row.chunk_id not in reranked_ids)
        final_chunks = reranked[:top_n]
        final_chunk_ids = {row.chunk_id for row in final_chunks}
        for _, row, score in scored_rows:
            if row.chunk_id in final_chunk_ids:
                row.similarity_score = score
        return RerankRunResult(
            chunks=final_chunks,
            metadata=RerankRunMetadata(
                enabled=True,
                applied=True,
                provider=candidate.provider_type,
                model=candidate.model_name,
                source=candidate.source,
                provider_config_id=candidate.provider_config_id,
                candidate_count=len(chunks),
                selected_count=len(final_chunks),
                latency_ms=latency_ms,
                selection_notes=list(selection.selection_notes),
            ),
        )
