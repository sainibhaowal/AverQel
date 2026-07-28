from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.deepspace.models.agent_activity import AgentActivity
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.integration import Integration
from app.integrations.services.connector_orchestrator import ConnectorOrchestrator
from app.integrations.services.health_utils import build_health_report, future_iso
from app.platform.database.session import get_session_factory
from app.system.models.audit_log import AuditLog

pytestmark = pytest.mark.db_commit


def _seed_connector(
    db_session,
    seed_user,
    *,
    slug: str = "github",
    name: str = "GitHub",
    status: ConnectorStatus = ConnectorStatus.ACTIVE,
    config: dict[str, Any] | None = None,
) -> Connector:
    seeded = seed_user(
        "Connector Health Tenant", "health@example.com", "Secret123!", ("admin",)
    )
    integration_name = f"{name} {uuid4().hex[:8]}"
    integration = Integration(
        name=integration_name,
        slug=slug,
        description=f"{integration_name} integration",
        ui_metadata={},
    )
    db_session.add(integration)
    db_session.flush()

    connector = Connector(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        integration_id=integration.id,
        name=f"{name} Connector",
        status=status,
        config=config or {},
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    return connector


def test_validate_connector_health_persists_structured_health_contract(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-health-offline-{uuid4().hex[:8]}"
    connector = _seed_connector(db_session, seed_user, slug=slug, name="GitHub Offline")

    class _OfflineService:
        def __init__(self, *_args, **_kwargs):
            self.sync_called = False

        def sync(self) -> dict[str, Any]:
            self.sync_called = True
            raise AssertionError("sync should not run during validation")

        def validate_config(self) -> bool:
            return True

        def validate_health(self) -> dict[str, Any]:
            return build_health_report(
                status="offline",
                healthy=False,
                message="GitHub API unreachable",
                error_code="connectivity_failure",
                metadata={"provider": "github"},
            )

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _OfflineService)

    result = ConnectorOrchestrator(db_session).validate_connector_health(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    assert result["status"] == "offline"
    assert result["healthy"] is False
    assert result["health"]["status"] == "offline"
    assert result["health"]["last_error_message"] == "GitHub API unreachable"
    assert connector.status == ConnectorStatus.PAUSED
    assert connector.health_status == "offline"
    assert connector.consecutive_failures == 1
    assert connector.circuit_open_until is not None
    assert connector.last_error == "GitHub API unreachable"


def test_sync_connector_short_circuits_when_circuit_is_open(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-health-circuit-{uuid4().hex[:8]}"
    health = build_health_report(
        status="offline",
        healthy=False,
        message="Circuit already open",
        error_code="circuit_open",
        circuit_open_until=future_iso(600),
        consecutive_failures=3,
        metadata={"reason": "previous failure"},
    )
    connector = _seed_connector(
        db_session,
        seed_user,
        slug=slug,
        name="GitHub Circuit",
        config={Connector.HEALTH_CONFIG_KEY: health},
        status=ConnectorStatus.PAUSED,
    )

    calls = {"validate": 0, "sync": 0}

    class _BlockedService:
        def __init__(self, *_args, **_kwargs):
            pass

        def sync(self) -> dict[str, Any]:
            calls["sync"] += 1
            raise AssertionError("sync should not run while the circuit is open")

        def validate_config(self) -> bool:
            calls["validate"] += 1
            return True

        def validate_health(self) -> dict[str, Any]:
            calls["validate"] += 1
            raise AssertionError(
                "validate_health should not run while the circuit is open"
            )

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _BlockedService)

    result = ConnectorOrchestrator(db_session).sync_connector(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    assert result["status"] == "offline"
    assert result["health"]["status"] == "offline"
    assert result["health"]["error_code"] == "circuit_open"
    assert calls == {"validate": 0, "sync": 0}
    assert connector.status == ConnectorStatus.PAUSED
    assert connector.health_status == "offline"
    assert connector.error_count == 3


def test_sync_connector_records_checkpoint_and_retries_transient_fetch(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-checkpoint-retry-{uuid4().hex[:8]}"
    connector = _seed_connector(
        db_session,
        seed_user,
        slug=slug,
        name="Retry Connector",
    )
    calls = {"sync": 0}

    class _RetryService:
        def __init__(self, *_args, **_kwargs):
            pass

        def validate_config(self) -> bool:
            return True

        def validate_health(self) -> dict[str, Any]:
            return build_health_report(
                status="healthy",
                healthy=True,
                message="ok",
                metadata={"provider": "retry"},
            )

        def sync(self) -> dict[str, Any]:
            calls["sync"] += 1
            if calls["sync"] == 1:
                raise ConnectionError("temporary upstream outage")
            return {"status": "skipped", "message": "no changes"}

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _RetryService)

    result = ConnectorOrchestrator(db_session).sync_connector(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    checkpoint = connector.config[Connector.SYNC_CHECKPOINT_CONFIG_KEY]
    assert result["status"] == "skipped"
    assert result["sync"]["run_id"]
    assert result["sync"]["phase"] == "skipped"
    assert result["sync"]["attempt"] == 2
    assert result["sync"]["duration_ms"] is not None
    assert result["sync"]["started_at"]
    assert result["sync"]["completed_at"]
    assert calls["sync"] == 2
    assert checkpoint["attempt"] == 2
    assert checkpoint["status"] == "completed"
    assert checkpoint["phase"] == "skipped"
    assert checkpoint["run_id"]
    assert checkpoint["duration_ms"] is not None
    assert checkpoint["started_at"]

    db_session.expire_all()
    audit_events = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_type == "connector")
        .filter(AuditLog.resource_id == str(connector.id))
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    assert audit_events
    assert any(event.details.get("phase") == "start" for event in audit_events)
    assert any(event.details.get("phase") == "skipped" for event in audit_events)
    assert any(event.status == "started" for event in audit_events)


def test_sync_connector_uses_runtime_decrypted_secrets_without_persisting_them(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-secret-runtime-{uuid4().hex[:8]}"
    connector = _seed_connector(
        db_session,
        seed_user,
        slug=slug,
        name="Secret Runtime Connector",
    )
    db_session.add(
        ConnectorSecret(
            connector_id=connector.id,
            tenant_id=connector.tenant_id,
            secret_ciphertext=b"ciphertext",
            secret_nonce=b"nonce",
            secret_kid="kid-1",
            secret_type="access_token",
        )
    )
    db_session.commit()

    class _SecretAwareService:
        def __init__(self, connector, *_args, **_kwargs):  # noqa: ANN001
            self.connector = connector

        def validate_config(self) -> bool:
            return True

        def validate_health(self) -> dict[str, Any]:
            assert self.connector.config["access_token"] == "decrypted-token"
            return build_health_report(status="healthy", healthy=True, message="ok")

        def sync(self) -> dict[str, Any]:
            assert self.connector.config["access_token"] == "decrypted-token"
            return {"status": "skipped", "message": "no changes"}

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _SecretAwareService)
    monkeypatch.setattr(
        "app.integrations.services.connector_secret_crypto.ConnectorSecretCrypto.decrypt",
        lambda self, **kwargs: b"decrypted-token",  # noqa: ARG005
    )

    result = ConnectorOrchestrator(db_session).sync_connector(
        connector.id,
        connector.tenant_id,
    )
    with get_session_factory()() as verify_session:
        verify_session.execute(text("SET ROLE aks_app"))
        from app.platform.database.session import set_db_tenant_context

        set_db_tenant_context(verify_session, connector.tenant_id)
        persisted = verify_session.get(Connector, connector.id)

    assert result["status"] == "skipped"
    assert persisted is not None
    assert "access_token" not in (persisted.config or {})
    assert persisted.status == ConnectorStatus.ACTIVE


def test_sync_connector_records_failed_checkpoint_with_error_taxonomy(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-checkpoint-failure-{uuid4().hex[:8]}"
    connector = _seed_connector(
        db_session,
        seed_user,
        slug=slug,
        name="Failure Connector",
    )

    class _FailureService:
        def __init__(self, *_args, **_kwargs):
            pass

        def validate_config(self) -> bool:
            return True

        def validate_health(self) -> dict[str, Any]:
            return build_health_report(status="healthy", healthy=True, message="ok")

        def sync(self) -> dict[str, Any]:
            raise PermissionError("credentials rejected")

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _FailureService)

    result = ConnectorOrchestrator(db_session).sync_connector(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    checkpoint = connector.config[Connector.SYNC_CHECKPOINT_CONFIG_KEY]
    assert result["status"] == "error"
    assert result["sync"]["run_id"]
    assert result["sync"]["phase"] == "sync_error"
    assert result["sync"]["error_code"]
    assert result["sync"]["duration_ms"] is not None
    assert checkpoint["status"] == "failed"
    assert checkpoint["phase"] == "sync_error"
    assert checkpoint["error_code"]
    assert checkpoint["retryable"] is False
    assert checkpoint["duration_ms"] is not None

    activity = (
        db_session.query(AgentActivity)
        .filter(AgentActivity.tenant_id == connector.tenant_id)
        .order_by(AgentActivity.created_at.desc())
        .first()
    )
    assert activity is not None
    assert activity.activity_type == "error"
    assert activity.metadata_json["error_code"]
    assert activity.metadata_json["retryable"] is False
    assert activity.metadata_json["run_id"] == result["sync"]["run_id"]

    db_session.expire_all()
    audit_events = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_type == "connector")
        .filter(AuditLog.resource_id == str(connector.id))
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    assert audit_events
    assert any(event.action == "connector_sync" for event in audit_events)
    assert any(event.status == "error" for event in audit_events)


def test_sync_connector_records_retryable_failure_with_retry_after_timestamp(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-checkpoint-retryable-{uuid4().hex[:8]}"
    connector = _seed_connector(
        db_session,
        seed_user,
        slug=slug,
        name="Retryable Failure Connector",
    )

    class _RetryableFailureService:
        def __init__(self, *_args, **_kwargs):
            pass

        def validate_config(self) -> bool:
            return True

        def validate_health(self) -> dict[str, Any]:
            return build_health_report(status="healthy", healthy=True, message="ok")

        def sync(self) -> dict[str, Any]:
            raise ConnectionError("temporary upstream outage")

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _RetryableFailureService)

    result = ConnectorOrchestrator(db_session).sync_connector(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    checkpoint = connector.config[Connector.SYNC_CHECKPOINT_CONFIG_KEY]
    assert result["status"] == "error"
    assert result["sync"]["retryable"] is True
    assert result["sync"]["retry_after_at"]
    assert checkpoint["status"] == "failed"
    assert checkpoint["retryable"] is True
    assert checkpoint["retry_after_at"]

    db_session.expire_all()
    audit_events = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_type == "connector")
        .filter(AuditLog.resource_id == str(connector.id))
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    assert audit_events
    assert any(event.details.get("phase") == "sync_error" for event in audit_events)
    assert any(event.status == "error" for event in audit_events)
    retry_audit = next(
        event for event in audit_events if event.details.get("phase") == "sync_error"
    )
    assert retry_audit.details.get("error_domain") == "upstream"
    assert retry_audit.details.get("retry_after_seconds") is not None
    assert result["sync"]["error_domain"] == "upstream"
    assert result["sync"]["retry_after_seconds"] is not None


def test_validate_connector_health_uses_cached_snapshot_when_provider_is_down(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-health-stale-{uuid4().hex[:8]}"
    snapshot = {
        "integration_slug": slug,
        "document_id": str(uuid4()),
        "filename": "cached.md",
        "title": "Cached Snapshot",
        "summary": "last known good state",
        "hash": "abc123",
        "synced_at": "2026-05-13T00:00:00Z",
    }
    connector = _seed_connector(
        db_session,
        seed_user,
        slug=slug,
        name="Cached Connector",
        config={Connector.LAST_SUCCESS_SNAPSHOT_KEY: snapshot},
    )

    class _DownService:
        def __init__(self, *_args, **_kwargs):
            pass

        def sync(self) -> dict[str, Any]:
            raise AssertionError("sync should not run during validation")

        def validate_config(self) -> bool:
            return True

        def validate_health(self) -> dict[str, Any]:
            return build_health_report(
                status="offline",
                healthy=False,
                message="Upstream unavailable",
                error_code="connectivity_failure",
                metadata={"provider": "cached"},
            )

    monkeypatch.setitem(ConnectorOrchestrator._REGISTRY, slug, _DownService)

    result = ConnectorOrchestrator(db_session).validate_connector_health(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    assert result["status"] == "stale"
    assert result["health"]["status"] == "stale"
    assert result["health"]["metadata"]["has_fallback_snapshot"] is True
    assert result["fallback_snapshot"] == snapshot
    assert connector.health_status == "stale"
    assert connector.last_success_snapshot == snapshot


def test_sync_connector_records_checkpoint_when_service_is_missing(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    slug = f"connector-missing-service-{uuid4().hex[:8]}"
    connector = _seed_connector(
        db_session, seed_user, slug=slug, name="Missing Service"
    )
    monkeypatch.delitem(ConnectorOrchestrator._REGISTRY, slug, raising=False)

    result = ConnectorOrchestrator(db_session).sync_connector(
        connector.id,
        connector.tenant_id,
    )
    db_session.refresh(connector)

    checkpoint = connector.config[Connector.SYNC_CHECKPOINT_CONFIG_KEY]
    expected_message = f"No service implementation for integration: {slug}"

    assert result["status"] == "error"
    assert result["sync"]["phase"] == "start"
    assert result["message"] == expected_message
    assert connector.status == ConnectorStatus.ERROR
    assert connector.last_error == expected_message
    assert checkpoint["status"] == "failed"
    assert checkpoint["phase"] == "start"
    assert checkpoint["error_code"] == "integration_service_missing"
    assert checkpoint["error_message"] == expected_message
