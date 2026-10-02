from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from celery.exceptions import MaxRetriesExceededError  # type: ignore[import-untyped]
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.organization import DocumentWebhookDelivery, DocumentWebhookSubscription
from app.documents.services.webhook_security import WebhookEndpointError, validate_webhook_endpoint
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_MAX_FAILURES_BEFORE_DISABLE = 10
_STALE_DELIVERY_AFTER = timedelta(minutes=20)


def _signature(secret: bytes, payload: bytes, timestamp: str | None = None) -> str:
    """Return the v2 timestamp-bound signature, or the legacy body signature."""
    message = payload if timestamp is None else timestamp.encode() + b"." + payload
    return "sha256=" + hmac.new(secret, message, hashlib.sha256).hexdigest()


def _event_with_identity(event: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(event)
    normalized.setdefault("event_id", str(uuid.uuid4()))
    return normalized


def _delivery_event(delivery: DocumentWebhookDelivery, event: dict[str, Any]) -> dict[str, Any]:
    stored = dict(delivery.payload or {})
    if not stored:
        stored = dict(event)
    stored.setdefault("type", delivery.event_type)
    if delivery.event_id:
        stored.setdefault("event_id", delivery.event_id)
    return _event_with_identity(stored)


def _latest_attempt_started(delivery: DocumentWebhookDelivery) -> datetime | None:
    history = list(delivery.attempt_history or [])
    if not history:
        return None
    value = history[-1].get("started_at")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _claim_delivery(
    session: Session,
    *,
    subscription_id: uuid.UUID,
    delivery_id: uuid.UUID,
    tenant_id: uuid.UUID,
    event: dict[str, Any],
) -> tuple[DocumentWebhookSubscription, DocumentWebhookDelivery, dict[str, Any]] | None:
    """Atomically claim a delivery so an outbox scan and a task cannot double-send it."""
    subscription = (
        session.query(DocumentWebhookSubscription)
        .filter(
            DocumentWebhookSubscription.id == subscription_id,
            DocumentWebhookSubscription.tenant_id == tenant_id,
        )
        .first()
    )
    delivery = (
        session.query(DocumentWebhookDelivery)
        .filter(
            DocumentWebhookDelivery.id == delivery_id,
            DocumentWebhookDelivery.tenant_id == tenant_id,
            DocumentWebhookDelivery.subscription_id == subscription_id,
        )
        .with_for_update()
        .first()
    )
    if subscription is None or delivery is None:
        return None
    if delivery.status == "delivered":
        return None
    if not subscription.active:
        delivery.status = "skipped"
        delivery.error_message = "Webhook is inactive."
        delivery.completed_at = datetime.now(UTC)
        session.commit()
        return None
    if delivery.status == "delivering":
        started = _latest_attempt_started(delivery)
        if started and datetime.now(UTC) - started < _STALE_DELIVERY_AFTER:
            return None

    delivery.status = "delivering"
    delivery.next_attempt_at = None
    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    attempt_started = datetime.now(UTC)
    history = list(delivery.attempt_history or [])
    history.append(
        {
            "attempt": delivery.attempt_count,
            "started_at": attempt_started.isoformat(),
            "status": "delivering",
        }
    )
    delivery.attempt_history = history
    session.commit()
    return subscription, delivery, _delivery_event(delivery, event)


def _record_failure(
    session: Session,
    *,
    subscription: DocumentWebhookSubscription,
    delivery: DocumentWebhookDelivery,
    error: Exception,
    response_status: int | None,
    retry_count: int,
    max_retries: int,
) -> tuple[str, int]:
    message = str(error)[:2000]
    subscription.failure_count = int(subscription.failure_count or 0) + 1
    subscription.last_error = message
    delivery.response_status = response_status
    should_retry = (
        retry_count < max_retries and subscription.failure_count < _MAX_FAILURES_BEFORE_DISABLE
    )
    status = "retrying" if should_retry else "failed"
    delay = min(900, 30 * (2**retry_count))
    delivery.status = status
    delivery.error_message = message
    delivery.completed_at = None if should_retry else datetime.now(UTC)
    delivery.next_attempt_at = (
        datetime.now(UTC) + timedelta(seconds=delay) if should_retry else None
    )
    history = list(delivery.attempt_history or [])
    if history:
        history[-1].update(
            {
                "status": status,
                "response_status": response_status,
                "error": message,
                "completed_at": (
                    delivery.completed_at.isoformat() if delivery.completed_at else None
                ),
            }
        )
    delivery.attempt_history = history
    if subscription.failure_count >= _MAX_FAILURES_BEFORE_DISABLE:
        subscription.active = False
        subscription.disabled_reason = f"Automatically disabled after {subscription.failure_count} consecutive delivery failures."
        delivery.status = "failed"
        delivery.completed_at = datetime.now(UTC)
        delivery.next_attempt_at = None
    session.commit()
    return status, delay


@celery_app.task(name="documents.dispatch_webhooks")
def dispatch_document_webhooks(*, tenant_id: str, event: dict[str, Any]) -> int:
    """Persist matching deliveries before attempting to enqueue any network work."""
    session: Session = get_session_factory()()
    tenant_uuid = uuid.UUID(tenant_id)
    normalized_event = _event_with_identity(event)
    try:
        set_db_tenant_context(session, tenant_uuid)
        event_type = str(normalized_event.get("type") or "")
        subscriptions = (
            session.query(DocumentWebhookSubscription)
            .filter(
                DocumentWebhookSubscription.tenant_id == tenant_uuid,
                DocumentWebhookSubscription.active.is_(True),
            )
            .all()
        )
        queued: list[tuple[uuid.UUID, uuid.UUID]] = []
        for subscription in subscriptions:
            if event_type not in set(subscription.event_types or []):
                continue
            delivery = DocumentWebhookDelivery(
                id=generate_uuid7_with_fallback(),
                tenant_id=tenant_uuid,
                subscription_id=subscription.id,
                event_type=event_type or "document.event",
                event_id=str(normalized_event["event_id"]),
                payload=normalized_event,
            )
            try:
                with session.begin_nested():
                    session.add(delivery)
                    session.flush()
            except IntegrityError:
                # The unique tenant/subscription/event key makes redelivered source
                # events idempotent. The existing durable row remains authoritative.
                continue
            queued.append((subscription.id, delivery.id))
        session.commit()
    finally:
        session.close()

    # Queue only after commit. If the broker is unavailable, the committed queued
    # rows are recovered by the periodic outbox dispatcher.
    for subscription_id, delivery_id in queued:
        try:
            deliver_document_webhook.delay(
                subscription_id=str(subscription_id),
                delivery_id=str(delivery_id),
                tenant_id=tenant_id,
                event=normalized_event,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Webhook delivery left in durable outbox because queueing failed",
                extra={"subscription_id": str(subscription_id), "delivery_id": str(delivery_id)},
            )
    return len(queued)


@celery_app.task(name="documents.dispatch_pending_webhook_deliveries")
def dispatch_pending_webhook_deliveries(*, limit: int = 100) -> int:
    """Recover committed deliveries when a broker/worker was temporarily unavailable."""
    session: Session = get_session_factory()()
    now = datetime.now(UTC)
    try:
        # This is the only cross-tenant worker query. The following delivery
        # task immediately restores the concrete tenant context before reading
        # or sending any payload.
        set_db_tenant_context(session, "bypass")
        rows = (
            session.query(DocumentWebhookDelivery)
            .filter(
                or_(
                    DocumentWebhookDelivery.status == "queued",
                    and_(
                        DocumentWebhookDelivery.status == "retrying",
                        DocumentWebhookDelivery.next_attempt_at <= now,
                    ),
                )
            )
            .order_by(DocumentWebhookDelivery.created_at.asc(), DocumentWebhookDelivery.id.asc())
            .limit(max(1, min(limit, 500)))
            .all()
        )
        work = [
            (row.subscription_id, row.id, row.tenant_id, dict(row.payload or {})) for row in rows
        ]
    finally:
        session.close()
    queued = 0
    for subscription_id, delivery_id, tenant_id, event in work:
        try:
            deliver_document_webhook.delay(
                subscription_id=str(subscription_id),
                delivery_id=str(delivery_id),
                tenant_id=str(tenant_id),
                event=event,
            )
            queued += 1
        except Exception:  # noqa: BLE001
            logger.exception(
                "Webhook outbox delivery remains queued", extra={"delivery_id": str(delivery_id)}
            )
    return queued


@celery_app.task(bind=True, name="documents.deliver_webhook", max_retries=5)
def deliver_document_webhook(
    self, *, subscription_id: str, delivery_id: str, tenant_id: str, event: dict[str, Any]
) -> bool:
    session: Session = get_session_factory()()
    tenant_uuid = uuid.UUID(tenant_id)
    try:
        set_db_tenant_context(session, tenant_uuid)
        claimed = _claim_delivery(
            session,
            subscription_id=uuid.UUID(subscription_id),
            delivery_id=uuid.UUID(delivery_id),
            tenant_id=tenant_uuid,
            event=event,
        )
        if claimed is None:
            return False
        subscription, delivery, normalized_event = claimed
        settings = get_settings()
        try:
            validate_webhook_endpoint(str(subscription.endpoint_url), environment=settings.env)
            secret = ConnectorSecretCrypto(settings).decrypt(
                ciphertext=subscription.secret_ciphertext,
                nonce=subscription.secret_nonce,
                kid=subscription.secret_kid,
                aad=tenant_id.encode(),
            )
            body = json.dumps(normalized_event, separators=(",", ":"), sort_keys=True).encode()
            timestamp = str(int(datetime.now(UTC).timestamp()))
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "AverQel-Documents-Webhook/2",
                "X-AverQel-Event": str(normalized_event.get("type") or "document.event"),
                "X-AverQel-Event-Id": str(normalized_event.get("event_id") or ""),
                "X-AverQel-Timestamp": timestamp,
                "X-AverQel-Signature-Version": "2",
                "X-AverQel-Signature": _signature(secret, body, timestamp),
                # Kept for consumers migrating from body-only signatures.
                "X-AverQel-Signature-Legacy": _signature(secret, body),
            }
            response = httpx.post(
                subscription.endpoint_url,
                content=body,
                headers=headers,
                timeout=10.0,
                follow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f"webhook returned HTTP {response.status_code}")
            subscription.failure_count = 0
            subscription.last_error = None
            subscription.disabled_reason = None
            delivery.status = "delivered"
            delivery.response_status = response.status_code
            delivery.error_message = None
            delivery.next_attempt_at = None
            delivery.completed_at = datetime.now(UTC)
            history = list(delivery.attempt_history or [])
            if history:
                history[-1].update(
                    {
                        "status": "delivered",
                        "response_status": response.status_code,
                        "completed_at": delivery.completed_at.isoformat(),
                    }
                )
            delivery.attempt_history = history
            session.commit()
            return True
        except WebhookEndpointError as exc:
            # A blocked/invalid endpoint must not be retried as if it were a
            # transient network error. Disable it and expose the reason to admins.
            subscription.active = False
            subscription.disabled_reason = f"Automatically disabled: {str(exc)[:500]}"
            _record_failure(
                session,
                subscription=subscription,
                delivery=delivery,
                error=exc,
                response_status=None,
                retry_count=self.request.retries,
                max_retries=0,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            response_status = getattr(locals().get("response"), "status_code", None)
            status, delay = _record_failure(
                session,
                subscription=subscription,
                delivery=delivery,
                error=exc,
                response_status=response_status,
                retry_count=self.request.retries,
                max_retries=self.max_retries,
            )
            if status == "retrying":
                try:
                    raise self.retry(
                        kwargs={
                            "subscription_id": subscription_id,
                            "delivery_id": delivery_id,
                            "tenant_id": tenant_id,
                            "event": normalized_event,
                        },
                        exc=exc,
                        countdown=delay,
                    )
                except MaxRetriesExceededError:
                    logger.warning(
                        "Document webhook exhausted retries",
                        extra={"subscription_id": subscription_id, "delivery_id": delivery_id},
                        exc_info=True,
                    )
            return False
    finally:
        session.close()
