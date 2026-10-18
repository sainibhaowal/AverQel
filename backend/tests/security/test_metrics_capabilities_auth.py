from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.auth.models.user import User
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.query.models.query import Query
from tests.conftest import SeededUser, _generate_test_collection_code


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
    user = seed_user("metrics-reader-tenant", "reader@example.com", "StrongPass!1234", ("reader",))
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
    user = seed_user("metrics-admin-tenant", "admin@example.com", "StrongPass!1234", ("admin",))
    get_settings().bootstrap_super_admin_emails = [user.email]
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


def test_metrics_summary_forbidden_for_admin_outside_platform_allowlist(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "metrics-unlisted-admin-tenant",
        "unlisted-admin@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = ["different-owner@example.com"]
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
    assert response.json()["suppressed"] is True
    assert response.json()["total_queries"] is None


def test_analytics_dashboard_uses_fixed_window_and_suppresses_small_daily_groups(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    admin = seed_user(
        "analytics-window-tenant",
        "analytics-window-admin@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    settings = get_settings()
    settings.bootstrap_super_admin_emails = [admin.email]
    now = datetime.now(UTC)
    member_ids = [generate_uuid7_with_fallback() for _ in range(4)]

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, admin.tenant_id)
        for index, member_id in enumerate(member_ids):
            session.add(
                User(
                    id=member_id,
                    tenant_id=admin.tenant_id,
                    email=f"analytics-member-{index}@example.com",
                    collection_code=_generate_test_collection_code(),
                    password_hash=hash_password("UnusedStrongPass!1234"),
                    is_active=True,
                )
            )
        session.flush()
        contributors = [admin.user_id, *member_ids]
        for index, user_id in enumerate(contributors):
            created_at = now - timedelta(days=31 if index == 4 else index + 1)
            session.add(
                Query(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=admin.tenant_id,
                    user_id=user_id,
                    query_text="private query prompt",
                    normalized_query="private query prompt",
                    top_k=3,
                    cache_hit=False,
                    answer="private answer text",
                    confidence=0.8,
                    trace_id=str(uuid.uuid4()),
                    shared_with=[],
                    created_at=created_at,
                )
            )
        session.commit()
    finally:
        session.rollback()
        session.close()

    token = _login(client, str(admin.tenant_id), admin.email, admin.password)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(admin.tenant_id),
    }
    response = client.get("/api/v1/analytics/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["suppressed"] is True

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, admin.tenant_id)
        session.add(
            Query(
                id=generate_uuid7_with_fallback(),
                tenant_id=admin.tenant_id,
                user_id=member_ids[-1],
                query_text="private query prompt",
                normalized_query="private query prompt",
                top_k=3,
                cache_hit=False,
                answer="private answer text",
                confidence=0.8,
                trace_id=str(uuid.uuid4()),
                shared_with=[],
                created_at=now - timedelta(days=2),
            )
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    response = client.get("/api/v1/analytics/dashboard", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["suppressed"] is False
    assert payload["total_queries"] == 5
    assert payload["volume_over_time"] == []
    assert "user_id" not in response.text
    assert "private query prompt" not in response.text
    assert "private answer text" not in response.text


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
    user = seed_user("cap-reader-tenant", "cap-reader@example.com", "StrongPass!1234", ("reader",))
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
    user = seed_user("cap-admin-tenant", "cap-admin@example.com", "StrongPass!1234", ("admin",))
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
