from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.auth.tenancy import require_request_tenant_id
from app.db.session import get_db
from app.schemas.query.queries import QueryCitationResponse, QueryRequest, QueryResponse
from app.schemas.query.batch import BatchQueryRequest, BatchQueryResponse
from app.services.query.query_service import QueryExecutionResult, QueryService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _enforce_tenant_scope(request_tenant_id: uuid.UUID, auth: AuthContext) -> None:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Requested tenant does not match authenticated tenant scope.",
            status_code=403,
        )


def _map_query_response(result: QueryExecutionResult) -> QueryResponse:
    citations = [
        QueryCitationResponse(
            document_id=uuid.UUID(str(item["document_id"])),
            chunk_id=uuid.UUID(str(item["chunk_id"])),
            filename=str(item.get("filename", "Unknown")),
            snippet=str(item["snippet"]),
            similarity_score=float(item["similarity_score"]),
            source_type=str(item.get("source_type", "text")),
        )
        for item in result.citations
    ]

    return QueryResponse(
        answer=result.answer,
        confidence=result.confidence,
        citations=citations,
        trace_id=result.trace_id,
        cached=result.cached,
        conversation_id=result.conversation_id,
    )


@router.post("/query", response_model=QueryResponse)
async def intelligence_query(
    payload: QueryRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = QueryService(db=db, settings=settings)
    result = service.execute(
        auth=auth,
        query_text=payload.query,
        top_k=payload.top_k,
        filters=payload.filters.model_dump(exclude_none=True),
        document_ids=payload.filters.document_ids,
        created_at_from=payload.filters.created_at_from,
        created_at_to=payload.filters.created_at_to,
        source_types=payload.filters.source_types,
        min_extraction_coverage=payload.filters.min_extraction_coverage,
        max_extraction_coverage=payload.filters.max_extraction_coverage,
        conversation_id=payload.conversation_id,
        search_mode=payload.search_mode,
    )
    return _map_query_response(result)


@router.post("/batch", response_model=BatchQueryResponse)
async def intelligence_batch_query(
    payload: BatchQueryRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BatchQueryResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = QueryService(db=db, settings=settings)
    results: list[QueryResponse] = []

    for query_payload in payload.queries:
        result = service.execute(
            auth=auth,
            query_text=query_payload.query,
            top_k=query_payload.top_k,
            filters=query_payload.filters.model_dump(exclude_none=True),
            document_ids=query_payload.filters.document_ids,
            created_at_from=query_payload.filters.created_at_from,
            created_at_to=query_payload.filters.created_at_to,
            source_types=query_payload.filters.source_types,
            min_extraction_coverage=query_payload.filters.min_extraction_coverage,
            max_extraction_coverage=query_payload.filters.max_extraction_coverage,
            conversation_id=query_payload.conversation_id,
            search_mode=query_payload.search_mode,
        )
        results.append(_map_query_response(result))

    return BatchQueryResponse(results=results)
