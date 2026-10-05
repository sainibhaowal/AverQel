from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.models.user import User
from app.auth.rbac import require_permissions
from app.auth.tenancy import TenantContext, get_tenant_context
from app.core.config import get_settings
from app.platform.database.session import get_db, set_db_tenant_context
from app.system.api.admin import require_platform_admin_access
from app.system.models.app_feedback import AppFeedback, FeedbackCampaign
from app.system.models.app_feedback_message import AppFeedbackMessage
from app.system.schemas.app_feedback import (
    AdminFeedbackMessageCreate,
    AppFeedbackCreate,
    AppFeedbackDetailResponse,
    AppFeedbackMessageCreate,
    AppFeedbackMessageResponse,
    AppFeedbackResponse,
    AppFeedbackUpdate,
    FeedbackCampaignCreate,
    FeedbackCampaignResponse,
)
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.user_notifications import add_user_notification, notify_platform_admins

router = APIRouter(prefix="/app-feedback", tags=["app-feedback"])


def _feedback_for_user(
    db: Session, *, feedback_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> AppFeedback:
    feedback = db.execute(
        select(AppFeedback).where(
            AppFeedback.id == feedback_id,
            AppFeedback.tenant_id == tenant_id,
            AppFeedback.user_id == user_id,
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


def _feedback_messages(
    db: Session, *, feedback: AppFeedback, include_internal: bool
) -> list[AppFeedbackMessage]:
    query = select(AppFeedbackMessage).where(
        AppFeedbackMessage.feedback_id == feedback.id,
        AppFeedbackMessage.tenant_id == feedback.tenant_id,
    )
    if not include_internal:
        query = query.where(AppFeedbackMessage.is_internal.is_(False))
    return list(
        db.execute(query.order_by(AppFeedbackMessage.created_at, AppFeedbackMessage.id)).scalars()
    )


def _detail(
    db: Session, feedback: AppFeedback, *, include_internal: bool, email: str | None = None
) -> AppFeedbackDetailResponse:
    response = AppFeedbackResponse.model_validate(feedback)
    response.email = email
    return AppFeedbackDetailResponse(
        **response.model_dump(),
        messages=[
            AppFeedbackMessageResponse.model_validate(item)
            for item in _feedback_messages(db, feedback=feedback, include_internal=include_internal)
        ],
    )


@router.post("/submit", response_model=AppFeedbackResponse)
def submit_app_feedback(
    payload: AppFeedbackCreate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AppFeedbackResponse:
    RateLimitService(get_settings()).enforce_feedback_submission_limit(
        tenant_id=str(tenant.tenant_id), user_id=str(auth.user_id)
    )
    campaign = None
    if payload.campaign_id:
        campaign = db.execute(
            select(FeedbackCampaign).where(
                FeedbackCampaign.id == payload.campaign_id,
                FeedbackCampaign.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=404, detail="Feedback campaign not found")
    feedback = AppFeedback(
        tenant_id=tenant.tenant_id,
        user_id=auth.user_id,
        campaign_id=payload.campaign_id,
        subject=payload.subject.strip(),
        content=payload.content.strip(),
        category=payload.category,
        status="new",
    )
    db.add(feedback)
    db.flush()
    add_user_notification(
        db,
        tenant_id=tenant.tenant_id,
        recipient_user_id=auth.user_id,
        event_domain="feedback",
        event_type="feedback_received",
        title="Feedback received",
        message=f"Thanks for sharing: {feedback.subject}",
        href=f"/dashboard/feedback?feedback={feedback.id}",
        resource_id=str(feedback.id),
        idempotency_key=f"feedback:received:{feedback.id}",
    )
    notify_platform_admins(
        db,
        event_domain="feedback",
        event_type="feedback_submitted",
        title="New user feedback",
        message=f"{feedback.category.replace('_', ' ').title()}: {feedback.subject}",
        href=f"/dashboard/admin/feedback?submission={feedback.id}",
        resource_id=str(feedback.id),
    )
    db.commit()
    return AppFeedbackResponse.model_validate(feedback)


@router.get("/mine", response_model=list[AppFeedbackResponse])
def list_my_feedback(
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[AppFeedbackResponse]:
    items = (
        db.execute(
            select(AppFeedback)
            .where(AppFeedback.tenant_id == tenant.tenant_id, AppFeedback.user_id == auth.user_id)
            .order_by(desc(AppFeedback.updated_at), desc(AppFeedback.id))
            .limit(100)
        )
        .scalars()
        .all()
    )
    return [AppFeedbackResponse.model_validate(item) for item in items]


@router.get("/mine/{feedback_id}", response_model=AppFeedbackDetailResponse)
def get_my_feedback(
    feedback_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AppFeedbackDetailResponse:
    feedback = _feedback_for_user(
        db, feedback_id=feedback_id, tenant_id=tenant.tenant_id, user_id=auth.user_id
    )
    return _detail(db, feedback, include_internal=False)


@router.post("/mine/{feedback_id}/messages", response_model=AppFeedbackDetailResponse)
def add_user_feedback_message(
    feedback_id: uuid.UUID,
    payload: AppFeedbackMessageCreate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AppFeedbackDetailResponse:
    feedback = _feedback_for_user(
        db, feedback_id=feedback_id, tenant_id=tenant.tenant_id, user_id=auth.user_id
    )
    db.add(
        AppFeedbackMessage(
            tenant_id=tenant.tenant_id,
            feedback_id=feedback.id,
            author_user_id=auth.user_id,
            author_role="user",
            body=payload.body.strip(),
        )
    )
    feedback.updated_at = datetime.now(UTC)
    notify_platform_admins(
        db,
        event_domain="feedback",
        event_type="feedback_user_reply",
        title="User added feedback details",
        message=f"New message: {feedback.subject}",
        href=f"/dashboard/admin/feedback?submission={feedback.id}",
        resource_id=f"{feedback.id}:user-reply:{uuid.uuid4()}",
    )
    db.flush()
    detail = _detail(db, feedback, include_internal=False)
    db.commit()
    return detail


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
    limit: int = Query(default=100, ge=1, le=200),
    status: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=50),
    q: str | None = Query(default=None, max_length=200),
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> list[AppFeedbackResponse]:
    set_db_tenant_context(db, "bypass")
    query = (
        select(AppFeedback, User.email)
        .outerjoin(User, User.id == AppFeedback.user_id)
        .order_by(desc(AppFeedback.created_at), desc(AppFeedback.id))
    )
    if status:
        query = query.where(AppFeedback.status == status)
    if category:
        query = query.where(AppFeedback.category == category)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                AppFeedback.subject.ilike(pattern),
                AppFeedback.content.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    results = db.execute(query.limit(limit)).all()
    submissions = []
    for feedback, email in results:
        response = AppFeedbackResponse.model_validate(feedback)
        response.email = email
        submissions.append(response)
    return submissions


@router.get(
    "/admin/submissions/{feedback_id}",
    response_model=AppFeedbackDetailResponse,
    dependencies=[Depends(require_permissions("admin:feedback:read"))],
)
def get_submission_admin(
    feedback_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AppFeedbackDetailResponse:
    set_db_tenant_context(db, "bypass")
    result = db.execute(
        select(AppFeedback, User.email)
        .outerjoin(User, User.id == AppFeedback.user_id)
        .where(AppFeedback.id == feedback_id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return _detail(db, result[0], include_internal=True, email=result[1])


@router.patch(
    "/admin/submissions/{feedback_id}",
    response_model=AppFeedbackResponse,
    dependencies=[Depends(require_permissions("admin:feedback:write"))],
)
def update_submission_admin(
    feedback_id: uuid.UUID,
    payload: AppFeedbackUpdate,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AppFeedbackResponse:
    set_db_tenant_context(db, "bypass")
    feedback = db.get(AppFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    old_status = feedback.status
    if old_status != payload.status:
        feedback.status = payload.status
        feedback.updated_at = datetime.now(UTC)
        db.add(
            AppFeedbackMessage(
                tenant_id=feedback.tenant_id,
                feedback_id=feedback.id,
                author_user_id=auth.user_id,
                author_role="admin",
                kind="status_changed",
                body=f"Feedback status changed from {old_status.replace('_', ' ')} to {payload.status.replace('_', ' ')}.",
            )
        )
        add_user_notification(
            db,
            tenant_id=uuid.UUID(str(feedback.tenant_id)),
            recipient_user_id=uuid.UUID(str(feedback.user_id)),
            event_domain="feedback",
            event_type="feedback_status_changed",
            title="Feedback status updated",
            message=f"Your feedback is now {payload.status.replace('_', ' ')}: {feedback.subject}",
            href=f"/dashboard/feedback?feedback={feedback.id}",
            resource_id=str(feedback.id),
            idempotency_key=f"feedback:status:{feedback.id}:{uuid.uuid4()}",
        )
    db.commit()
    return AppFeedbackResponse.model_validate(feedback)


@router.post(
    "/admin/submissions/{feedback_id}/messages",
    response_model=AppFeedbackDetailResponse,
    dependencies=[Depends(require_permissions("admin:feedback:write"))],
)
def add_admin_feedback_message(
    feedback_id: uuid.UUID,
    payload: AdminFeedbackMessageCreate,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AppFeedbackDetailResponse:
    set_db_tenant_context(db, "bypass")
    feedback = db.get(AppFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    internal = payload.visibility == "internal"
    db.add(
        AppFeedbackMessage(
            tenant_id=feedback.tenant_id,
            feedback_id=feedback.id,
            author_user_id=auth.user_id,
            author_role="admin",
            body=payload.body.strip(),
            is_internal=internal,
        )
    )
    feedback.updated_at = datetime.now(UTC)
    if not internal:
        add_user_notification(
            db,
            tenant_id=uuid.UUID(str(feedback.tenant_id)),
            recipient_user_id=uuid.UUID(str(feedback.user_id)),
            event_domain="feedback",
            event_type="feedback_reply",
            title="AverQel replied to your feedback",
            message=f"There is a new reply about: {feedback.subject}",
            href=f"/dashboard/feedback?feedback={feedback.id}",
            resource_id=str(feedback.id),
            idempotency_key=f"feedback:reply:{uuid.uuid4()}",
        )
    db.flush()
    detail = _detail(db, feedback, include_internal=True)
    db.commit()
    return detail
