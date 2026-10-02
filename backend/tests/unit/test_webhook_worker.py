from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.documents.workers.tasks_webhooks import (
    _delivery_event,
    _record_failure,
    _signature,
)


def test_timestamp_signature_is_deterministic_and_distinct_from_legacy() -> None:
    secret = b"test-secret"
    body = b'{"event_id":"evt-1"}'
    assert _signature(secret, body).startswith("sha256=")
    assert len(_signature(secret, body)) == 71
    assert _signature(secret, body, "1700000000") == _signature(secret, body, "1700000000")
    assert _signature(secret, body, "1700000000") != _signature(secret, body, "1700000001")
    assert _signature(secret, body) != _signature(secret, body, "1700000000")


def test_delivery_event_prefers_durable_payload_and_preserves_event_identity() -> None:
    delivery = SimpleNamespace(
        payload={"type": "document.indexed", "event_id": "evt-42", "data": {"id": "doc-1"}},
        event_type="document.indexed",
        event_id="evt-42",
    )
    result = _delivery_event(delivery, {"type": "wrong", "data": {"old": True}})
    assert result == {"type": "document.indexed", "event_id": "evt-42", "data": {"id": "doc-1"}}


def test_failure_schedules_retry_and_records_diagnostics() -> None:
    subscription = SimpleNamespace(
        failure_count=0, last_error=None, active=True, disabled_reason=None
    )
    delivery = SimpleNamespace(
        response_status=None,
        status="delivering",
        error_message=None,
        completed_at=None,
        next_attempt_at=None,
        attempt_history=[
            {"attempt": 1, "started_at": datetime.now(UTC).isoformat(), "status": "delivering"}
        ],
    )
    session = SimpleNamespace(commit=lambda: None)
    status, delay = _record_failure(
        session,
        subscription=subscription,
        delivery=delivery,
        error=RuntimeError("connection refused"),
        response_status=None,
        retry_count=0,
        max_retries=5,
    )
    assert status == "retrying"
    assert delay == 30
    assert delivery.next_attempt_at is not None
    assert delivery.attempt_history[-1]["status"] == "retrying"


def test_repeated_failures_disable_webhook_with_visible_reason() -> None:
    subscription = SimpleNamespace(
        failure_count=9,
        last_error=None,
        active=True,
        disabled_reason=None,
    )
    delivery = SimpleNamespace(
        response_status=503,
        status="delivering",
        error_message=None,
        completed_at=None,
        next_attempt_at=None,
        attempt_history=[
            {"attempt": 10, "started_at": datetime.now(UTC).isoformat(), "status": "delivering"}
        ],
    )
    _record_failure(
        SimpleNamespace(commit=lambda: None),
        subscription=subscription,
        delivery=delivery,
        error=RuntimeError("service unavailable"),
        response_status=503,
        retry_count=2,
        max_retries=5,
    )
    assert subscription.active is False
    assert "10 consecutive" in subscription.disabled_reason
    assert delivery.status == "failed"
