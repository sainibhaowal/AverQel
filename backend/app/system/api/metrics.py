from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.rbac import require_permissions
from app.platform.database.session import get_db
from app.system.api.admin import require_platform_admin_access
from app.system.schemas.metrics_summary import MetricsSummaryResponse
from app.system.services.audit_service import AuditService
from app.system.services.metrics_service import (
    metrics_payload,
    read_deepspace_metrics_summary,
    read_metrics_summary,
)

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
def get_metrics_summary(
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> MetricsSummaryResponse:
    """Return global process metrics only to allowlisted platform operators."""
    api_requests, api_errors, db_queries, worker_retries, worker_dead_letters = (
        read_metrics_summary()
    )
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.metrics.summary.read",
        resource_type="system_metrics",
    )
    return MetricsSummaryResponse(
        api_requests_total=api_requests,
        api_errors_total=api_errors,
        db_query_count=db_queries,
        worker_retries_total=worker_retries,
        worker_dead_letters_total=worker_dead_letters,
        **read_deepspace_metrics_summary(),
    )
