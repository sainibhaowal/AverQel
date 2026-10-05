from __future__ import annotations

import hashlib
import logging
import smtplib
import ssl
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import parseaddr

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.auth.models.user import User
from app.core.config import get_settings
from app.platform.database.session import managed_db_session, set_db_tenant_context
from app.platform.worker.celery_app import celery_app
from app.system.models.notification_delivery import NotificationDelivery
from app.system.models.support_ticket import SupportTicket
from app.system.models.user_notification import UserNotification
from app.system.services.user_notifications import add_user_notification, notify_platform_admins

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8


def _notify_assigned_admin(
    db: Session,
    *,
    ticket: SupportTicket,
    assigned_admin_tenants: dict[uuid.UUID, uuid.UUID],
    event_type: str,
    title: str,
    message: str,
    resource_id: str,
    idempotency_key: str,
) -> bool:
    """Store a platform-admin alert in the recipient's tenant notification feed."""
    if not ticket.assigned_admin_id:
        return False
    admin_tenant_id = assigned_admin_tenants.get(ticket.assigned_admin_id)
    if not admin_tenant_id:
        return False
    add_user_notification(
        db,
        tenant_id=admin_tenant_id,
        recipient_user_id=ticket.assigned_admin_id,
        event_domain="support",
        event_type=event_type,
        title=title,
        message=message,
        href=f"/dashboard/admin/support?ticket={ticket.id}",
        resource_id=resource_id,
        idempotency_key=idempotency_key,
    )
    return True


def _send_email(*, recipient: str, subject: str, body: str, delivery_id: str) -> None:
    settings = get_settings()
    if not settings.notification_smtp_host or not settings.notification_smtp_from:
        raise RuntimeError("Notification SMTP is not configured")
    message = EmailMessage()
    sender_header = settings.notification_smtp_from
    sender_address = parseaddr(sender_header)[1]
    if not sender_address or "@" not in sender_address:
        raise RuntimeError("Notification sender address is invalid")
    message["From"] = sender_header
    message["To"] = recipient
    message["Subject"] = " ".join(subject.replace("\r", " ").replace("\n", " ").split())[:180]
    message["Message-ID"] = (
        f"<averqel-notification-{delivery_id}@{sender_address.rsplit('@', 1)[-1]}>"
    )
    message.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(
        settings.notification_smtp_host, settings.notification_smtp_port, timeout=15
    ) as client:
        client.ehlo()
        if settings.notification_smtp_starttls:
            client.starttls(context=context)
            client.ehlo()
        if settings.notification_smtp_username:
            client.login(
                settings.notification_smtp_username, settings.notification_smtp_password or ""
            )
        client.send_message(message)


@celery_app.task(name="notifications.dispatch_email_outbox", acks_late=True, max_retries=0)  # type: ignore[misc]
def dispatch_email_outbox(batch_size: int = 50) -> int:
    """Claim and deliver pending email outbox rows, retrying with bounded backoff."""
    delivered = 0
    claimed_ids: list[str] = []
    with managed_db_session() as db:
        set_db_tenant_context(db, "bypass")
        now = datetime.now(UTC)
        rows = (
            db.execute(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.channel == "email",
                    or_(
                        (NotificationDelivery.status == "pending")
                        & (NotificationDelivery.next_attempt_at <= now),
                        (NotificationDelivery.status == "processing")
                        & (NotificationDelivery.leased_until <= now),
                    ),
                )
                .order_by(NotificationDelivery.created_at)
                .with_for_update(skip_locked=True)
                .limit(max(1, min(batch_size, 200)))
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = "processing"
            row.leased_until = now + timedelta(minutes=2)
            claimed_ids.append(str(row.id))
        db.commit()

    # Do not hold database locks or a transaction open while talking to SMTP.
    grouped: dict[str, dict[str, object]] = {}
    if claimed_ids:
        with managed_db_session() as db:
            set_db_tenant_context(db, "bypass")
            joined = db.execute(
                select(NotificationDelivery, UserNotification, User)
                .join(UserNotification, UserNotification.id == NotificationDelivery.notification_id)
                .join(User, User.id == NotificationDelivery.recipient_user_id)
                .where(
                    NotificationDelivery.id.in_(claimed_ids),
                    NotificationDelivery.status == "processing",
                )
            ).all()
            for row, notification, user in joined:
                if not user.email:
                    row.status = "failed"
                    row.last_error = "recipient_email_missing"
                    row.leased_until = None
                    continue
                group = grouped.setdefault(user.email, {"ids": [], "items": []})
                cast_ids = group["ids"]
                cast_items = group["items"]
                assert isinstance(cast_ids, list) and isinstance(cast_items, list)
                cast_ids.append(str(row.id))
                cast_items.append((notification.title, notification.message, notification.href))
            db.commit()
    for recipient, group in grouped.items():
        delivery_ids = group["ids"]
        items = group["items"]
        assert isinstance(delivery_ids, list) and isinstance(items, list)
        stable_id = hashlib.sha256("|".join(sorted(delivery_ids)).encode()).hexdigest()[:32]
        title = "AverQel notification digest" if len(items) > 1 else str(items[0][0])
        email_settings = get_settings()
        public_origin = (
            email_settings.averqel_public_origin
            or (f"https://{email_settings.averqel_domain}" if email_settings.averqel_domain else "")
        ).rstrip("/")
        body = "\n\n".join(
            f"{item_title}\n{message}\nOpen AverQel: {public_origin}{href}"
            for item_title, message, href in items
        )
        try:
            _send_email(recipient=recipient, subject=title, body=body, delivery_id=stable_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Notification email delivery failed",
                extra={"delivery_count": len(delivery_ids)},
                exc_info=True,
            )
            with managed_db_session() as db:
                set_db_tenant_context(db, "bypass")
                rows = (
                    db.execute(
                        select(NotificationDelivery)
                        .where(NotificationDelivery.id.in_(delivery_ids))
                        .with_for_update()
                    )
                    .scalars()
                    .all()
                )
                for row in rows:
                    row.attempts += 1
                    row.last_error = type(exc).__name__[:100]
                    row.leased_until = None
                    if row.attempts >= MAX_ATTEMPTS:
                        row.status = "failed"
                    else:
                        row.status = "pending"
                        row.next_attempt_at = datetime.now(UTC) + timedelta(
                            seconds=min(3600, 30 * (2 ** (row.attempts - 1)))
                        )
                db.commit()
        else:
            with managed_db_session() as db:
                set_db_tenant_context(db, "bypass")
                rows = (
                    db.execute(
                        select(NotificationDelivery)
                        .where(NotificationDelivery.id.in_(delivery_ids))
                        .with_for_update()
                    )
                    .scalars()
                    .all()
                )
                for row in rows:
                    row.status = "delivered"
                    row.delivered_at = datetime.now(UTC)
                    row.leased_until = None
                    row.last_error = None
                db.commit()
                delivered += len(rows)
    return delivered


@celery_app.task(name="notifications.check_support_sla", acks_late=True, max_retries=0)  # type: ignore[misc]
def check_support_sla(batch_size: int = 500) -> int:
    now = datetime.now(UTC)
    emitted = 0
    with managed_db_session() as db:
        set_db_tenant_context(db, "bypass")
        tickets = (
            db.execute(
                select(SupportTicket)
                .where(
                    SupportTicket.status.notin_(["resolved", "closed"]),
                    or_(
                        SupportTicket.resolution_due_at < now,
                        (SupportTicket.first_response_at.is_(None))
                        & (SupportTicket.first_response_due_at < now),
                    ),
                )
                .order_by(SupportTicket.created_at)
                .limit(max(1, min(batch_size, 2000)))
            )
            .scalars()
            .all()
        )
        assigned_admin_ids = {
            ticket.assigned_admin_id for ticket in tickets if ticket.assigned_admin_id
        }
        assigned_admin_tenants: dict[uuid.UUID, uuid.UUID] = {}
        if assigned_admin_ids:
            for admin_id, tenant_id in db.execute(
                select(User.id, User.tenant_id).where(User.id.in_(assigned_admin_ids))
            ).tuples():
                assigned_admin_tenants[admin_id] = tenant_id
        for ticket in tickets:
            if (
                ticket.first_response_at is None
                and ticket.first_response_due_at
                and ticket.first_response_due_at < now
            ):
                resource = f"{ticket.id}:first-response:{ticket.first_response_due_at.isoformat()}"
                notify_platform_admins(
                    db,
                    event_domain="support",
                    event_type="sla_first_response_breached",
                    title="Support first-response SLA breached",
                    message=f"Ticket {ticket.id} has not received a public response by its deadline.",
                    href=f"/dashboard/admin/support?ticket={ticket.id}",
                    resource_id=resource,
                )
                _notify_assigned_admin(
                    db,
                    ticket=ticket,
                    assigned_admin_tenants=assigned_admin_tenants,
                    event_type="sla_first_response_breached",
                    title="Your support ticket is overdue",
                    message=f"Ticket {ticket.id} has passed its first-response deadline.",
                    resource_id=resource,
                    idempotency_key=f"support:sla:first:{ticket.id}:{ticket.first_response_due_at.isoformat()}:{ticket.assigned_admin_id}",
                )
                emitted += 1
            if ticket.resolution_due_at and ticket.resolution_due_at < now:
                resource = f"{ticket.id}:resolution:{ticket.resolution_due_at.isoformat()}"
                notify_platform_admins(
                    db,
                    event_domain="support",
                    event_type="sla_resolution_breached",
                    title="Support resolution SLA breached",
                    message=f"Ticket {ticket.id} remains unresolved beyond its deadline.",
                    href=f"/dashboard/admin/support?ticket={ticket.id}",
                    resource_id=resource,
                )
                _notify_assigned_admin(
                    db,
                    ticket=ticket,
                    assigned_admin_tenants=assigned_admin_tenants,
                    event_type="sla_resolution_breached",
                    title="Your support ticket is past its resolution deadline",
                    message=f"Ticket {ticket.id} remains unresolved beyond its deadline.",
                    resource_id=resource,
                    idempotency_key=f"support:sla:resolution:{ticket.id}:{ticket.resolution_due_at.isoformat()}:{ticket.assigned_admin_id}",
                )
                emitted += 1
        db.commit()
    return emitted


@celery_app.task(name="notifications.cleanup_retention", acks_late=True, max_retries=0)  # type: ignore[misc]
def cleanup_notification_retention() -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    with managed_db_session() as db:
        set_db_tenant_context(db, "bypass")
        notifications = db.execute(
            delete(UserNotification).where(
                UserNotification.dismissed_at.is_not(None),
                UserNotification.dismissed_at
                < now - timedelta(days=settings.notification_retention_days),
            )
        )
        deliveries = db.execute(
            delete(NotificationDelivery).where(
                NotificationDelivery.status == "delivered",
                NotificationDelivery.created_at
                < now - timedelta(days=settings.notification_delivery_retention_days),
            )
        )
        db.commit()
        return {
            "notifications": int(notifications.rowcount or 0),
            "deliveries": int(deliveries.rowcount or 0),
        }
