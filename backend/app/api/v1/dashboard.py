from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_auth_context
from app.core.tenancy import TenantContext, get_tenant_context
from app.db.session import get_db
from app.schemas.analytics.dashboard import (
    DashboardOverviewResponse,
    DashboardStatsResponse,
)
from app.services.analytics.dashboard_service import DashboardService

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
    return service.get_overview(
        tenant_id=tenant_context.tenant_id, user_id=auth.user_id
    )
