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


def test_unhandled_exception_returns_standard_error_payload(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-error-shape",
        "reader-error-shape@tenant.example",
        "StrongPass!1234",
        ("reader",),
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={
            "query": "trigger validation error",
            "top_k": 5,
            "filters": {"unknown": "x"},
        },
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_FILTER_FIELD"
    assert payload["trace_id"]
