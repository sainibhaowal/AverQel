from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.integration import Integration
from app.models.system.audit_log import AuditLog
from app.integrations.services.connector_orchestrator import ConnectorOrchestrator


def _auth_headers(seeded) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"admin"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def _seed_connector(db_session, tenant_id, user_id, slug: str) -> Connector:
    db_session.add(Tenant(id=tenant_id, name=f"Tenant {uuid4().hex[:8]}"))
    db_session.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=f"{uuid4().hex[:8]}@example.com",
            collection_code=f"C{uuid4().hex[:12]}",
            password_hash="hash",
            is_active=True,
            failed_login_attempts=0,
            access_token_version=0,
            totp_enabled=False,
            totp_backup_codes=None,
        )
    )
    db_session.flush()
    integration = (
        db_session.execute(select(Integration).where(Integration.slug == slug))
        .scalars()
        .first()
    )
    if integration is None:
        integration = Integration(
            id=uuid4(),
            name=f"{slug} integration {uuid4().hex[:8]}",
            slug=slug,
            description=f"Integration for {slug}",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        integration_id=integration.id,
        name=f"{slug} connector {uuid4().hex[:8]}",
        config={},
        sync_frequency="daily",
    )
    db_session.add(connector)
    db_session.commit()
    return connector


def test_trigger_sync_route_hands_off_to_background_orchestrator(
    client,
    db_session,
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connector = _seed_connector(
        db_session,
        tenant_id,
        user_id,
        "github",
    )
    headers = _auth_headers(
        type("_Seeded", (), {"tenant_id": tenant_id, "user_id": user_id})()
    )
    calls: list[dict[str, str]] = []

    def fake_sync(
        self, connector_id, tenant_id, progress_callback=None, attempt=1
    ):  # noqa: ARG001
        calls.append(
            {
                "connector_id": str(connector_id),
                "tenant_id": str(tenant_id),
                "attempt": str(attempt),
            }
        )
        return {
            "status": "accepted",
            "message": "background sync complete",
        }

    monkeypatch.setattr(ConnectorOrchestrator, "sync_connector", fake_sync)

    response = client.post(
        f"/api/v1/integrations/connectors/{connector.id}/sync", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["message"] == "Sync job queued in background"
    assert calls == [
        {
            "connector_id": str(connector.id),
            "tenant_id": str(tenant_id),
            "attempt": "1",
        }
    ]


def test_connector_summary_endpoint_exposes_live_health_and_sync_state(
    client,
    db_session,
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connector = _seed_connector(db_session, tenant_id, user_id, "github")
    headers = _auth_headers(
        type("_Seeded", (), {"tenant_id": tenant_id, "user_id": user_id})()
    )
    retry_after_at = datetime.now(UTC) + timedelta(seconds=45)

    health = {
        "healthy": False,
        "status": "degraded",
        "error_code": "connectivity_failure",
        "error_message": "temporary outage",
        "http_status": None,
        "metadata": {"provider": "github"},
        "checked_at": "2030-01-01T00:00:00Z",
        "last_good_at": None,
        "circuit_open_until": retry_after_at.isoformat().replace("+00:00", "Z"),
        "consecutive_failures": 2,
    }
    checkpoint = {
        "run_id": "run-1",
        "connector_id": str(connector.id),
        "connector_name": connector.name,
        "integration_slug": "github",
        "phase": "sync_error",
        "status": "failed",
        "attempt": 2,
        "updated_at": "2030-01-01T00:00:00Z",
        "error_code": "connectivity_failure",
        "error_message": "temporary outage",
        "retryable": True,
        "retry_after_at": health["circuit_open_until"],
        "retry_after_seconds": 45,
        "error_domain": "upstream",
        "duration_ms": 1234,
    }
    connector.config = {
        Connector.HEALTH_CONFIG_KEY: health,
        Connector.SYNC_CHECKPOINT_CONFIG_KEY: checkpoint,
    }
    db_session.commit()
    db_session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="connector_sync",
            resource_type="connector",
            resource_id=str(connector.id),
            status="error",
            trace_id=uuid4().hex,
            details={
                "phase": "sync_error",
                "error_domain": "upstream",
                "retry_after_seconds": 45,
            },
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/integrations/connectors/{connector.id}/summary", headers=headers
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["connector"]["id"] == str(connector.id)
    assert payload["live_status"] == "degraded"
    assert payload["retryable"] is True
    assert payload["retry_after_seconds"] == 45
    assert payload["error_domain"] == "upstream"
    assert payload["retry_state"] == "waiting"
    assert payload["health_age_seconds"] is not None
    assert payload["sync_checkpoint_age_seconds"] is not None
    assert payload["health"]["status"] == "degraded"
    assert payload["sync_checkpoint"]["phase"] == "sync_error"
    assert payload["last_sync_audit"]["action"] == "connector_sync"
    assert payload["recent_audit_count"] >= 1


def test_connector_fleet_summary_endpoint_aggregates_connector_health(
    client,
    db_session,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    headers = _auth_headers(
        type("_Seeded", (), {"tenant_id": tenant_id, "user_id": user_id})()
    )
    db_session.add(Tenant(id=tenant_id, name=f"Tenant {uuid4().hex[:8]}"))
    db_session.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=f"{uuid4().hex[:8]}@example.com",
            collection_code=f"C{uuid4().hex[:12]}",
            password_hash="hash",
            is_active=True,
            failed_login_attempts=0,
            access_token_version=0,
            totp_enabled=False,
            totp_backup_codes=None,
        )
    )
    db_session.flush()

    github_slug = f"github-summary-{uuid4().hex[:8]}"
    gmail_slug = f"gmail-summary-{uuid4().hex[:8]}"
    slack_slug = f"slack-summary-{uuid4().hex[:8]}"

    github = Integration(
        id=uuid4(),
        name="GitHub integration",
        slug=github_slug,
        description="GitHub integration",
        ui_metadata={},
    )
    gmail = Integration(
        id=uuid4(),
        name="Gmail integration",
        slug=gmail_slug,
        description="Gmail integration",
        ui_metadata={},
    )
    slack = Integration(
        id=uuid4(),
        name="Slack integration",
        slug=slack_slug,
        description="Slack integration",
        ui_metadata={},
    )
    db_session.add_all([github, gmail, slack])
    db_session.flush()

    active = Connector(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        integration_id=github.id,
        name="github connector",
        config={
            Connector.HEALTH_CONFIG_KEY: {
                "status": "healthy",
                "healthy": True,
                "last_checked_at": "2030-01-01T00:00:00Z",
            }
        },
        sync_frequency="daily",
        status=ConnectorStatus.ACTIVE,
    )
    paused = Connector(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        integration_id=gmail.id,
        name="gmail connector",
        config={
            Connector.HEALTH_CONFIG_KEY: {
                "status": "stale",
                "healthy": False,
                "last_checked_at": "2030-01-01T00:00:00Z",
            },
            Connector.SYNC_CHECKPOINT_CONFIG_KEY: {
                "retryable": True,
                "retry_after_at": "2030-01-01T00:00:45Z",
                "error_domain": "upstream",
            },
        },
        sync_frequency="daily",
        status=ConnectorStatus.PAUSED,
    )
    syncing = Connector(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        integration_id=slack.id,
        name="slack connector",
        config={
            Connector.HEALTH_CONFIG_KEY: {
                "status": "degraded",
                "healthy": False,
                "last_checked_at": "2030-01-01T00:00:00Z",
            },
            Connector.SYNC_CHECKPOINT_CONFIG_KEY: {
                "retryable": True,
                "retry_after_at": "2030-01-01T00:00:30Z",
                "error_domain": "upstream",
            },
        },
        sync_frequency="daily",
        status=ConnectorStatus.SYNCING,
    )
    db_session.add_all([active, paused, syncing])

    db_session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="connector_sync",
            resource_type="connector",
            resource_id=str(paused.id),
            status="error",
            trace_id=uuid4().hex,
            details={
                "phase": "sync_error",
                "retryable": True,
                "error_domain": "upstream",
            },
        )
    )
    db_session.commit()

    response = client.get("/api/v1/integrations/connectors/summary", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["total_connectors"] == 3
    assert payload["active_count"] == 1
    assert payload["syncing_count"] == 1
    assert payload["paused_count"] == 1
    assert payload["error_count"] == 0
    assert payload["healthy_count"] == 1
    assert payload["stale_count"] == 1
    assert payload["retryable_count"] == 2
    assert payload["due_sync_count"] == 0
    assert payload["recent_audit_count"] >= 1
    assert payload["status_breakdown"]["active"] == 1
    assert payload["integration_breakdown"][github_slug] == 1
    assert payload["integration_breakdown"][gmail_slug] == 1
    assert payload["integration_breakdown"][slack_slug] == 1
    assert payload["error_domain_breakdown"]["upstream"] == 2
    assert payload["health_status_breakdown"]["healthy"] == 1
    assert payload["health_status_breakdown"]["stale"] == 1
    assert payload["health_status_breakdown"]["degraded"] == 1
    assert payload["retry_state_breakdown"]["none"] == 1
    assert payload["retry_state_breakdown"]["waiting"] == 2
    assert len(payload["attention_connectors"]) >= 1
    attention_by_name = {item["name"]: item for item in payload["attention_connectors"]}
    assert attention_by_name["gmail connector"]["retry_state"] == "waiting"
    assert attention_by_name["gmail connector"]["health_age_seconds"] is not None


def test_connector_sync_history_endpoint_returns_recent_audits_and_is_tenant_scoped(
    client,
    db_session,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connector = _seed_connector(db_session, tenant_id, user_id, "github")
    headers = _auth_headers(
        type("_Seeded", (), {"tenant_id": tenant_id, "user_id": user_id})()
    )

    db_session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="connector_sync",
            resource_type="connector",
            resource_id=str(connector.id),
            status="started",
            trace_id=uuid4().hex,
            details={
                "phase": "start",
                "attempt": 1,
                "duration_ms": 12,
                "retryable": False,
                "error_domain": "unknown",
            },
        )
    )
    db_session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="connector_sync",
            resource_type="connector",
            resource_id=str(connector.id),
            status="error",
            trace_id=uuid4().hex,
            details={
                "phase": "sync_error",
                "attempt": 2,
                "duration_ms": 88,
                "error_code": "connectivity_failure",
                "retryable": True,
                "retry_after_at": "2030-01-01T00:00:45Z",
                "retry_after_seconds": 45,
                "error_domain": "upstream",
            },
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/integrations/connectors/{connector.id}/sync-history",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    payload_by_phase = {item["phase"]: item for item in payload}
    assert payload_by_phase["sync_error"]["status"] == "error"
    assert payload_by_phase["sync_error"]["error_domain"] == "upstream"
    assert payload_by_phase["sync_error"]["retry_after_seconds"] == 45
    assert payload_by_phase["start"]["status"] == "started"
    assert payload_by_phase["start"]["attempt"] == 1
