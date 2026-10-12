from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardQueryStatsResponse,
    DashboardStatsResponse,
)
from app.analytics.services.dashboard_service import DashboardService
from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.tenancy import TenantContext, get_tenant_context
from app.platform.database.session import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DashboardStatsResponse:
    service = DashboardService(db)
    return service.get_stats(tenant_id=tenant_context.tenant_id)


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
    service = DashboardService(db)
    return service.get_overview(tenant_id=tenant_context.tenant_id, user_id=auth.user_id)


@router.get("/query-stats", response_model=DashboardQueryStatsResponse)
def get_dashboard_query_stats(
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> DashboardQueryStatsResponse:
    """Return only the live status data used by the grounded-query workspace."""
    return DashboardService(db).get_query_stats(tenant_id=tenant_context.tenant_id)
