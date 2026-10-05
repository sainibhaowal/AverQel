from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.tenancy import TenantContext, get_tenant_context
from app.core.config import get_settings
from app.core.errors import ApiError
from app.platform.database.session import get_db
from app.system.models.user_notification import UserNotification
from app.system.models.user_notification_preference import UserNotificationPreference
from app.system.schemas.notifications import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    UserNotificationResponse,
)
from app.system.services.user_notifications import (
    dismiss_user_notifications,
    list_user_notifications,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/preferences", response_model=NotificationPreferenceResponse)
def get_notification_preferences(
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> NotificationPreferenceResponse:
    row = db.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.tenant_id == tenant.tenant_id,
            UserNotificationPreference.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return NotificationPreferenceResponse(
            email_enabled=False,
            digest_frequency="none",
            muted_domains=[],
            email_delivery_available=bool(
                get_settings().notification_smtp_host and get_settings().notification_smtp_from
            ),
        )
    return NotificationPreferenceResponse(
        email_enabled=row.email_enabled,
        digest_frequency=row.digest_frequency,
        muted_domains=row.muted_domains or [],
        email_delivery_available=bool(
            get_settings().notification_smtp_host and get_settings().notification_smtp_from
        ),
    )


@router.put("/preferences", response_model=NotificationPreferenceResponse)
def update_notification_preferences(
    payload: NotificationPreferenceUpdate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> NotificationPreferenceResponse:
    row = db.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.tenant_id == tenant.tenant_id,
            UserNotificationPreference.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserNotificationPreference(tenant_id=tenant.tenant_id, user_id=auth.user_id)
        db.add(row)
    values = payload.model_dump(exclude_unset=True)
    if values.get("email_enabled") and not (
        get_settings().notification_smtp_host and get_settings().notification_smtp_from
    ):
        raise ApiError(
            code="NOTIFICATION_EMAIL_UNAVAILABLE",
            message="Email delivery is not configured for this deployment.",
            status_code=422,
        )
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    return NotificationPreferenceResponse(
        email_enabled=row.email_enabled,
        digest_frequency=row.digest_frequency,
        muted_domains=row.muted_domains or [],
        email_delivery_available=bool(
            get_settings().notification_smtp_host and get_settings().notification_smtp_from
        ),
    )


def _owned_notification(
    db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
) -> UserNotification:
    item = db.execute(
        select(UserNotification).where(
            UserNotification.id == notification_id,
            UserNotification.tenant_id == tenant_id,
            UserNotification.recipient_user_id == user_id,
            UserNotification.dismissed_at.is_(None),
        )
    ).scalar_one_or_none()
    if item is None:
        raise ApiError(
            code="NOTIFICATION_NOT_FOUND", message="Notification not found.", status_code=404
        )
    return item


@router.get("", response_model=list[UserNotificationResponse])
def list_notifications(
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[UserNotificationResponse]:
    muted_domains = (
        db.execute(
            select(UserNotificationPreference.muted_domains).where(
                UserNotificationPreference.tenant_id == tenant.tenant_id,
                UserNotificationPreference.user_id == auth.user_id,
            )
        ).scalar_one_or_none()
        or []
    )
    items, has_more = list_user_notifications(
        db,
        tenant_id=tenant.tenant_id,
        user_id=auth.user_id,
        limit=limit,
        offset=offset,
        muted_domains=muted_domains,
    )
    response.headers["X-Has-More"] = "true" if has_more else "false"
    return [UserNotificationResponse.model_validate(item) for item in items]


@router.post("/{notification_id}/read", response_model=UserNotificationResponse)
def mark_notification_read(
    notification_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> UserNotificationResponse:
    item = _owned_notification(
        db, tenant_id=tenant.tenant_id, user_id=auth.user_id, notification_id=notification_id
    )
    item.read_at = item.read_at or datetime.now(UTC)
    db.commit()
    return UserNotificationResponse.model_validate(item)


@router.post("/read-all", status_code=204)
def mark_all_notifications_read(
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Response:
    db.execute(
        update(UserNotification)
        .where(
            UserNotification.tenant_id == tenant.tenant_id,
            UserNotification.recipient_user_id == auth.user_id,
            UserNotification.dismissed_at.is_(None),
            UserNotification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return Response(status_code=204)


@router.delete("/{notification_id}", status_code=204)
def dismiss_notification(
    notification_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Response:
    item = _owned_notification(
        db, tenant_id=tenant.tenant_id, user_id=auth.user_id, notification_id=notification_id
    )
    item.dismissed_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.delete("", status_code=204)
def clear_notifications(
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Response:
    dismiss_user_notifications(db, tenant_id=tenant.tenant_id, user_id=auth.user_id)
    db.commit()
    return Response(status_code=204)
