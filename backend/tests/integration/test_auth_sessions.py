from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import SeededUser


def test_user_can_list_and_revoke_one_linked_session(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-auth-sessions",
        "sessions@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = {"X-Tenant-Id": str(seeded.tenant_id)}
    login = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={
            "email": seeded.email,
            "password": seeded.password,
            "device_id": "browser-one",
            "device_label": "Laptop",
        },
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]
    auth_headers = {**headers, "Authorization": f"Bearer {access_token}"}

    listed = client.get("/api/v1/auth/sessions", headers=auth_headers)
    assert listed.status_code == 200
    sessions = listed.json()
    assert len(sessions) == 1
    assert sessions[0]["device_id"] == "browser-one"
    assert sessions[0]["current"] is True

    revoked = client.delete(f"/api/v1/auth/sessions/{sessions[0]['id']}", headers=auth_headers)
    assert revoked.status_code == 200
    assert revoked.json() == {"success": True}

    profile = client.get("/api/v1/auth/profile", headers=auth_headers)
    assert profile.status_code == 401
    assert profile.json()["error"]["code"] == "SESSION_REVOKED"
