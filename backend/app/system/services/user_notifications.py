from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import desc, func, select, text, update
from sqlalchemy.orm import Session

from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.core.config import get_settings
from app.platform.database.session import set_db_tenant_context
from app.system.models.notification_delivery import NotificationDelivery
from app.system.models.user_notification import UserNotification
from app.system.models.user_notification_preference import UserNotificationPreference

logger = logging.getLogger(__name__)


def next_notification_delivery_at(
    *, frequency: str, timezone_name: str, now: datetime | None = None
) -> datetime:
    """Return the next delivery boundary in the recipient's timezone, as UTC."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    if frequency == "none":
        return current
    zone = ZoneInfo(timezone_name or "UTC")
    local_now = current.astimezone(zone)
    candidate = datetime.combine(local_now.date(), time(hour=8), tzinfo=zone)
    if frequency == "weekly":
        candidate += timedelta(days=(7 - local_now.weekday()) % 7)
    if candidate <= local_now:
        candidate += timedelta(days=1 if frequency == "daily" else 7)
    return candidate.astimezone(UTC)


def add_user_notification(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    recipient_user_id: uuid.UUID,
    event_domain: str,
    event_type: str,
    title: str,
    message: str,
    href: str,
    resource_id: uuid.UUID | str | None = None,
    idempotency_key: str | None = None,
) -> UserNotification:
    if idempotency_key:
        existing = db.execute(
            select(UserNotification).where(
                UserNotification.tenant_id == tenant_id,
                UserNotification.recipient_user_id == recipient_user_id,
                UserNotification.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    notification = UserNotification(
        tenant_id=tenant_id,
        recipient_user_id=recipient_user_id,
        event_domain=event_domain,
        event_type=event_type,
        title=title,
        message=message,
        href=href,
        resource_id=str(resource_id) if resource_id is not None else None,
        idempotency_key=idempotency_key,
    )
    db.add(notification)
    db.flush()
    settings = get_settings()
    if settings.notification_smtp_host and settings.notification_smtp_from:
        preference = db.execute(
            select(UserNotificationPreference).where(
                UserNotificationPreference.tenant_id == tenant_id,
                UserNotificationPreference.user_id == recipient_user_id,
            )
        ).scalar_one_or_none()
        user = db.execute(
            select(User).where(User.id == recipient_user_id, User.tenant_id == tenant_id)
        ).scalar_one_or_none()
        muted = set(preference.muted_domains or []) if preference else set()
        if (
            user
            and user.email
            and preference
            and preference.email_enabled
            and event_domain not in muted
        ):
            frequency = preference.digest_frequency or "none"
            due = next_notification_delivery_at(
                frequency=frequency,
                timezone_name=preference.timezone or "UTC",
            )
            db.add(
                NotificationDelivery(
                    tenant_id=tenant_id,
                    notification_id=notification.id,
                    recipient_user_id=recipient_user_id,
                    channel="email",
                    next_attempt_at=due,
                )
            )
    return notification


def list_user_notifications(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
    offset: int = 0,
    muted_domains: list[str] | None = None,
) -> tuple[list[UserNotification], bool]:
    query = select(UserNotification).where(
        UserNotification.tenant_id == tenant_id,
        UserNotification.recipient_user_id == user_id,
        UserNotification.dismissed_at.is_(None),
    )
    if muted_domains:
        query = query.where(UserNotification.event_domain.notin_(muted_domains))
    rows = list(
        db.execute(
            query.order_by(desc(UserNotification.created_at), desc(UserNotification.id))
            .limit(limit + 1)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    return rows[:limit], has_more


def dismiss_user_notifications(db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(UserNotification)
        .where(
            UserNotification.tenant_id == tenant_id,
            UserNotification.recipient_user_id == user_id,
            UserNotification.dismissed_at.is_(None),
        )
        .values(dismissed_at=datetime.now(UTC))
    )
    return int(result.rowcount or 0)


def notify_platform_admins(
    db: Session,
    *,
    event_domain: str,
    event_type: str,
    title: str,
    message: str,
    href: str,
    resource_id: uuid.UUID | str,
) -> None:
    allowlisted_emails = {
        email.strip().lower()
        for email in get_settings().bootstrap_super_admin_emails
        if email.strip()
    }
    if not allowlisted_emails:
        return
    prior_tenant_context = db.execute(
        text("SELECT current_setting('app.tenant_id', true)")
    ).scalar_one_or_none()
    set_db_tenant_context(db, "bypass")
    try:
        admins = (
            db.execute(
                select(User).where(
                    User.is_active.is_(True), func.lower(User.email).in_(allowlisted_emails)
                )
            )
            .scalars()
            .all()
        )
        for admin in admins:
            add_user_notification(
                db,
                tenant_id=admin.tenant_id,
                recipient_user_id=admin.id,
                event_domain=event_domain,
                event_type=event_type,
                title=title,
                message=message,
                href=href,
                resource_id=resource_id,
                idempotency_key=f"{event_domain}:{event_type}:{resource_id}:{admin.id}",
            )
    finally:
        if prior_tenant_context and prior_tenant_context != "bypass":
            set_db_tenant_context(db, prior_tenant_context)


def notify_tenant_admins(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    event_domain: str,
    event_type: str,
    title: str,
    message: str,
    href: str,
    resource_id: uuid.UUID | str,
) -> None:
    """Queue deduplicated in-app alerts for active admins in one tenant."""
    prior_tenant_context = db.execute(
        text("SELECT current_setting('app.tenant_id', true)")
    ).scalar_one_or_none()
    set_db_tenant_context(db, "bypass")
    try:
        try:
            with db.begin_nested():
                admins = (
                    db.execute(
                        select(User.id)
                        .join(UserRole, UserRole.user_id == User.id)
                        .join(Role, Role.id == UserRole.role_id)
                        .where(
                            User.tenant_id == tenant_id,
                            UserRole.tenant_id == tenant_id,
                            Role.name == "admin",
                            User.is_active.is_(True),
                        )
                        .distinct()
                    )
                    .scalars()
                    .all()
                )
        except Exception:
            logger.exception("Could not find tenant admins for collection moderation alert")
            return
        for admin_id in admins:
            try:
                with db.begin_nested():
                    add_user_notification(
                        db,
                        tenant_id=tenant_id,
                        recipient_user_id=admin_id,
                        event_domain=event_domain,
                        event_type=event_type,
                        title=title,
                        message=message,
                        href=href,
                        resource_id=resource_id,
                        idempotency_key=f"{event_domain}:{event_type}:{resource_id}:{admin_id}",
                    )
            except Exception:  # notification delivery must not discard the submitted report
                logger.exception(
                    "Could not enqueue collection moderation alert for tenant admin %s", admin_id
                )
    finally:
        set_db_tenant_context(db, prior_tenant_context or str(tenant_id))
