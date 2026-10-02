from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _headers(seeded: SeededUser, token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}


def test_webhook_management_is_tenant_scoped_and_supports_rotation_and_cursor(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    first = seed_user(
        "tenant-webhook-a", "admin-webhook-a@tenant.example", "StrongPass!1234", ("admin",)
    )
    second = seed_user(
        "tenant-webhook-b", "admin-webhook-b@tenant.example", "StrongPass!1234", ("admin",)
    )
    first_token = _login(client, first)
    second_token = _login(client, second)

    create = client.post(
        "/api/v1/documents/webhooks",
        headers=_headers(first, first_token),
        json={
            "endpoint_url": "http://127.0.0.1:9876/events",
            "event_types": ["document.indexed"],
        },
    )
    assert create.status_code == 200
    webhook_id = create.json()["id"]
    assert create.json()["event_types"] == ["document.indexed"]
    assert create.json()["secret"]

    foreign_list = client.get(
        "/api/v1/documents/webhooks",
        headers=_headers(second, second_token),
    )
    assert foreign_list.status_code == 200
    assert foreign_list.json() == []

    cross_tenant = client.get(
        "/api/v1/documents/webhooks",
        headers={"Authorization": f"Bearer {second_token}", "X-Tenant-Id": str(first.tenant_id)},
    )
    assert cross_tenant.status_code == 403

    rotate = client.post(
        f"/api/v1/documents/webhooks/{webhook_id}/rotate-secret",
        headers=_headers(first, first_token),
    )
    assert rotate.status_code == 200
    assert rotate.json()["secret"]
    assert rotate.json()["secret"] != create.json()["secret"]

    history = client.get(
        f"/api/v1/documents/webhooks/{webhook_id}/deliveries?limit=1",
        headers=_headers(first, first_token),
    )
    assert history.status_code == 200
    assert history.json() == []
