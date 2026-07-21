from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.auth.tenancy import require_request_tenant_id
from app.db.session import get_db
from app.schemas.query.queries import (
    ChatCapabilitiesResponse,
    CitationFeedbackRequest,
    CitationFeedbackResponse,
    QueryCitationResponse,
    QueryRequest,
    QueryResponse,
)
from app.providers.services.reasoning_capabilities import reasoning_capabilities
from app.providers.services.selection_service import ProviderSelectionService
from app.services.query.query_service import QueryService
from app.services.system.audit_service import AuditService
from app.services.system.quality_service import QualityService
from app.services.system.rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queries", tags=["queries"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

_ALLOWED_FILTER_FIELDS = {
    "document_ids",
    "created_at_from",
    "created_at_to",
    "source_types",
    "min_extraction_coverage",
    "max_extraction_coverage",
}


def _merge_chat_reasoning_capabilities(
    cached_capabilities: dict[str, Any],
    inferred_capabilities: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(cached_capabilities)

    merged["supports_reasoning"] = bool(
        cached_capabilities.get("supports_reasoning")
        or inferred_capabilities.get("supports_reasoning")
    )
    merged["supports_thinking_toggle"] = bool(
        cached_capabilities.get("supports_thinking_toggle")
        or inferred_capabilities.get("supports_thinking_toggle")
    )
    merged["reasoning_visibility"] = str(
        cached_capabilities.get("reasoning_visibility")
        or inferred_capabilities.get("reasoning_visibility")
        or "hidden"
    )

    for field in (
        "request_controls_on",
        "request_controls_off",
        "supported_reasoning_efforts",
    ):
        cached_items = [
            str(item)
            for item in cast(list[Any], cached_capabilities.get(field, []))
            if isinstance(item, str)
        ]
        inferred_items = [
            str(item)
            for item in cast(list[Any], inferred_capabilities.get(field, []))
            if isinstance(item, str)
        ]
        merged[field] = list(dict.fromkeys([*cached_items, *inferred_items]))

    return merged


def _enforce_tenant_scope(request_tenant_id: uuid.UUID, auth: AuthContext) -> None:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Token tenant scope does not match requested tenant.",
            status_code=403,
        )


def _validate_query_payload(raw_payload: Any) -> QueryRequest:
    if not isinstance(raw_payload, dict):
        raise ApiError(
            code="QUERY_VALIDATION_ERROR",
            message="Query payload must be a JSON object.",
            status_code=422,
        )

    raw_filters = raw_payload.get("filters", {})
    if not isinstance(raw_filters, dict):
        raise ApiError(
            code="QUERY_VALIDATION_ERROR",
            message="filters must be a JSON object.",
            status_code=422,
        )

    unknown_filter_fields = sorted(set(raw_filters.keys()) - _ALLOWED_FILTER_FIELDS)
    if unknown_filter_fields:
        raise ApiError(
            code="INVALID_FILTER_FIELD",
            message="filters include unsupported fields.",
            status_code=400,
            details={"unknown_fields": unknown_filter_fields},
        )

    try:
        return QueryRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise ApiError(
            code="QUERY_VALIDATION_ERROR",
            message="Query payload validation failed.",
            status_code=422,
            details={"errors": exc.errors()},
        ) from exc


def _map_citations(items: list[dict[str, Any]]) -> list[QueryCitationResponse]:
    return [
        QueryCitationResponse(
            document_id=uuid.UUID(str(item["document_id"])),
            chunk_id=uuid.UUID(str(item["chunk_id"])),
            filename=str(item.get("filename", "Unknown")),
            snippet=str(item["snippet"]),
            similarity_score=float(item["similarity_score"]),
            source_type=str(item.get("source_type", "text")),
        )
        for item in items
    ]


def _validate_top_k_bounds(*, top_k: int, settings: Settings) -> None:
    if top_k < settings.query_top_k_min or top_k > settings.query_top_k_max:
        raise ApiError(
            code="TOP_K_OUT_OF_RANGE",
            message="top_k is outside allowed bounds.",
            status_code=400,
            details={
                "min": settings.query_top_k_min,
                "max": settings.query_top_k_max,
            },
        )


def _safe_audit_commit(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    action: str,
    details: dict[str, str] | None = None,
) -> None:
    try:
        AuditService(db).write_event(
            tenant_id=tenant_id,
            action=action,
            resource_type="query",
            actor_user_id=actor_user_id,
            details=details or {},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning(
            "Failed to persist query audit event.",
            extra={
                "tenant_id": str(tenant_id),
                "actor_user_id": str(actor_user_id),
                "action": action,
            },
            exc_info=True,
        )


@router.post(
    "",
    response_model=QueryResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def run_query(
    request: Request,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )

    raw_payload = await request.json()
    payload = _validate_query_payload(raw_payload)
    _validate_top_k_bounds(top_k=payload.top_k, settings=settings)

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
        conversation_kind=payload.conversation_kind,
        search_mode=payload.search_mode,
        thinking_enabled=payload.thinking_enabled,
    )

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="queries.run",
        details={"cached": str(result.cached)},
    )

    return QueryResponse(
        answer=result.answer,
        confidence=result.confidence,
        citations=_map_citations(result.citations),
        trace_id=result.trace_id,
        cached=result.cached,
        conversation_id=result.conversation_id,
    )


@router.post(
    "/stream",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def stream_query(
    request: Request,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    RateLimitService(settings).enforce_query_user_limit(
        request=request, user_id=str(auth.user_id)
    )

    raw_payload = await request.json()
    payload = _validate_query_payload(raw_payload)
    _validate_top_k_bounds(top_k=payload.top_k, settings=settings)

    service = QueryService(db=db, settings=settings)

    async def event_generator() -> Any:
        async for chunk in service.stream_execute(
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
            conversation_kind=payload.conversation_kind,
            search_mode=payload.search_mode,
            thinking_enabled=payload.thinking_enabled,
        ):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/capabilities/chat",
    response_model=ChatCapabilitiesResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_chat_capabilities(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatCapabilitiesResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    selection = ProviderSelectionService(db, settings).resolve_chat(
        tenant_id=auth.tenant_id,
        workspace_id=None,
        actor_user_id=auth.user_id,
    )
    candidate = selection.candidates[0] if selection.candidates else None
    if candidate is None:
        return ChatCapabilitiesResponse()

    capabilities_payload: dict[str, Any] = {}
    if candidate.provider_config_id is not None:
        row = ProviderSelectionService(db, settings).model_cache.get_model(
            tenant_id=auth.tenant_id,
            provider_config_id=candidate.provider_config_id,
            model_name=candidate.model_name,
            model_kind="chat",
        )
        if row is not None:
            capabilities_payload = dict(row.capabilities_json or {})
    inferred_capabilities = reasoning_capabilities(
        candidate.provider_type,
        candidate.model_name,
        base_url=candidate.base_url,
    )
    capabilities_payload = (
        _merge_chat_reasoning_capabilities(capabilities_payload, inferred_capabilities)
        if capabilities_payload
        else inferred_capabilities
    )

    return ChatCapabilitiesResponse(
        provider_type=candidate.provider_type,
        model_name=candidate.model_name,
        context_limit=(
            candidate.context_window
            if isinstance(candidate.context_window, int)
            else None
        ),
        context_limit_source=(
            candidate.context_window_source
            if isinstance(candidate.context_window_source, str)
            and candidate.context_window_source.strip()
            else None
        ),
        supports_thinking=bool(capabilities_payload.get("supports_reasoning")),
        supports_thinking_toggle=bool(
            capabilities_payload.get("supports_thinking_toggle")
        ),
        reasoning_visibility=str(
            capabilities_payload.get("reasoning_visibility") or "hidden"
        ),
        request_controls_on=[
            str(item)
            for item in cast(
                list[Any], capabilities_payload.get("request_controls_on", [])
            )
            if isinstance(item, str)
        ],
        request_controls_off=[
            str(item)
            for item in cast(
                list[Any], capabilities_payload.get("request_controls_off", [])
            )
            if isinstance(item, str)
        ],
        supported_reasoning_efforts=[
            str(item)
            for item in cast(
                list[Any], capabilities_payload.get("supported_reasoning_efforts", [])
            )
            if isinstance(item, str)
        ],
    )


@router.post(
    "/{query_id}/citations/{chunk_id}/feedback",
    response_model=CitationFeedbackResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def submit_citation_feedback(
    query_id: uuid.UUID,
    chunk_id: uuid.UUID,
    payload: CitationFeedbackRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CitationFeedbackResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    quality_service = QualityService(db)
    citation = quality_service.record_citation_feedback(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        query_id=query_id,
        chunk_id=chunk_id,
        feedback_score=payload.score,
    )

    if not citation:
        raise ApiError(
            code="CITATION_NOT_FOUND",
            message="Citation not found.",
            status_code=404,
        )

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to save citation feedback.",
            status_code=500,
        ) from exc

    return CitationFeedbackResponse(
        query_id=query_id,
        chunk_id=chunk_id,
        score=payload.score,
    )
