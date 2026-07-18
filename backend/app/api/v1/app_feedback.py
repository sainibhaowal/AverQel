from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.v1.admin import require_platform_admin_access
from app.core.auth import AuthContext, get_auth_context
from app.core.rbac import require_permissions
from app.db.session import get_db
from app.models.auth.user import User
from app.models.system.app_feedback import AppFeedback, FeedbackCampaign
from app.schemas.system.app_feedback import (
    AppFeedbackCreate,
    AppFeedbackResponse,
    FeedbackCampaignCreate,
    FeedbackCampaignResponse,
)

router = APIRouter(prefix="/app-feedback", tags=["app-feedback"])


@router.post("/submit", response_model=AppFeedbackResponse)
def submit_app_feedback(
    payload: AppFeedbackCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AppFeedbackResponse:
    feedback = AppFeedback(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        campaign_id=payload.campaign_id,
        subject=payload.subject,
        content=payload.content,
        category=payload.category,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return AppFeedbackResponse.model_validate(feedback)


@router.get("/campaigns", response_model=list[FeedbackCampaignResponse])
def list_active_campaigns(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[FeedbackCampaignResponse]:
    campaigns = (
        db.execute(
            select(FeedbackCampaign)
            .where(FeedbackCampaign.is_active)
            .order_by(desc(FeedbackCampaign.created_at))
        )
        .scalars()
        .all()
    )
    return [FeedbackCampaignResponse.model_validate(campaign) for campaign in campaigns]


# Admin Routes
@router.post(
    "/admin/campaigns",
    response_model=FeedbackCampaignResponse,
    dependencies=[Depends(require_permissions("admin:feedback:write"))],
)
def create_campaign(
    payload: FeedbackCampaignCreate,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> FeedbackCampaignResponse:
    campaign = FeedbackCampaign(**payload.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return FeedbackCampaignResponse.model_validate(campaign)


@router.get(
    "/admin/submissions",
    response_model=list[AppFeedbackResponse],
    dependencies=[Depends(require_permissions("admin:feedback:read"))],
)
def list_all_submissions(
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> list[AppFeedbackResponse]:
    results = db.execute(
        select(AppFeedback, User.email)
        .outerjoin(User, User.id == AppFeedback.user_id)
        .order_by(desc(AppFeedback.created_at))
    ).all()

    submissions = []
    for feedback, email in results:
        res = AppFeedbackResponse.model_validate(feedback)
        res.email = email
        submissions.append(res)

    return submissions
