from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models.auth_session import AuthSession
from app.auth.models.user import User
from app.core.config import Settings
from app.platform.database.session import get_session_factory, set_db_tenant_context
from tests.conftest import SeededUser


def _headers(token: str, tenant_id: object) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(tenant_id),
    }


def test_platform_admin_mfa_enrollment_and_security_history_are_account_scoped(
    client: TestClient,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    admin = seed_user(
        "tenant-mfa-admin",
        "platform-owner@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    settings.bootstrap_super_admin_emails = [admin.email]
    settings.platform_admin_mfa_required = True

    login = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(admin.tenant_id)},
        json={"email": admin.email, "password": admin.password},
    )
    assert login.status_code == 200
    password_only_token = login.json()["access_token"]
    headers = _headers(password_only_token, admin.tenant_id)

    blocked = client.get("/api/v1/admin/users", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ADMIN_MFA_SETUP_REQUIRED"

    setup = client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    confirmed = client.post(
        "/api/v1/auth/2fa/confirm",
        headers=headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmed.status_code == 200
    assert len(confirmed.json()["backup_codes"]) == 8
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 200

    cannot_disable = client.post(
        "/api/v1/auth/2fa/disable",
        headers=headers,
        json={"password": admin.password},
    )
    assert cannot_disable.status_code == 403
    assert cannot_disable.json()["error"]["code"] == "ADMIN_MFA_REQUIRED"

    mfa_challenge = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(admin.tenant_id)},
        json={"email": admin.email, "password": admin.password},
    )
    assert mfa_challenge.status_code == 200
    assert mfa_challenge.json()["requires_2fa"] is True
    pending_token = mfa_challenge.json()["pending_token"]

    verified_login = client.post(
        "/api/v1/auth/2fa/verify",
        headers={"X-Tenant-Id": str(admin.tenant_id)},
        json={"pending_token": pending_token, "code": pyotp.TOTP(secret).now()},
    )
    assert verified_login.status_code == 200
    verified_token = verified_login.json()["access_token"]
    verified_headers = _headers(verified_token, admin.tenant_id)
    assert client.get("/api/v1/admin/users", headers=verified_headers).status_code == 200

    purge_request = client.post(
        "/api/v1/admin/data-deletions",
        headers=verified_headers,
        json={
            "reason": "security_incident",
            "target_tenant_id": str(admin.tenant_id),
            "target_confirmation": f"DELETE {admin.tenant_id}",
        },
    )
    assert purge_request.status_code == 200
    purge_payload = purge_request.json()
    assert purge_payload["status"] == "awaiting_approval"
    assert purge_payload["self_approval_not_before"]
    cancellation = client.post(
        f"/api/v1/admin/data-deletions/{purge_payload['deletion_id']}/cancel",
        params={"target_tenant_id": str(admin.tenant_id)},
        headers=verified_headers,
    )
    assert cancellation.status_code == 200
    assert cancellation.json()["status"] == "cancelled"

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, admin.tenant_id)
        auth_session = session.execute(
            select(AuthSession)
            .where(AuthSession.user_id == admin.user_id)
            .order_by(AuthSession.created_at.desc())
            .limit(1)
        ).scalar_one()
        assert auth_session.mfa_verified_at is not None
        admin_session_id = auth_session.id
        user = session.execute(select(User).where(User.id == admin.user_id)).scalar_one()
        assert user.last_login_at is not None
    finally:
        session.close()

    register = client.post(
        "/api/v1/auth/register",
        json={"email": "history-target@example.org", "password": "StrongPass!1234"},
    )
    assert register.status_code == 200
    target_user_id = register.json()["user_id"]

    target_login = client.post(
        "/api/v1/auth/login",
        json={"email": "history-target@example.org", "password": "StrongPass!1234"},
    )
    assert target_login.status_code == 200
    target_headers = {"Authorization": f"Bearer {target_login.json()['access_token']}"}
    password_change = client.post(
        "/api/v1/auth/change-password",
        headers=target_headers,
        json={
            "current_password": "StrongPass!1234",
            "new_password": "AnotherStrongPass!5678",
        },
    )
    assert password_change.status_code == 200

    first_new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "history-target@example.org", "password": "AnotherStrongPass!5678"},
    )
    second_new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "history-target@example.org", "password": "AnotherStrongPass!5678"},
    )
    assert first_new_login.status_code == 200
    assert second_new_login.status_code == 200
    target_headers = {"Authorization": f"Bearer {second_new_login.json()['access_token']}"}
    sessions = client.get("/api/v1/auth/sessions", headers=target_headers)
    assert sessions.status_code == 200
    session_to_revoke = next(item for item in sessions.json() if not item["current"])
    revocation = client.delete(
        f"/api/v1/auth/sessions/{session_to_revoke['id']}",
        headers=target_headers,
    )
    assert revocation.status_code == 200

    settings.auth_max_failed_attempts = 2
    failed_login = client.post(
        "/api/v1/auth/login",
        json={"email": "history-target@example.org", "password": "incorrect-password"},
    )
    assert failed_login.status_code == 401
    second_failed_login = client.post(
        "/api/v1/auth/login",
        json={"email": "history-target@example.org", "password": "incorrect-password"},
    )
    assert second_failed_login.status_code == 401

    history = client.get(
        "/api/v1/admin/audit-logs",
        params={
            "limit": 100,
            "security_only": "true",
            "account_user_id": target_user_id,
        },
        headers=verified_headers,
    )
    assert history.status_code == 200
    items = history.json()["items"]
    assert {item["action"] for item in items} >= {
        "auth.register",
        "auth.login",
        "auth.password_change",
        "auth.session_revoked",
        "auth.login.failed",
        "auth.login.lockout",
    }
    registration = next(item for item in items if item["action"] == "auth.register")
    successful_login = next(item for item in items if item["action"] == "auth.login")
    failure = next(item for item in items if item["action"] == "auth.login.failed")
    assert registration["details"]["registration_method"] == "password"
    assert successful_login["status"] == "success"
    assert successful_login["details"]["auth_method"] == "password"
    assert str(successful_login["details"]["mfa_verified"]).lower() == "false"
    assert failure["details"]["auth_method"] == "password"
    assert "email" not in registration["details"]
    assert "password" not in failure["details"]
    lockout = next(item for item in items if item["action"] == "auth.login.lockout")
    assert lockout["status"] == "locked"
    assert lockout["details"]["failure_reason"] == "maximum_failed_attempts"

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, admin.tenant_id)
        admin_session = session.execute(
            select(AuthSession).where(AuthSession.id == admin_session_id)
        ).scalar_one()
        assert admin_session.mfa_verified_at is not None
        admin_session.mfa_verified_at = datetime.now(UTC) - timedelta(minutes=11)
        session.commit()
    finally:
        session.close()

    stale_mfa_delete = client.request(
        "DELETE",
        f"/api/v1/admin/users/{target_user_id}",
        headers=verified_headers,
        json={"confirmation": "DELETE history-target@example.org"},
    )
    assert stale_mfa_delete.status_code == 403
    assert stale_mfa_delete.json()["error"]["code"] == "RECENT_MFA_AUTH_REQUIRED"

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, admin.tenant_id)
        admin_session = session.execute(
            select(AuthSession).where(AuthSession.id == admin_session_id)
        ).scalar_one()
        admin_session.mfa_verified_at = datetime.now(UTC)
        session.commit()
    finally:
        session.close()

    delete_response = client.request(
        "DELETE",
        f"/api/v1/admin/users/{target_user_id}",
        headers=verified_headers,
        json={"confirmation": "DELETE wrong@example.org"},
    )
    assert delete_response.status_code == 400
    delete_response = client.request(
        "DELETE",
        f"/api/v1/admin/users/{target_user_id}",
        headers=verified_headers,
        json={"confirmation": "DELETE history-target@example.org"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, "bypass")
        assert (
            session.execute(select(User).where(User.id == target_user_id)).scalar_one_or_none()
            is None
        )
    finally:
        session.close()

    deleted_history = client.get(
        "/api/v1/admin/audit-logs",
        params={
            "limit": 100,
            "security_only": "true",
            "account_user_id": target_user_id,
        },
        headers=verified_headers,
    )
    assert deleted_history.status_code == 200
    erased = [
        item
        for item in deleted_history.json()["items"]
        if item["action"] == "admin.user.account_erased"
    ]
    assert len(erased) == 1
    assert erased[0]["details"]["target_user_id"] == target_user_id
    assert str(erased[0]["details"]["target_tenant_removed"]).lower() == "true"
    assert len(deleted_history.json()["items"]) == 1
