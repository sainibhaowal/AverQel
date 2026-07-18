from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import SeededUser


def _login(client: TestClient, tenant_id: str, email: str, password: str) -> str:
    res = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": tenant_id},
        json={"email": email, "password": password},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# /metrics — must stay unauthenticated for Prometheus scraper compatibility
# ---------------------------------------------------------------------------


def test_raw_metrics_endpoint_is_accessible_without_auth(client: TestClient) -> None:
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert "aks_api_requests_total" in response.text


# ---------------------------------------------------------------------------
# /metrics/summary — admin-only JSON endpoint
# ---------------------------------------------------------------------------


def test_metrics_summary_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/metrics/summary")
    assert response.status_code == 401


def test_metrics_summary_forbidden_for_non_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "metrics-reader-tenant", "reader@example.com", "StrongPass!1234", ("reader",)
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/metrics/summary",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_metrics_summary_accessible_for_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "metrics-admin-tenant", "admin@example.com", "StrongPass!1234", ("admin",)
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/metrics/summary",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "api_requests_total" in body
    assert "api_errors_total" in body
    assert "db_query_count" in body
    assert isinstance(body["api_requests_total"], int)
    assert isinstance(body["api_errors_total"], int)
    assert isinstance(body["db_query_count"], int)


# ---------------------------------------------------------------------------
# /analytics/dashboard — dedicated admin analytics permission
# ---------------------------------------------------------------------------


def test_analytics_dashboard_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 401


def test_analytics_dashboard_forbidden_for_reader(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "analytics-reader-tenant",
        "analytics-reader@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/analytics/dashboard",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_analytics_dashboard_accessible_for_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "analytics-admin-tenant",
        "analytics-admin@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/analytics/dashboard",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /capabilities — requires any authenticated user
# ---------------------------------------------------------------------------


def test_capabilities_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 401


def test_capabilities_accessible_for_authenticated_reader(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "cap-reader-tenant", "cap-reader@example.com", "StrongPass!1234", ("reader",)
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/capabilities",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "supported_formats" in body
    assert "ocr_enabled" in body
    assert "vision_enabled" in body
    assert "limits" in body


def test_capabilities_accessible_for_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "cap-admin-tenant", "cap-admin@example.com", "StrongPass!1234", ("admin",)
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/capabilities",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /collections — explicit collection read/write permissions
# ---------------------------------------------------------------------------


def test_collections_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/collections")
    assert response.status_code == 401


def test_collections_accessible_for_authenticated_reader(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "collections-reader-tenant",
        "collections-reader@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    create_response = client.post(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
        json={"name": "Reader Collection", "description": "reader-owned"},
    )
    assert create_response.status_code == 201

    list_response = client.get(
        "/api/v1/collections",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert list_response.status_code == 200
    assert any(item["name"] == "Reader Collection" for item in list_response.json())
