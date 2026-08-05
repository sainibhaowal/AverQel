from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.documents.repositories.chunks import ChunksRepository, RetrievedChunkRow
from app.documents.repositories.documents import DocumentsRepository
from app.ingestion.services.embedding_service import EmbeddingService
from app.query.services.query_classifier import QueryClassifier, QueryType
from app.query.services.reranker_service import RerankerService
from app.query.services.trace_service import TraceCollector
from app.system.services.metrics_service import QUERY_PIPELINE_DURATION_SECONDS

logger = logging.getLogger(__name__)

_STRUCTURAL_SECTION_QUERY_RE = re.compile(
    r"\b(unit|chapter|section)\s+((?:\d+(?:\.\d+)*)|(?:[ivxlcdm]+))\b",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class RetrievedChunk:
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    content: str
    similarity_score: float
    source_type: str = "text"
    section_header: str | None = None
    page_number: int | None = None


@dataclass(slots=True, frozen=True)
class RetrievalDepthPlan:
    profile: str
    answer_top_k: int
    rerank_top_k: int
    retrieve_top_k: int


class _QualityScoredRow(Protocol):
    similarity_score: float
    quality_score: float | None


class RetrievalService:
    RRF_K = 60
    HYBRID_MULTIPLIER = 2
    CLUSTER_GAP = 2
    NEIGHBOR_EXPANSION = 1
    QUALITY_BOOST_WEIGHT = 0.1
    MAX_SCORE = 1.0
    MIN_SCORE = 0.0

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.embeddings = EmbeddingService(settings, db=db)
        self.reranker = RerankerService(db, settings)
        self.chunks = ChunksRepository(db)
        self.documents = DocumentsRepository(db)

    def _observe_metric(self, segment: str, start: float) -> None:
        try:
            QUERY_PIPELINE_DURATION_SECONDS.labels(segment=segment).observe(
                time.perf_counter() - start
            )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to observe retrieval metric.", exc_info=True)

    def _rrf_combine(
        self,
        vector_results: list[RetrievedChunkRow],
        keyword_results: list[RetrievedChunkRow],
        top_k: int,
    ) -> list[RetrievedChunkRow]:
        scores: dict[uuid.UUID, float] = {}
        lookup: dict[uuid.UUID, RetrievedChunkRow] = {}

        for rank, row in enumerate(vector_results, start=1):
            scores[row.chunk_id] = scores.get(row.chunk_id, 0.0) + (1.0 / (self.RRF_K + rank))
            lookup[row.chunk_id] = row

        for rank, row in enumerate(keyword_results, start=1):
            scores[row.chunk_id] = scores.get(row.chunk_id, 0.0) + (1.0 / (self.RRF_K + rank))
            lookup.setdefault(row.chunk_id, row)

        sorted_ids = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)[
            :top_k
        ]
        max_rrf = (1.0 / (self.RRF_K + 1)) * 2

        fused: list[RetrievedChunkRow] = []
        for chunk_id in sorted_ids:
            row = lookup[chunk_id]
            fused.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=(round(scores[chunk_id] / max_rrf, 6) if max_rrf > 0 else 0.0),
                    source_type=row.source_type,
                    chunk_index=row.chunk_index,
                    section_header=row.section_header,
                    page_number=row.page_number,
                )
            )
        return fused

    def _expand_and_cluster(
        self,
        base_results: list[RetrievedChunkRow],
    ) -> list[RetrievedChunk]:
        if not base_results:
            return []

        hits_by_doc: dict[uuid.UUID, list[RetrievedChunkRow]] = {}
        for row in base_results:
            hits_by_doc.setdefault(row.document_id, []).append(row)

        final_results: list[RetrievedChunk] = []
        doc_indices: dict[uuid.UUID, list[int]] = {}

        for doc_id, hits in hits_by_doc.items():
            indices: set[int] = set()
            for hit in hits:
                for offset in range(-self.NEIGHBOR_EXPANSION, self.NEIGHBOR_EXPANSION + 1):
                    if hit.chunk_index + offset >= 0:
                        indices.add(hit.chunk_index + offset)
            doc_indices[doc_id] = sorted(indices)

        adjacent_chunks = self.chunks.get_chunks_by_indices_global(
            document_indices=doc_indices,
        )

        chunk_map: dict[tuple[uuid.UUID, int], str] = {
            (chunk.document_id, chunk.chunk_index): chunk.content for chunk in adjacent_chunks
        }

        for doc_id, hits in hits_by_doc.items():
            hits.sort(key=lambda row: row.chunk_index)
            clusters: list[list[RetrievedChunkRow]] = []
            current_cluster: list[RetrievedChunkRow] = []

            for hit in hits:
                if not current_cluster:
                    current_cluster.append(hit)
                    continue

                if hit.chunk_index <= current_cluster[-1].chunk_index + self.CLUSTER_GAP:
                    current_cluster.append(hit)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [hit]

            if current_cluster:
                clusters.append(current_cluster)

            for cluster in clusters:
                min_idx = cluster[0].chunk_index
                max_idx = cluster[-1].chunk_index

                merged_content: list[str] = []
                for idx in range(
                    min_idx - self.NEIGHBOR_EXPANSION,
                    max_idx + self.NEIGHBOR_EXPANSION + 1,
                ):
                    content = chunk_map.get((doc_id, idx))
                    if content:
                        merged_content.append(content)

                best_hit = max(cluster, key=lambda row: row.similarity_score)
                final_results.append(
                    RetrievedChunk(
                        document_id=doc_id,
                        chunk_id=best_hit.chunk_id,
                        filename=best_hit.filename,
                        content="\n\n".join(merged_content),
                        similarity_score=round(
                            max(
                                self.MIN_SCORE,
                                min(best_hit.similarity_score, self.MAX_SCORE),
                            ),
                            6,
                        ),
                        source_type=best_hit.source_type,
                        section_header=best_hit.section_header,
                        page_number=best_hit.page_number,
                    )
                )

        final_results.sort(key=lambda row: row.similarity_score, reverse=True)
        return final_results

    def _apply_quality_boost(
        self,
        results: list[_QualityScoredRow] | list[RetrievedChunkRow],
    ) -> None:
        for row in results:
            quality_score = getattr(row, "quality_score", None)
            if quality_score is None:
                continue

            boosted = row.similarity_score + (float(quality_score) * self.QUALITY_BOOST_WEIGHT)
            row.similarity_score = max(self.MIN_SCORE, min(boosted, self.MAX_SCORE))

    @staticmethod
    def _extract_structural_section_terms(query: str) -> list[str]:
        normalized_terms: list[str] = []
        seen: set[str] = set()
        for match in _STRUCTURAL_SECTION_QUERY_RE.finditer(query):
            label = match.group(1).lower()
            value = match.group(2).lower()
            term = f"{label} {value}"
            if term in seen:
                continue
            seen.add(term)
            normalized_terms.append(term)
        return normalized_terms

    def _retrieve_structural_section_hits(
        self,
        *,
        document_ids: list[uuid.UUID],
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        section_terms = self._extract_structural_section_terms(query)
        if not section_terms or not document_ids:
            return []

        exact_hits: list[RetrievedChunkRow] = []
        seen_chunk_ids: set[uuid.UUID] = set()
        per_term_limit = max(top_k, 8)

        for term in section_terms:
            for hit in self.chunks.search_document_text_global(
                document_ids=document_ids,
                query=term,
                limit=per_term_limit,
            ):
                if hit.chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(hit.chunk_id)
                exact_hits.append(hit)

        if not exact_hits:
            return []

        exact_hits.sort(key=lambda row: (row.document_id, row.chunk_index))
        return self._expand_and_cluster(exact_hits[: max(top_k, len(section_terms))])

    @staticmethod
    def _validate_search_mode(search_mode: str) -> str:
        allowed = {"semantic", "keyword", "hybrid"}
        normalized = search_mode.strip().lower()
        if normalized not in allowed:
            raise ValueError(f"search_mode must be one of {sorted(allowed)}")
        return normalized

    def _build_depth_plan(
        self,
        *,
        query: str,
        requested_top_k: int,
        search_mode: str,
        document_scope_count: int,
    ) -> RetrievalDepthPlan:
        query_type = QueryClassifier.classify(query)
        max_limit = self.settings.query_top_k_max

        if query_type in {QueryType.COMPARISON, QueryType.SYNTHESIS}:
            profile = "broad_synthesis"
            answer_top_k = 10
            rerank_top_k = 18
            retrieve_top_k = 25
        elif query_type in {QueryType.SUMMARIZATION, QueryType.EXPLORATORY}:
            profile = "exploratory"
            answer_top_k = 8
            rerank_top_k = 16
            retrieve_top_k = 24
        elif query_type == QueryType.VERIFICATION:
            profile = "verification"
            answer_top_k = 6
            rerank_top_k = 12
            retrieve_top_k = 18
        else:
            profile = "factual"
            answer_top_k = 6
            rerank_top_k = 12
            retrieve_top_k = 16

        if document_scope_count <= 1:
            answer_top_k = max(5, answer_top_k - 1)
            rerank_top_k = max(answer_top_k + 3, rerank_top_k - 2)
            retrieve_top_k = max(rerank_top_k + 2, retrieve_top_k - 4)
            profile = f"{profile}_single_document"
        elif document_scope_count >= 10:
            rerank_top_k = min(max_limit, rerank_top_k + 2)
            retrieve_top_k = min(max_limit, retrieve_top_k + 1)
            profile = f"{profile}_wide_scope"

        if search_mode == "keyword":
            answer_top_k = max(5, answer_top_k - 1)
            rerank_top_k = max(answer_top_k + 2, rerank_top_k - 2)
            retrieve_top_k = max(rerank_top_k + 2, retrieve_top_k - 2)
            profile = f"{profile}_keyword"
        elif search_mode == "semantic":
            rerank_top_k = min(max_limit, rerank_top_k + 1)
            retrieve_top_k = min(max_limit, retrieve_top_k + 1)
            profile = f"{profile}_semantic"

        answer_top_k = min(max_limit, max(self.settings.reranking_top_k_answer, answer_top_k))
        rerank_top_k = min(
            max_limit,
            max(answer_top_k, self.settings.reranking_top_k_rerank, rerank_top_k),
        )
        retrieve_top_k = min(
            max_limit,
            max(rerank_top_k, self.settings.reranking_top_k_retrieve, retrieve_top_k),
        )

        return RetrievalDepthPlan(
            profile=profile,
            answer_top_k=answer_top_k,
            rerank_top_k=rerank_top_k,
            retrieve_top_k=retrieve_top_k,
        )

    def retrieve(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        top_k: int,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
        search_mode: str = "hybrid",
        trace: TraceCollector | None = None,
    ) -> list[RetrievedChunk]:
        normalized_search_mode = self._validate_search_mode(search_mode)

        accessible_docs = self.documents.get_accessible_document_ids_global(
            user_id=user_id,
        )

        if document_ids is not None:
            final_doc_ids = list(set(document_ids) & accessible_docs)
            if not final_doc_ids and document_ids:
                return []
        else:
            final_doc_ids = list(accessible_docs)
            if not final_doc_ids:
                return []

        depth_plan = self._build_depth_plan(
            query=query,
            requested_top_k=top_k,
            search_mode=normalized_search_mode,
            document_scope_count=len(final_doc_ids),
        )
        answer_top_k = depth_plan.answer_top_k
        rerank_top_k = depth_plan.rerank_top_k
        retrieve_top_k = depth_plan.retrieve_top_k

        if trace is not None:
            trace.set_metadata(
                retrieval_depth_mode="adaptive",
                retrieval_depth_profile=depth_plan.profile,
                requested_top_k=top_k,
                effective_answer_top_k=answer_top_k,
                effective_rerank_top_k=rerank_top_k,
                effective_retrieve_top_k=retrieve_top_k,
                document_scope_count=len(final_doc_ids),
            )

        structural_hits = self._retrieve_structural_section_hits(
            document_ids=final_doc_ids,
            query=query,
            top_k=answer_top_k,
        )
        if structural_hits:
            if trace is not None:
                trace.record_retrieval(
                    searched=len(structural_hits),
                    evaluated=len(structural_hits),
                    selected=len(structural_hits),
                    rejected=0,
                    strategy="structural_section_match",
                )
                trace.set_metadata(
                    reranking_applied=False,
                    reranker_reason="structural_section_match_bypass",
                )
            return structural_hits[:answer_top_k]

        search_top_k = (
            retrieve_top_k
            if normalized_search_mode != "hybrid"
            else retrieve_top_k * self.HYBRID_MULTIPLIER
        )

        vector_results: list[RetrievedChunkRow] = []
        keyword_results: list[RetrievedChunkRow] = []

        if normalized_search_mode in {"semantic", "hybrid"}:
            embed_start = time.perf_counter()
            try:
                query_embedding = self.embeddings.embed_many([query], tenant_id=tenant_id)[0]
            except TypeError as exc:
                if "tenant_id" not in str(exc):
                    raise
                # Preserve compatibility with older test doubles patched against
                # the pre-selection embed_many(texts) signature.
                query_embedding = self.embeddings.embed_many([query])[0]
            self._observe_metric("embed_query", embed_start)

            semantic_start = time.perf_counter()
            vector_results = self.chunks.search_top_k_global(
                query_embedding=query_embedding,
                top_k=search_top_k,
                document_ids=final_doc_ids,
                created_at_from=created_at_from,
                created_at_to=created_at_to,
                source_types=source_types,
                min_extraction_coverage=min_extraction_coverage,
                max_extraction_coverage=max_extraction_coverage,
            )
            self._observe_metric("semantic_search", semantic_start)

            self._apply_quality_boost(vector_results)
            vector_results.sort(key=lambda row: row.similarity_score, reverse=True)

            if normalized_search_mode == "semantic":
                rerank_result = self.reranker.rerank_chunks(
                    tenant_id=tenant_id,
                    workspace_id=None,
                    actor_user_id=user_id,
                    query=query,
                    chunks=vector_results[:rerank_top_k],
                    top_n=answer_top_k,
                )
                expanded = self._expand_and_cluster(rerank_result.chunks)
                if trace is not None:
                    trace.record_retrieval(
                        searched=len(vector_results),
                        evaluated=len(vector_results),
                        selected=len(expanded),
                        rejected=max(0, len(vector_results) - len(expanded)),
                        strategy=normalized_search_mode,
                    )
                    trace.set_metadata(
                        reranking_applied=rerank_result.metadata.applied,
                        reranker_provider=rerank_result.metadata.provider,
                        reranker_model=rerank_result.metadata.model,
                        reranker_latency_ms=rerank_result.metadata.latency_ms,
                        reranker_candidate_count=rerank_result.metadata.candidate_count,
                        reranker_selected_count=rerank_result.metadata.selected_count,
                        reranker_failure_reason=rerank_result.metadata.failure_reason,
                    )
                return expanded

        if normalized_search_mode in {"keyword", "hybrid"}:
            keyword_start = time.perf_counter()
            keyword_results = self.chunks.search_bm25_global(
                query=query,
                top_k=search_top_k,
                document_ids=final_doc_ids,
                created_at_from=created_at_from,
                created_at_to=created_at_to,
                source_types=source_types,
                min_extraction_coverage=min_extraction_coverage,
                max_extraction_coverage=max_extraction_coverage,
            )
            self._observe_metric("keyword_search", keyword_start)

            self._apply_quality_boost(keyword_results)
            keyword_results.sort(key=lambda row: row.similarity_score, reverse=True)

            if normalized_search_mode == "keyword":
                rerank_result = self.reranker.rerank_chunks(
                    tenant_id=tenant_id,
                    workspace_id=None,
                    actor_user_id=user_id,
                    query=query,
                    chunks=keyword_results[:rerank_top_k],
                    top_n=answer_top_k,
                )
                expanded = self._expand_and_cluster(rerank_result.chunks)
                if trace is not None:
                    trace.record_retrieval(
                        searched=len(keyword_results),
                        evaluated=len(keyword_results),
                        selected=len(expanded),
                        rejected=max(0, len(keyword_results) - len(expanded)),
                        strategy=normalized_search_mode,
                    )
                    trace.set_metadata(
                        reranking_applied=rerank_result.metadata.applied,
                        reranker_provider=rerank_result.metadata.provider,
                        reranker_model=rerank_result.metadata.model,
                        reranker_latency_ms=rerank_result.metadata.latency_ms,
                        reranker_candidate_count=rerank_result.metadata.candidate_count,
                        reranker_selected_count=rerank_result.metadata.selected_count,
                        reranker_failure_reason=rerank_result.metadata.failure_reason,
                    )
                return expanded

        fused = self._rrf_combine(
            vector_results,
            keyword_results,
            top_k=retrieve_top_k,
        )
        rerank_result = self.reranker.rerank_chunks(
            tenant_id=tenant_id,
            workspace_id=None,
            actor_user_id=user_id,
            query=query,
            chunks=fused[:rerank_top_k],
            top_n=answer_top_k,
        )
        expanded = self._expand_and_cluster(rerank_result.chunks)

        if trace is not None:
            total_raw = len(vector_results) + len(keyword_results)
            trace.record_retrieval(
                searched=total_raw,
                evaluated=total_raw,
                selected=len(expanded),
                rejected=max(0, total_raw - len(expanded)),
                strategy=normalized_search_mode,
            )
            trace.set_metadata(
                reranking_applied=rerank_result.metadata.applied,
                reranker_provider=rerank_result.metadata.provider,
                reranker_model=rerank_result.metadata.model,
                reranker_latency_ms=rerank_result.metadata.latency_ms,
                reranker_candidate_count=rerank_result.metadata.candidate_count,
                reranker_selected_count=rerank_result.metadata.selected_count,
                reranker_failure_reason=rerank_result.metadata.failure_reason,
            )

        return expanded

    def get_document_references(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[RetrievedChunk]:
        if not document_ids:
            return []

        import sqlalchemy as sa
        from sqlalchemy import select

        from app.documents.models.document import Document
        from app.documents.models.document_chunk import DocumentChunk
        from app.system.services.metrics_service import observe_db_query

        stmt = (
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id.in_(document_ids),
                sa.or_(
                    DocumentChunk.chunk_metadata["header_1"].astext.ilike("%referen%"),
                    DocumentChunk.chunk_metadata["header_1"].astext.ilike("%bibliograph%"),
                    DocumentChunk.chunk_metadata["header_2"].astext.ilike("%referen%"),
                    DocumentChunk.chunk_metadata["header_2"].astext.ilike("%bibliograph%"),
                ),
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )

        with observe_db_query("chunks.get_document_references"):
            rows = self.db.execute(stmt).all()

        results: list[RetrievedChunk] = []
        for chunk, filename in rows:
            results.append(
                RetrievedChunk(
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    filename=filename,
                    content=chunk.content,
                    similarity_score=1.0,
                    source_type=chunk.chunk_metadata.get("mode", "text"),
                    section_header=chunk.chunk_metadata.get("header_1")
                    or chunk.chunk_metadata.get("header_2"),
                    page_number=chunk.chunk_metadata.get(
                        "page_number", (chunk.chunk_index // 4) + 1
                    ),
                )
            )
        return results
