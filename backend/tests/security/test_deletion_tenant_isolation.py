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


def test_cross_tenant_deletion_status_access_is_blocked(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    tenant_a = seed_user(
        "tenant-del-a", "admin-del-a@tenant.example", "StrongPass!1234", ("admin",)
    )
    tenant_b = seed_user(
        "tenant-del-b", "admin-del-b@tenant.example", "StrongPass!1234", ("admin",)
    )
    get_settings().bootstrap_super_admin_emails = [tenant_a.email, tenant_b.email]

    token_a = _login(client, tenant_a)
    token_b = _login(client, tenant_b)

    create = client.post(
        "/api/v1/admin/data-deletions",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Tenant-Id": str(tenant_a.tenant_id),
        },
        json={"reason": "tenant-a purge"},
    )
    assert create.status_code == 200
    deletion_id = create.json()["deletion_id"]

    cross_tenant_status = client.get(
        f"/api/v1/admin/data-deletions/{deletion_id}",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Tenant-Id": str(tenant_b.tenant_id),
        },
    )
    assert cross_tenant_status.status_code == 404
    assert cross_tenant_status.json()["error"]["code"] == "DATA_DELETION_NOT_FOUND"
