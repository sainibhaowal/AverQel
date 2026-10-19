from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.auth.tenancy import TenantContext, get_tenant_context
from app.core.config import get_settings
from app.platform.database.session import get_db, set_db_tenant_context
from app.system.api.admin import require_platform_admin_access
from app.system.models.app_feedback import AppFeedback, FeedbackCampaign
from app.system.models.app_feedback_message import AppFeedbackMessage
from app.system.models.support_encryption_key import SupportEncryptionKey
from app.system.schemas.app_feedback import (
    AdminAppFeedbackDetailResponse,
    AdminAppFeedbackMessageResponse,
    AdminAppFeedbackResponse,
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
from app.system.schemas.support_encryption import (
    FeedbackRecordEncryptionMigration,
    LegacyFeedbackRecord,
    LegacyFeedbackRecordPage,
)
from app.system.services.audit_service import AuditService
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.support_encryption import EncryptedPayloadError, validate_payload
from app.system.services.user_notifications import (
    add_user_notification,
    notify_platform_admins,
)

router = APIRouter(prefix="/app-feedback", tags=["app-feedback"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"


def _feedback_key_ids(
    db: Session, *, user_id: uuid.UUID, tenant_id_to_restore: uuid.UUID | None = None
) -> set[str]:
    set_db_tenant_context(db, "bypass")
    rows = (
        db.execute(
            select(SupportEncryptionKey).where(
                (SupportEncryptionKey.scope == "platform_admin")
                | (
                    (SupportEncryptionKey.scope == "user")
                    & (SupportEncryptionKey.user_id == user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    admin_key = next((row for row in rows if row.scope == "platform_admin"), None)
    user_key = next((row for row in rows if row.scope == "user" and row.user_id == user_id), None)
    if tenant_id_to_restore is not None:
        set_db_tenant_context(db, tenant_id_to_restore)
    if admin_key is None or user_key is None:
        raise HTTPException(status_code=409, detail="Support encryption keys are not initialized")
    return {admin_key.key_id, user_key.key_id}


def _admin_feedback_key_id(db: Session, *, admin_user_id: uuid.UUID) -> str:
    set_db_tenant_context(db, "bypass")
    row = db.execute(
        select(SupportEncryptionKey).where(SupportEncryptionKey.scope == "platform_admin")
    ).scalar_one_or_none()
    if row is None or row.user_id != admin_user_id:
        raise HTTPException(status_code=409, detail="Admin support encryption key is unavailable")
    return row.key_id


def _validate_encrypted_payload(payload: str, expected_key_ids: set[str]) -> None:
    try:
        validate_payload(payload, expected_key_ids)
    except EncryptedPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def require_feedback_review_access(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Require a verified platform administrator for global feedback access."""
    return require_platform_admin_access(auth=auth, db=db, settings=get_settings())


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


def _admin_detail(db: Session, feedback: AppFeedback) -> AdminAppFeedbackDetailResponse:
    user_key = db.execute(
        select(SupportEncryptionKey).where(
            SupportEncryptionKey.user_id == feedback.user_id,
            SupportEncryptionKey.scope == "user",
        )
    ).scalar_one_or_none()
    return AdminAppFeedbackDetailResponse(
        **AdminAppFeedbackResponse.model_validate(feedback).model_dump(),
        recipient_public_key=(
            {"key_id": user_key.key_id, "public_key": user_key.public_key}
            if user_key is not None
            else None
        ),
        messages=[
            AdminAppFeedbackMessageResponse.model_validate(item)
            for item in _feedback_messages(db, feedback=feedback, include_internal=True)
        ],
    )


@router.post("/submit", response_model=AppFeedbackResponse)
def submit_app_feedback(
    payload: AppFeedbackCreate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AppFeedbackResponse:
    _validate_encrypted_payload(
        payload.encrypted_payload,
        _feedback_key_ids(db, user_id=auth.user_id, tenant_id_to_restore=tenant.tenant_id),
    )
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
        subject="[Encrypted feedback]",
        content="[Encrypted]",
        encrypted_payload=payload.encrypted_payload,
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
        message="Your encrypted feedback was received.",
        href=f"/dashboard/feedback?feedback={feedback.id}",
        resource_id=str(feedback.id),
        idempotency_key=f"feedback:received:{feedback.id}",
    )
    notify_platform_admins(
        db,
        event_domain="feedback",
        event_type="feedback_submitted",
        title="New user feedback",
        message="A user submitted feedback for review.",
        href=f"/dashboard/admin/feedback?submission={feedback.id}",
        resource_id=feedback.id,
    )
    db.commit()
    return AppFeedbackResponse.model_validate(feedback)


@router.get("/mine", response_model=list[AppFeedbackResponse])
def list_my_feedback(
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[AppFeedbackResponse]:
    _no_store(response)
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
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AppFeedbackDetailResponse:
    _no_store(response)
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
    _validate_encrypted_payload(
        payload.encrypted_payload,
        _feedback_key_ids(db, user_id=auth.user_id, tenant_id_to_restore=tenant.tenant_id),
    )
    db.add(
        AppFeedbackMessage(
            tenant_id=tenant.tenant_id,
            feedback_id=feedback.id,
            author_user_id=auth.user_id,
            author_role="user",
            body="[Encrypted message]",
            encrypted_payload=payload.encrypted_payload,
        )
    )
    feedback.updated_at = datetime.now(UTC)
    reply_event_id = f"{feedback.id}:user-reply:{uuid.uuid4()}"
    notify_platform_admins(
        db,
        event_domain="feedback",
        event_type="feedback_user_reply",
        title="User added feedback details",
        message="A user added details to a feedback submission.",
        href=f"/dashboard/admin/feedback?submission={feedback.id}",
        resource_id=reply_event_id,
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
    dependencies=[
        Depends(require_permissions("admin:feedback:write")),
        Depends(require_feedback_review_access),
    ],
)
def create_campaign(
    payload: FeedbackCampaignCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> FeedbackCampaignResponse:
    campaign = FeedbackCampaign(**payload.model_dump())
    db.add(campaign)
    db.flush()
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.feedback.campaign.created",
        resource_type="feedback_campaign",
        resource_id=str(campaign.id),
    )
    db.commit()
    db.refresh(campaign)
    return FeedbackCampaignResponse.model_validate(campaign)


@router.get(
    "/admin/submissions",
    response_model=list[AdminAppFeedbackResponse],
    dependencies=[
        Depends(require_permissions("admin:feedback:read")),
        Depends(require_feedback_review_access),
    ],
)
def list_all_submissions(
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    status: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=50),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AdminAppFeedbackResponse]:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    query = select(AppFeedback).order_by(desc(AppFeedback.created_at), desc(AppFeedback.id))
    if status:
        query = query.where(AppFeedback.status == status)
    if category:
        query = query.where(AppFeedback.category == category)
    rows = db.execute(query.limit(limit)).scalars().all()
    submissions = [AdminAppFeedbackResponse.model_validate(feedback) for feedback in rows]
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.feedback.submissions.list.read",
        resource_type="app_feedback_submissions",
    )
    return submissions


@router.get(
    "/admin/submissions/{feedback_id}",
    response_model=AdminAppFeedbackDetailResponse,
    dependencies=[
        Depends(require_permissions("admin:feedback:read")),
        Depends(require_feedback_review_access),
    ],
)
def get_submission_admin(
    feedback_id: uuid.UUID,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AdminAppFeedbackDetailResponse:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    feedback = db.execute(
        select(AppFeedback).where(AppFeedback.id == feedback_id)
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    detail = _admin_detail(db, feedback)
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.feedback.submission.read",
        resource_type="app_feedback_submission",
        resource_id=str(feedback_id),
    )
    return detail


@router.get(
    "/admin/encryption/legacy",
    response_model=LegacyFeedbackRecordPage,
    dependencies=[
        Depends(require_permissions("admin:feedback:read")),
        Depends(require_feedback_review_access),
    ],
)
def list_legacy_feedback_records(
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LegacyFeedbackRecordPage:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    has_legacy_messages = exists(
        select(1).where(
            AppFeedbackMessage.feedback_id == AppFeedback.id,
            AppFeedbackMessage.encrypted_payload.is_(None),
            AppFeedbackMessage.author_role != "system",
        )
    )
    legacy_filter = or_(AppFeedback.encrypted_payload.is_(None), has_legacy_messages)
    total = db.scalar(select(func.count()).select_from(AppFeedback).where(legacy_filter)) or 0
    rows = db.execute(
        select(AppFeedback.id, AppFeedback.user_id)
        .where(legacy_filter)
        .order_by(AppFeedback.created_at, AppFeedback.id)
        .limit(limit)
        .offset(offset)
    ).all()
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.feedback.encryption.legacy.list.read",
        resource_type="feedback_encryption_migration",
    )
    return LegacyFeedbackRecordPage(
        items=[LegacyFeedbackRecord(id=row.id, user_id=row.user_id) for row in rows],
        total=int(total),
    )


@router.put(
    "/admin/submissions/{feedback_id}/encryption",
    response_model=AdminAppFeedbackDetailResponse,
    dependencies=[
        Depends(require_permissions("admin:feedback:write")),
        Depends(require_feedback_review_access),
    ],
)
def encrypt_legacy_feedback_record(
    feedback_id: uuid.UUID,
    payload: FeedbackRecordEncryptionMigration,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AdminAppFeedbackDetailResponse:
    set_db_tenant_context(db, "bypass")
    feedback = db.get(AppFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if feedback.encrypted_payload is None:
        if payload.encrypted_payload is None:
            raise HTTPException(status_code=422, detail="Encrypted feedback content is required")
        conversation_key_ids = _feedback_key_ids(db, user_id=feedback.user_id)
        _validate_encrypted_payload(payload.encrypted_payload, conversation_key_ids)
        feedback.encrypted_payload = payload.encrypted_payload
        feedback.subject = "[Encrypted feedback]"
        feedback.content = "[Encrypted]"
    elif payload.encrypted_payload is not None:
        raise HTTPException(status_code=409, detail="Feedback content is already encrypted")

    legacy_messages = (
        db.execute(
            select(AppFeedbackMessage).where(
                AppFeedbackMessage.feedback_id == feedback.id,
                AppFeedbackMessage.encrypted_payload.is_(None),
                AppFeedbackMessage.author_role != "system",
            )
        )
        .scalars()
        .all()
    )
    expected_message_ids = {message.id for message in legacy_messages}
    supplied_messages = {message.id: message.encrypted_payload for message in payload.messages}
    if (
        len(supplied_messages) != len(payload.messages)
        or set(supplied_messages) != expected_message_ids
    ):
        raise HTTPException(
            status_code=422, detail="Migration must include each legacy message once"
        )
    conversation_key_ids = _feedback_key_ids(db, user_id=feedback.user_id)
    admin_key_id = _admin_feedback_key_id(db, admin_user_id=auth.user_id)
    for message in legacy_messages:
        ciphertext = supplied_messages[message.id]
        recipients = {admin_key_id} if message.is_internal else conversation_key_ids
        _validate_encrypted_payload(ciphertext, recipients)
        message.encrypted_payload = ciphertext
        message.body = "[Encrypted message]"

    db.flush()
    detail = _admin_detail(db, feedback)
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.feedback.encryption.legacy.migrated",
        resource_type="app_feedback_submission",
        resource_id=str(feedback.id),
    )
    db.commit()
    return detail


@router.patch(
    "/admin/submissions/{feedback_id}",
    response_model=AdminAppFeedbackResponse,
    dependencies=[
        Depends(require_permissions("admin:feedback:write")),
        Depends(require_feedback_review_access),
    ],
)
def update_submission_admin(
    feedback_id: uuid.UUID,
    payload: AppFeedbackUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AdminAppFeedbackResponse:
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
            message=f"Your feedback status changed to {payload.status.replace('_', ' ')}.",
            href=f"/dashboard/feedback?feedback={feedback.id}",
            resource_id=str(feedback.id),
            idempotency_key=f"feedback:status:{feedback.id}:{uuid.uuid4()}",
        )
        AuditService(db).write_event(
            tenant_id=auth.tenant_id,
            actor_user_id=auth.user_id,
            action="admin.feedback.submission.updated",
            resource_type="app_feedback_submission",
            resource_id=str(feedback.id),
        )
    db.commit()
    return AdminAppFeedbackResponse.model_validate(feedback)


@router.post(
    "/admin/submissions/{feedback_id}/messages",
    response_model=AdminAppFeedbackDetailResponse,
    dependencies=[
        Depends(require_permissions("admin:feedback:write")),
        Depends(require_feedback_review_access),
    ],
)
def add_admin_feedback_message(
    feedback_id: uuid.UUID,
    payload: AdminFeedbackMessageCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AdminAppFeedbackDetailResponse:
    set_db_tenant_context(db, "bypass")
    feedback = db.get(AppFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    internal = payload.visibility == "internal"
    admin_key_id = _admin_feedback_key_id(db, admin_user_id=auth.user_id)
    expected_key_ids = (
        {admin_key_id} if internal else _feedback_key_ids(db, user_id=feedback.user_id)
    )
    _validate_encrypted_payload(payload.encrypted_payload, expected_key_ids)
    db.add(
        AppFeedbackMessage(
            tenant_id=feedback.tenant_id,
            feedback_id=feedback.id,
            author_user_id=auth.user_id,
            author_role="admin",
            body="[Encrypted message]",
            encrypted_payload=payload.encrypted_payload,
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
            message="There is a new encrypted reply to your feedback.",
            href=f"/dashboard/feedback?feedback={feedback.id}",
            resource_id=str(feedback.id),
            idempotency_key=f"feedback:reply:{uuid.uuid4()}",
        )
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.feedback.message.created",
        resource_type="app_feedback_submission",
        resource_id=str(feedback.id),
    )
    db.flush()
    detail = _admin_detail(db, feedback)
    db.commit()
    return detail
