from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_auth_context
from app.core.errors import ApiError
from app.core.rbac import require_permissions
from app.core.tenancy import require_request_tenant_id
from app.db.session import get_db
from app.schemas.analytics.analytics import AnalyticsDashboardResponse
from app.services.analytics.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/dashboard",
    response_model=AnalyticsDashboardResponse,
    dependencies=[Depends(require_permissions("admin:analytics:read"))],
)
def get_analytics_dashboard(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AnalyticsDashboardResponse:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Requested tenant does not match authenticated tenant scope.",
            status_code=403,
        )

    service = AnalyticsService(db)
    return service.get_dashboard_metrics(tenant_id=auth.tenant_id)
