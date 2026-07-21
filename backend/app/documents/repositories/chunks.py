from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import and_, delete, select

from app.db.session import set_db_tenant_context
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.system.repositories.base import BaseRepository
from app.system.services.metrics_service import observe_db_query


@dataclass(slots=True)
class RetrievedChunkRow:
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    content: str
    similarity_score: float
    source_type: str = "text"
    chunk_index: int = 0
    section_header: str | None = None
    page_number: int | None = None
    quality_score: float | None = None


@dataclass(slots=True)
class DocumentEmbeddingSummary:
    provider: str
    model: str
    embedded_chunk_count: int


@dataclass(slots=True)
class DocumentChunkStats:
    chunk_count: int
    avg_quality_score: float | None


class ChunksRepository(BaseRepository):
    def _apply_bypass_scope(self) -> None:
        set_db_tenant_context(self.db, "bypass")

    def replace_document_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: list[DocumentChunk],
    ) -> list[DocumentChunk]:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("chunks.replace_document_chunks"):
            self.db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.document_id == document_id,
                )
            )
            for chunk in chunks:
                if chunk.tenant_id != tenant_id or chunk.document_id != document_id:
                    raise ValueError("Chunk tenant_id/document_id mismatch")
                self.db.add(chunk)
            self.db.flush()
        return chunks

    def replace_chunk_embeddings(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        embeddings: list[ChunkEmbedding],
    ) -> list[ChunkEmbedding]:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("chunks.replace_chunk_embeddings"):
            self.db.execute(
                delete(ChunkEmbedding).where(
                    ChunkEmbedding.tenant_id == tenant_id,
                    ChunkEmbedding.document_id == document_id,
                )
            )
            for embedding in embeddings:
                if (
                    embedding.tenant_id != tenant_id
                    or embedding.document_id != document_id
                ):
                    raise ValueError("Embedding tenant_id/document_id mismatch")
                self.db.add(embedding)
            self.db.flush()
        return embeddings

    def search_top_k(
        self,
        *,
        tenant_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
    ) -> list[RetrievedChunkRow]:
        self.apply_tenant_scope(tenant_id)

        distance = ChunkEmbedding.embedding.l2_distance(query_embedding)
        statement = (
            select(
                ChunkEmbedding.document_id,
                DocumentChunk.id.label("chunk_id"),
                Document.filename,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata["mode"].astext.label("source_type"),
                DocumentChunk.chunk_metadata.label("chunk_metadata"),
                DocumentChunk.quality_score.label("quality_score"),
                distance.label("distance"),
            )
            .join(
                DocumentChunk,
                and_(
                    DocumentChunk.id == ChunkEmbedding.chunk_id,
                    DocumentChunk.tenant_id == tenant_id,
                ),
            )
            .join(
                Document,
                and_(
                    Document.id == ChunkEmbedding.document_id,
                    Document.tenant_id == tenant_id,
                    Document.is_deleted.is_(False),
                    Document.quarantined.is_(False),
                ),
            )
            .where(ChunkEmbedding.tenant_id == tenant_id)
            .order_by(distance.asc(), DocumentChunk.chunk_index.asc())
            .limit(top_k)
        )

        if document_ids:
            statement = statement.where(ChunkEmbedding.document_id.in_(document_ids))
        if created_at_from is not None:
            statement = statement.where(Document.created_at >= created_at_from)
        if created_at_to is not None:
            statement = statement.where(Document.created_at <= created_at_to)
        if source_types:
            statement = statement.where(
                DocumentChunk.chunk_metadata["mode"].astext.in_(source_types)
            )
        if min_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score >= min_extraction_coverage
            )
        if max_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score <= max_extraction_coverage
            )

        with observe_db_query("chunks.search_top_k"):
            rows = self.db.execute(statement).all()

        results: list[RetrievedChunkRow] = []
        for row in rows:
            distance_value = float(row.distance)
            similarity_score = 1.0 / (1.0 + max(distance_value, 0.0))
            metadata = row.chunk_metadata or {}
            estimated_page = metadata.get("page_number", (row.chunk_index // 4) + 1)

            results.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=round(similarity_score, 6),
                    source_type=str(row.source_type or "text"),
                    chunk_index=int(row.chunk_index),
                    section_header=metadata.get("header_1") or metadata.get("header_2"),
                    page_number=estimated_page,
                    quality_score=row.quality_score,
                )
            )
        return results

    def search_top_k_global(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
    ) -> list[RetrievedChunkRow]:
        self._apply_bypass_scope()
        distance = ChunkEmbedding.embedding.l2_distance(query_embedding)
        statement = (
            select(
                ChunkEmbedding.document_id,
                DocumentChunk.id.label("chunk_id"),
                Document.filename,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata["mode"].astext.label("source_type"),
                DocumentChunk.chunk_metadata.label("chunk_metadata"),
                DocumentChunk.quality_score.label("quality_score"),
                distance.label("distance"),
            )
            .join(DocumentChunk, DocumentChunk.id == ChunkEmbedding.chunk_id)
            .join(
                Document,
                and_(
                    Document.id == ChunkEmbedding.document_id,
                    Document.is_deleted.is_(False),
                    Document.quarantined.is_(False),
                ),
            )
            .order_by(distance.asc(), DocumentChunk.chunk_index.asc())
            .limit(top_k)
        )
        if document_ids:
            statement = statement.where(ChunkEmbedding.document_id.in_(document_ids))
        if created_at_from is not None:
            statement = statement.where(Document.created_at >= created_at_from)
        if created_at_to is not None:
            statement = statement.where(Document.created_at <= created_at_to)
        if source_types:
            statement = statement.where(
                DocumentChunk.chunk_metadata["mode"].astext.in_(source_types)
            )
        if min_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score >= min_extraction_coverage
            )
        if max_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score <= max_extraction_coverage
            )
        with observe_db_query("chunks.search_top_k_global"):
            rows = self.db.execute(statement).all()
        results: list[RetrievedChunkRow] = []
        for row in rows:
            distance_value = float(row.distance)
            similarity_score = 1.0 / (1.0 + max(distance_value, 0.0))
            metadata = row.chunk_metadata or {}
            estimated_page = metadata.get("page_number", (row.chunk_index // 4) + 1)
            results.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=round(similarity_score, 6),
                    source_type=str(row.source_type or "text"),
                    chunk_index=int(row.chunk_index),
                    section_header=metadata.get("header_1") or metadata.get("header_2"),
                    page_number=estimated_page,
                    quality_score=row.quality_score,
                )
            )
        return results

    def search_bm25(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        top_k: int,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
    ) -> list[RetrievedChunkRow]:
        self.apply_tenant_scope(tenant_id)

        ts_query = sa.func.websearch_to_tsquery("english", query)
        rank = sa.func.ts_rank_cd(DocumentChunk.search_vector, ts_query)

        statement = (
            select(
                DocumentChunk.document_id,
                DocumentChunk.id.label("chunk_id"),
                Document.filename,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata["mode"].astext.label("source_type"),
                DocumentChunk.chunk_metadata.label("chunk_metadata"),
                DocumentChunk.quality_score.label("quality_score"),
                rank.label("rank_score"),
            )
            .join(
                Document,
                and_(
                    Document.id == DocumentChunk.document_id,
                    Document.tenant_id == tenant_id,
                    Document.is_deleted.is_(False),
                    Document.quarantined.is_(False),
                ),
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.search_vector.op("@@")(ts_query),
            )
            .order_by(rank.desc(), DocumentChunk.chunk_index.asc())
            .limit(top_k)
        )

        if document_ids:
            statement = statement.where(DocumentChunk.document_id.in_(document_ids))
        if created_at_from is not None:
            statement = statement.where(Document.created_at >= created_at_from)
        if created_at_to is not None:
            statement = statement.where(Document.created_at <= created_at_to)
        if source_types:
            statement = statement.where(
                DocumentChunk.chunk_metadata["mode"].astext.in_(source_types)
            )
        if min_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score >= min_extraction_coverage
            )
        if max_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score <= max_extraction_coverage
            )

        with observe_db_query("chunks.search_bm25"):
            rows = self.db.execute(statement).all()

        results: list[RetrievedChunkRow] = []
        for row in rows:
            metadata = row.chunk_metadata or {}
            estimated_page = metadata.get("page_number", (row.chunk_index // 4) + 1)

            results.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=float(row.rank_score),
                    source_type=str(row.source_type or "text"),
                    chunk_index=int(row.chunk_index),
                    section_header=metadata.get("header_1") or metadata.get("header_2"),
                    page_number=estimated_page,
                    quality_score=row.quality_score,
                )
            )
        return results

    def search_bm25_global(
        self,
        *,
        query: str,
        top_k: int,
        document_ids: list[uuid.UUID] | None,
        created_at_from: datetime | None,
        created_at_to: datetime | None,
        source_types: list[str] | None,
        min_extraction_coverage: float | None,
        max_extraction_coverage: float | None,
    ) -> list[RetrievedChunkRow]:
        self._apply_bypass_scope()
        ts_query = sa.func.websearch_to_tsquery("english", query)
        rank = sa.func.ts_rank_cd(DocumentChunk.search_vector, ts_query)
        statement = (
            select(
                DocumentChunk.document_id,
                DocumentChunk.id.label("chunk_id"),
                Document.filename,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata["mode"].astext.label("source_type"),
                DocumentChunk.chunk_metadata.label("chunk_metadata"),
                DocumentChunk.quality_score.label("quality_score"),
                rank.label("rank_score"),
            )
            .join(
                Document,
                and_(
                    Document.id == DocumentChunk.document_id,
                    Document.is_deleted.is_(False),
                    Document.quarantined.is_(False),
                ),
            )
            .where(DocumentChunk.search_vector.op("@@")(ts_query))
            .order_by(rank.desc(), DocumentChunk.chunk_index.asc())
            .limit(top_k)
        )
        if document_ids:
            statement = statement.where(DocumentChunk.document_id.in_(document_ids))
        if created_at_from is not None:
            statement = statement.where(Document.created_at >= created_at_from)
        if created_at_to is not None:
            statement = statement.where(Document.created_at <= created_at_to)
        if source_types:
            statement = statement.where(
                DocumentChunk.chunk_metadata["mode"].astext.in_(source_types)
            )
        if min_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score >= min_extraction_coverage
            )
        if max_extraction_coverage is not None:
            statement = statement.where(
                Document.extraction_coverage_score <= max_extraction_coverage
            )
        with observe_db_query("chunks.search_bm25_global"):
            rows = self.db.execute(statement).all()
        results: list[RetrievedChunkRow] = []
        for row in rows:
            metadata = row.chunk_metadata or {}
            estimated_page = metadata.get("page_number", (row.chunk_index // 4) + 1)
            results.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=float(row.rank_score),
                    source_type=str(row.source_type or "text"),
                    chunk_index=int(row.chunk_index),
                    section_header=metadata.get("header_1") or metadata.get("header_2"),
                    page_number=estimated_page,
                    quality_score=row.quality_score,
                )
            )
        return results

    def get_by_document_id(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentChunk]:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("chunks.get_by_document_id"):
            stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.document_id == document_id,
                )
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(limit)
                .offset(offset)
            )
            result = self.db.scalars(stmt).all()
        return list(result)

    def count_by_document_id(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> int:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("chunks.count_by_document_id"):
            stmt = select(sa.func.count(DocumentChunk.id)).where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id == document_id,
            )
            count = self.db.scalar(stmt)
        return int(count or 0)

    def get_chunks_by_indices(
        self,
        *,
        tenant_id: uuid.UUID,
        document_indices: dict[uuid.UUID, list[int]],
    ) -> list[DocumentChunk]:
        self.apply_tenant_scope(tenant_id)
        if not document_indices:
            return []

        conditions = []
        for doc_id, indices in document_indices.items():
            if not indices:
                continue
            conditions.append(
                and_(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_index.in_(indices),
                )
            )
        if not conditions:
            return []

        with observe_db_query("chunks.get_chunks_by_indices"):
            stmt = select(DocumentChunk).where(
                DocumentChunk.tenant_id == tenant_id,
                sa.or_(*conditions),
            )
            rows = self.db.scalars(stmt).all()
        return list(rows)

    def get_chunks_by_indices_global(
        self,
        *,
        document_indices: dict[uuid.UUID, list[int]],
    ) -> list[DocumentChunk]:
        self._apply_bypass_scope()
        if not document_indices:
            return []
        conditions = []
        for doc_id, indices in document_indices.items():
            if not indices:
                continue
            conditions.append(
                and_(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_index.in_(indices),
                )
            )
        if not conditions:
            return []
        with observe_db_query("chunks.get_chunks_by_indices_global"):
            stmt = select(DocumentChunk).where(sa.or_(*conditions))
            rows = self.db.scalars(stmt).all()
        return list(rows)

    def delete_by_document_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return

        query_emb = delete(ChunkEmbedding).where(
            ChunkEmbedding.tenant_id == tenant_id,
            ChunkEmbedding.document_id.in_(document_ids),
        )
        with observe_db_query("chunks.delete_embeddings_by_document_ids"):
            self.db.execute(query_emb)

        query_chunk = delete(DocumentChunk).where(
            DocumentChunk.tenant_id == tenant_id,
            DocumentChunk.document_id.in_(document_ids),
        )
        with observe_db_query("chunks.delete_chunks_by_document_ids"):
            self.db.execute(query_chunk)

    def get_embedding_summary_by_document_id(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DocumentEmbeddingSummary | None:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("chunks.get_embedding_summary_by_document_id"):
            stmt = (
                select(
                    ChunkEmbedding.provider,
                    ChunkEmbedding.model,
                    sa.func.count(ChunkEmbedding.id).label("embedded_chunk_count"),
                    sa.func.max(ChunkEmbedding.created_at).label("latest_embedding_at"),
                )
                .where(
                    ChunkEmbedding.tenant_id == tenant_id,
                    ChunkEmbedding.document_id == document_id,
                )
                .group_by(ChunkEmbedding.provider, ChunkEmbedding.model)
                .order_by(
                    sa.func.count(ChunkEmbedding.id).desc(),
                    sa.func.max(ChunkEmbedding.created_at).desc(),
                )
                .limit(1)
            )
            row = self.db.execute(stmt).one_or_none()

        if row is None:
            return None

        return DocumentEmbeddingSummary(
            provider=str(row.provider),
            model=str(row.model),
            embedded_chunk_count=int(row.embedded_chunk_count or 0),
        )

    def get_embedding_summaries_by_document_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, DocumentEmbeddingSummary]:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return {}

        ranked = sa.func.row_number().over(
            partition_by=ChunkEmbedding.document_id,
            order_by=(
                sa.func.count(ChunkEmbedding.id).desc(),
                sa.func.max(ChunkEmbedding.created_at).desc(),
            ),
        )
        grouped = (
            select(
                ChunkEmbedding.document_id.label("document_id"),
                ChunkEmbedding.provider.label("provider"),
                ChunkEmbedding.model.label("model"),
                sa.func.count(ChunkEmbedding.id).label("embedded_chunk_count"),
                ranked.label("rank"),
            )
            .where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.document_id.in_(document_ids),
            )
            .group_by(
                ChunkEmbedding.document_id,
                ChunkEmbedding.provider,
                ChunkEmbedding.model,
            )
        ).subquery()

        stmt = select(
            grouped.c.document_id,
            grouped.c.provider,
            grouped.c.model,
            grouped.c.embedded_chunk_count,
        ).where(grouped.c.rank == 1)

        with observe_db_query("chunks.get_embedding_summaries_by_document_ids"):
            rows = self.db.execute(stmt).all()

        return {
            row.document_id: DocumentEmbeddingSummary(
                provider=str(row.provider),
                model=str(row.model),
                embedded_chunk_count=int(row.embedded_chunk_count or 0),
            )
            for row in rows
        }

    def search_document_text(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
        query: str,
        limit: int = 25,
    ) -> list[RetrievedChunkRow]:
        self.apply_tenant_scope(tenant_id)
        normalized_query = query.strip()
        if not document_ids or not normalized_query:
            return []

        statement = (
            select(
                DocumentChunk.document_id,
                DocumentChunk.id.label("chunk_id"),
                Document.filename,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata["mode"].astext.label("source_type"),
                DocumentChunk.chunk_metadata.label("chunk_metadata"),
                DocumentChunk.quality_score.label("quality_score"),
            )
            .join(
                Document,
                and_(
                    Document.id == DocumentChunk.document_id,
                    Document.tenant_id == tenant_id,
                    Document.is_deleted.is_(False),
                ),
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id.in_(document_ids),
                DocumentChunk.content.ilike(f"%{normalized_query}%"),
            )
            .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
            .limit(limit)
        )

        with observe_db_query("chunks.search_document_text"):
            rows = self.db.execute(statement).all()

        results: list[RetrievedChunkRow] = []
        for row in rows:
            metadata = row.chunk_metadata or {}
            results.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=1.0,
                    source_type=str(row.source_type or "text"),
                    chunk_index=int(row.chunk_index),
                    section_header=metadata.get("header_1") or metadata.get("header_2"),
                    page_number=metadata.get("page_number", (row.chunk_index // 4) + 1),
                    quality_score=row.quality_score,
                )
            )
        return results

    def search_document_text_global(
        self,
        *,
        document_ids: list[uuid.UUID],
        query: str,
        limit: int = 25,
    ) -> list[RetrievedChunkRow]:
        self._apply_bypass_scope()
        normalized_query = query.strip()
        if not document_ids or not normalized_query:
            return []

        statement = (
            select(
                DocumentChunk.document_id,
                DocumentChunk.id.label("chunk_id"),
                Document.filename,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata["mode"].astext.label("source_type"),
                DocumentChunk.chunk_metadata.label("chunk_metadata"),
                DocumentChunk.quality_score.label("quality_score"),
            )
            .join(
                Document,
                and_(
                    Document.id == DocumentChunk.document_id,
                    Document.is_deleted.is_(False),
                ),
            )
            .where(
                DocumentChunk.document_id.in_(document_ids),
                DocumentChunk.content.ilike(f"%{normalized_query}%"),
            )
            .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
            .limit(limit)
        )
        with observe_db_query("chunks.search_document_text_global"):
            rows = self.db.execute(statement).all()
        results: list[RetrievedChunkRow] = []
        for row in rows:
            metadata = row.chunk_metadata or {}
            results.append(
                RetrievedChunkRow(
                    document_id=row.document_id,
                    chunk_id=row.chunk_id,
                    filename=row.filename,
                    content=row.content,
                    similarity_score=1.0,
                    source_type=str(row.source_type or "text"),
                    chunk_index=int(row.chunk_index),
                    section_header=metadata.get("header_1") or metadata.get("header_2"),
                    page_number=metadata.get("page_number", (row.chunk_index // 4) + 1),
                    quality_score=row.quality_score,
                )
            )
        return results

    def get_chunk_stats_by_document_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, DocumentChunkStats]:
        self.apply_tenant_scope(tenant_id)
        if not document_ids:
            return {}

        statement = (
            select(
                DocumentChunk.document_id,
                sa.func.count(DocumentChunk.id).label("chunk_count"),
                sa.func.avg(DocumentChunk.quality_score).label("avg_quality_score"),
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id.in_(document_ids),
            )
            .group_by(DocumentChunk.document_id)
        )
        with observe_db_query("chunks.get_chunk_stats_by_document_ids"):
            rows = self.db.execute(statement).all()

        return {
            row.document_id: DocumentChunkStats(
                chunk_count=int(row.chunk_count or 0),
                avg_quality_score=(
                    float(row.avg_quality_score)
                    if row.avg_quality_score is not None
                    else None
                ),
            )
            for row in rows
        }
