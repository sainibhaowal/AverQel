from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.roles import is_admin_role
from app.platform.database.session import get_db
from app.system.schemas.plans import (
    CurrentPlanSchema,
    PlanCardSchema,
    PlansResponse,
    StorageUsageSchema,
)
from app.system.services.storage_quota import PLANS, StorageQuotaService, resolve_storage_plan

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/current", response_model=PlansResponse)
def get_current_plan(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> PlansResponse:
    current = resolve_storage_plan(auth.roles)
    usage = StorageQuotaService(db).usage(tenant_id=auth.tenant_id)
    visible_plans = [PLANS["free"], PLANS["editor"]]
    if is_admin_role(auth.roles):
        visible_plans.append(PLANS["admin"])
    return PlansResponse(
        current_plan=CurrentPlanSchema(
            id=current.id,
            name=current.name,
            storage_limit_bytes=current.storage_limit_bytes,
            description=current.description,
            admin_account=is_admin_role(auth.roles),
        ),
        usage=StorageUsageSchema(
            documents_bytes=usage.documents_bytes,
            library_bytes=usage.library_bytes,
            artifacts_bytes=usage.artifacts_bytes,
            pending_upload_bytes=usage.pending_upload_bytes,
            account_data_bytes=usage.account_data_bytes,
            total_bytes=usage.total_bytes,
        ),
        plans=[
            PlanCardSchema(
                id=plan.id,
                name=plan.name,
                storage_limit_bytes=plan.storage_limit_bytes,
                description=plan.description,
                features=list(plan.features),
                admin_only=plan.admin_only,
            )
            for plan in visible_plans
        ],
        storage_scope="Shared across this authenticated tenant/workspace.",
    )
