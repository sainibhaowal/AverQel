from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_admin_audit_logs_endpoint_returns_platform_wide_items_and_tenant_filter(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.platform.database.session import get_session_factory, set_db_tenant_context
    from app.system.models.audit_log import AuditLog
    from app.system.services.audit_service import AuditService

    seeded = seed_user("tenant-audit", "admin-audit@tenant.example", "StrongPass!1234", ("admin",))
    other = seed_user(
        "tenant-audit-other", "member-audit@tenant.example", "StrongPass!1234", ("user",)
    )
    get_settings().bootstrap_super_admin_emails = [seeded.email]
    _login(client, other)
    token = _login(client, seeded)

    session = get_session_factory()()
    try:
        platform_event = AuditService(session).write_event(
            tenant_id=None,
            action="auth.login.failed",
            resource_type="auth",
            actor_user_id=None,
            status="failure",
            details={"auth_method": "password", "failure_reason": "invalid_credentials"},
        )
        old_platform_event = AuditService(session).write_event(
            tenant_id=None,
            action="auth.login.failed",
            resource_type="auth",
            actor_user_id=None,
            status="failure",
            details={"auth_method": "oauth", "failure_reason": "oauth_state_invalid"},
        )
        old_platform_event.created_at = datetime.now(UTC) - timedelta(days=91)
        session.commit()
        platform_event_id = platform_event.id
        old_platform_event_id = old_platform_event.id
    finally:
        session.rollback()
        session.close()

    response = client.get(
        "/api/v1/admin/audit-logs?limit=20",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "page" in payload
    assert isinstance(payload["items"], list)
    assert any(
        item["action"] == "auth.login" and item["tenant_id"] == str(other.tenant_id)
        for item in payload["items"]
    )
    assert any(
        item["id"] == str(platform_event_id) and item["tenant_id"] is None
        for item in payload["items"]
    )

    filtered_response = client.get(
        f"/api/v1/admin/audit-logs?limit=20&tenant_id={seeded.tenant_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert filtered_response.status_code == 200
    assert all(
        item["tenant_id"] == str(seeded.tenant_id) for item in filtered_response.json()["items"]
    )

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, "bypass")
        assert AuditService(session).purge_platform_events(retention_days=90) >= 1
        assert (
            session.execute(
                select(AuditLog.id).where(AuditLog.id == old_platform_event_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            session.execute(
                select(AuditLog.id).where(AuditLog.id == platform_event_id)
            ).scalar_one_or_none()
            == platform_event_id
        )
    finally:
        session.rollback()
        session.close()
