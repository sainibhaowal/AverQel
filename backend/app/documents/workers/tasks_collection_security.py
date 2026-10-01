"""Durable Web Push delivery for collection notifications."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - dependency is installed in worker images
    WebPushException = RuntimeError
    webpush = None

from app.core.config import get_settings
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.collection_security import (
    CollectionPushDelivery,
    CollectionPushSubscription,
)
from app.integrations.services.connector_secret_crypto import (
    ConnectorSecretCrypto,
    ConnectorSecretCryptoError,
)
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 8


def _send(subscription: CollectionPushSubscription, payload: dict[str, str]) -> None:
    settings = get_settings()
    if not settings.web_push_vapid_private_key or not settings.web_push_subject:
        raise RuntimeError("web push VAPID credentials are not configured")
    if webpush is None:
        raise RuntimeError("pywebpush is not installed in this worker image")
    auth = ConnectorSecretCrypto(settings).decrypt(
        ciphertext=subscription.auth_ciphertext,
        nonce=subscription.auth_nonce,
        kid=subscription.auth_kid,
        aad=f"collection-push:{subscription.tenant_id}:{subscription.user_id}".encode(),
    ).decode("utf-8")
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": auth},
        },
        data=json.dumps(payload, separators=(",", ":")),
        vapid_private_key=settings.web_push_vapid_private_key,
        vapid_claims={"sub": settings.web_push_subject},
        timeout=10,
    )


@celery_app.task(name="collections.dispatch_push_outbox")  # type: ignore[misc]
def dispatch_collection_push_outbox(*, limit: int = 100) -> int:
    """Claim and deliver committed push outbox rows with bounded retries."""
    session = get_session_factory()()
    processed = 0
    try:
        set_db_tenant_context(session, "bypass")
        now = datetime.now(UTC)
        rows = (
            session.query(CollectionPushDelivery)
            .filter(
                CollectionPushDelivery.status.in_(("queued", "retrying")),
                (CollectionPushDelivery.next_attempt_at.is_(None) | (CollectionPushDelivery.next_attempt_at <= now)),
            )
            .order_by(CollectionPushDelivery.created_at.asc(), CollectionPushDelivery.id.asc())
            .with_for_update(skip_locked=True)
            .limit(max(1, min(limit, 500)))
            .all()
        )
        for delivery in rows:
            delivery.status = "delivering"
            delivery.attempt_count = int(delivery.attempt_count or 0) + 1
            session.flush()
            notification = session.get(CollectionNotification, delivery.notification_id)
            subscriptions = (
                session.query(CollectionPushSubscription)
                .filter(
                    CollectionPushSubscription.user_id == delivery.recipient_user_id,
                    CollectionPushSubscription.active.is_(True),
                )
                .all()
                if notification is not None
                else []
            )
            payload = (
                {
                    "title": notification.collection_name,
                    "body": notification.message,
                    "event_type": notification.event_type,
                    "notification_id": str(notification.id),
                }
                if notification is not None
                else {}
            )
            if not subscriptions:
                delivery.status = "delivered"
                delivery.completed_at = now
                processed += 1
                continue
            failures = []
            delivered = False
            for subscription in subscriptions:
                try:
                    _send(subscription, payload)
                    delivered = True
                    subscription.failure_count = 0
                except WebPushException as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status in {404, 410}:
                        subscription.active = False
                    subscription.failure_count = int(subscription.failure_count or 0) + 1
                    failures.append(str(exc)[:500])
                except (ConnectorSecretCryptoError, RuntimeError, OSError, ValueError) as exc:
                    failures.append(str(exc)[:500])
            if delivered:
                delivery.status = "delivered"
                delivery.completed_at = now
                delivery.last_error = None
            elif delivery.attempt_count >= _MAX_ATTEMPTS:
                delivery.status = "failed"
                delivery.completed_at = now
                delivery.last_error = "; ".join(failures)[:2000]
            else:
                delivery.status = "retrying"
                delivery.next_attempt_at = now + timedelta(seconds=min(900, 2 ** delivery.attempt_count * 5))
                delivery.last_error = "; ".join(failures)[:2000]
            processed += 1
        session.commit()
        return processed
    finally:
        session.close()
