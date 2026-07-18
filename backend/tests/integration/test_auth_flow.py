from __future__ import annotations

from collections.abc import Callable

import pyotp
from fastapi.testclient import TestClient

from app.core.auth import AuthContext
from app.core.config import Settings
from app.services.auth.auth_service import AuthService
from tests.conftest import SeededUser


def test_auth_login_refresh_logout_flow(
    client: TestClient,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded: SeededUser = seed_user(
        "tenant-auth-flow",
        "admin@tenant-a.example",
        "StrongPass!1234",
        ("admin",),
    )
    settings.bootstrap_super_admin_emails = [seeded.email]

    login_response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["token_type"] == "bearer"
    assert login_payload["expires_in"] == settings.jwt_access_ttl_minutes * 60
    assert login_payload["user"]["roles"] == ["admin"]
    first_access_token = login_payload["access_token"]
    first_refresh_token = login_response.cookies.get(settings.refresh_cookie_name)
    assert first_refresh_token

    client.cookies.set(settings.refresh_cookie_name, first_refresh_token)
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.json()
    second_access_token = refresh_payload["access_token"]
    second_refresh_token = refresh_response.cookies.get(settings.refresh_cookie_name)
    assert second_access_token != first_access_token
    assert second_refresh_token
    assert second_refresh_token != first_refresh_token

    client.cookies.set(settings.refresh_cookie_name, first_refresh_token)
    replay_response = client.post("/api/v1/auth/refresh")
    assert replay_response.status_code == 401
    assert replay_response.json()["error"]["code"] in {
        "REFRESH_TOKEN_REVOKED",
        "REFRESH_TOKEN_REUSED",
    }

    client.cookies.set(settings.refresh_cookie_name, second_refresh_token)
    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {second_access_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert logout_response.status_code == 200
    assert logout_response.json() == {"success": True}

    client.cookies.set(settings.refresh_cookie_name, second_refresh_token)
    revoked_refresh_response = client.post("/api/v1/auth/refresh")
    assert revoked_refresh_response.status_code == 401
    assert revoked_refresh_response.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


def test_logout_revokes_access_token_even_if_redis_is_unavailable(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-auth-logout",
        "logout@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )

    login_response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert logout_response.status_code == 200

    def _boom():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.services.system.cache_service.get_redis_client", _boom)

    profile_response = client.get(
        "/api/v1/auth/profile",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert profile_response.status_code == 401
    assert profile_response.json()["error"]["code"] == "TOKEN_REVOKED"


def test_logout_all_invalidates_other_active_access_tokens(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-logout-all",
        "logout-all@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )

    first_login = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert first_login.status_code == 200
    first_access_token = first_login.json()["access_token"]

    second_login = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert second_login.status_code == 200
    second_access_token = second_login.json()["access_token"]

    logout_all_response = client.post(
        "/api/v1/auth/logout-all",
        headers={
            "Authorization": f"Bearer {first_access_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert logout_all_response.status_code == 200

    revoked_profile_response = client.get(
        "/api/v1/auth/profile",
        headers={
            "Authorization": f"Bearer {second_access_token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert revoked_profile_response.status_code == 401
    assert revoked_profile_response.json()["error"]["code"] == "TOKEN_REVOKED"


def test_register_rejects_weak_password(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "   "},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_PASSWORD"


def test_register_defaults_to_user_role(
    client: TestClient,
    settings: Settings,
) -> None:
    settings.bootstrap_super_admin_emails = ["rav.singh@averqel.com"]

    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "normal.user@example.com", "password": "StrongPass!1234"},
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "normal.user@example.com", "password": "StrongPass!1234"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["roles"] == ["user"]


def test_register_bootstrap_email_becomes_admin(
    client: TestClient,
    settings: Settings,
) -> None:
    settings.bootstrap_super_admin_emails = ["rav.singh@averqel.com"]

    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "rav.singh@averqel.com", "password": "StrongPass!1234"},
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "rav.singh@averqel.com", "password": "StrongPass!1234"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["roles"] == ["admin"]


def test_totp_secret_is_encrypted_at_rest(
    db_session,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-2fa",
        "2fa@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    service = AuthService(db_session, settings)
    auth = AuthContext(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=frozenset({"admin"}),
        token_id="token-1",
    )

    setup = service.setup_totp(auth=auth)
    user = service.users.get_by_id(seeded.tenant_id, seeded.user_id)
    assert user is not None
    assert user.totp_secret
    assert user.totp_secret != setup.secret
    assert setup.secret not in user.totp_secret

    backup_codes = service.confirm_totp(auth=auth, code=pyotp.TOTP(setup.secret).now())
    assert len(backup_codes) == 8

    pending = service.login(
        tenant_id=seeded.tenant_id,
        email=seeded.email,
        password=seeded.password,
    )
    assert pending.requires_2fa is True

    verified = service.verify_totp_login(
        pending_token=pending.pending_token,
        code=pyotp.TOTP(setup.secret).now(),
    )
    assert verified.access_token
