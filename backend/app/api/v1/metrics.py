from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.auth.rbac import require_permissions
from app.schemas.system.metrics_summary import MetricsSummaryResponse
from app.services.system.metrics_service import metrics_payload, read_metrics_summary

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def get_metrics() -> Response:
    """Raw Prometheus scrape endpoint — kept unauthenticated for internal scraper compatibility."""
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    dependencies=[Depends(require_permissions("admin:metrics:read"))],
)
def get_metrics_summary() -> MetricsSummaryResponse:
    """Admin-only JSON summary of key runtime metrics for the UI."""
    api_requests, api_errors, db_queries = read_metrics_summary()
    return MetricsSummaryResponse(
        api_requests_total=api_requests,
        api_errors_total=api_errors,
        db_query_count=db_queries,
    )
