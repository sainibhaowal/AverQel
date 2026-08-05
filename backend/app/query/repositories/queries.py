from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.query.models.query import Query
from app.query.models.query_citation import QueryCitation
from app.system.repositories.base import BaseRepository
from app.system.services.metrics_service import observe_db_query


class QueriesRepository(BaseRepository):
    def create_query(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str,
        normalized_query: str,
        filters: dict[str, Any],
        top_k: int,
        cache_hit: bool,
        answer: str,
        confidence: float,
        trace_id: str,
    ) -> Query:
        self.apply_tenant_scope(tenant_id)
        row = Query(
            tenant_id=tenant_id,
            user_id=user_id,
            query_text=query_text,
            normalized_query=normalized_query,
            filters=filters,
            top_k=top_k,
            cache_hit=cache_hit,
            answer=answer,
            confidence=confidence,
            trace_id=trace_id,
        )
        with observe_db_query("queries.create_query"):
            self.db.add(row)
            self.db.flush()
        return row

    def create_citations(
        self,
        *,
        tenant_id: uuid.UUID,
        citations: list[QueryCitation],
    ) -> list[QueryCitation]:
        self.apply_tenant_scope(tenant_id)
        with observe_db_query("queries.create_citations"):
            for citation in citations:
                if citation.tenant_id != tenant_id:
                    raise ValueError("Citation tenant_id does not match repository tenant_id")
                self.db.add(citation)
            self.db.flush()
        return citations

    def get_query(
        self,
        *,
        tenant_id: uuid.UUID,
        query_id: uuid.UUID,
    ) -> Query | None:
        self.apply_tenant_scope(tenant_id)
        statement = select(Query).where(
            Query.tenant_id == tenant_id,
            Query.id == query_id,
        )
        with observe_db_query("queries.get_query"):
            return self.db.execute(statement).scalar_one_or_none()
