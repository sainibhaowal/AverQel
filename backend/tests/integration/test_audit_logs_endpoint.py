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


def test_admin_audit_logs_endpoint_returns_tenant_scoped_items(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-audit", "admin-audit@tenant.example", "StrongPass!1234", ("admin",)
    )
    get_settings().bootstrap_super_admin_emails = [seeded.email]
    token = _login(client, seeded)

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
