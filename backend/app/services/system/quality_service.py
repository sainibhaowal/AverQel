from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.documents.document import Document
from app.models.documents.document_chunk import DocumentChunk
from app.models.query.query import Query
from app.models.query.query_citation import QueryCitation

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017

_LOW_QUALITY_WARNING = "Poor quality feedback from users."


class QualityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_citation_feedback(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_id: uuid.UUID,
        chunk_id: uuid.UUID,
        feedback_score: int,  # 1 for helpful, -1 for unhelpful
    ) -> QueryCitation | None:
        """Record explicit user feedback on a citation and update the chunk quality."""
        if feedback_score not in (-1, 1):
            raise ValueError("feedback_score must be either 1 or -1")

        citation = self.db.execute(
            select(QueryCitation)
            .join(Query, Query.id == QueryCitation.query_id)
            .where(
                QueryCitation.tenant_id == tenant_id,
                Query.tenant_id == tenant_id,
                Query.user_id == user_id,
                QueryCitation.query_id == query_id,
                QueryCitation.chunk_id == chunk_id,
            )
        ).scalar_one_or_none()

        if citation is None:
            return None

        citation.feedback_score = feedback_score
        self.db.flush()

        self._recompute_chunk_quality(tenant_id=tenant_id, chunk_id=chunk_id)
        return citation

    def _recompute_chunk_quality(
        self, *, tenant_id: uuid.UUID, chunk_id: uuid.UUID
    ) -> None:
        """Recompute average feedback score for a chunk and trigger re-ingestion if needed."""
        avg_score = self.db.execute(
            select(func.avg(QueryCitation.feedback_score)).where(
                QueryCitation.tenant_id == tenant_id,
                QueryCitation.chunk_id == chunk_id,
                QueryCitation.feedback_score.is_not(None),
            )
        ).scalar()

        if avg_score is None:
            return

        quality_score = float(avg_score)

        self.db.execute(
            update(DocumentChunk)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.id == chunk_id,
            )
            .values(quality_score=quality_score)
        )
        self.db.flush()

        if quality_score <= -0.5:
            chunk = self.db.execute(
                select(DocumentChunk).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.id == chunk_id,
                )
            ).scalar_one_or_none()
            if chunk is not None:
                self._flag_document_for_reingestion(
                    tenant_id=tenant_id,
                    document_id=chunk.document_id,
                )

    def _flag_document_for_reingestion(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        """Mark a document for re-ingestion when chunk-quality feedback is persistently poor."""
        doc = self.db.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.id == document_id,
            )
        ).scalar_one_or_none()

        if doc is None:
            return

        if doc.status != "needs_reingestion":
            doc.status = "needs_reingestion"

        warnings = list(doc.extraction_warnings or [])
        if _LOW_QUALITY_WARNING not in warnings:
            warnings.append(_LOW_QUALITY_WARNING)
            doc.extraction_warnings = warnings

        doc.updated_at = datetime.now(tz=UTC)
        self.db.flush()

        logger.info(
            "Document flagged for re-ingestion due to low chunk quality.",
            extra={
                "tenant_id": str(tenant_id),
                "document_id": str(document_id),
            },
        )
