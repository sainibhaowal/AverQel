from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest
import redis.asyncio as aioredis
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.system.api import metrics as metrics_api
from app.system.services.metrics_service import (
    RUNTIME_METRICS_UPDATE_CHANNEL,
    increment_runtime_metric,
    read_runtime_metrics_summary_async,
)
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


def test_metrics_summary_stream_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/metrics/summary/stream")
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


def test_metrics_summary_stream_forbidden_for_non_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "metrics-stream-reader-tenant",
        "metrics-stream-reader@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/metrics/summary/stream",
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
    assert body["metrics_scope"] == "service-wide"
    assert isinstance(body["metrics_complete"], bool)
    assert body["metrics_started_at"]
    assert body["snapshot_at"]


def test_metrics_summary_stream_sends_service_snapshot_to_platform_admin(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    user = seed_user(
        "metrics-stream-admin-tenant", "stream-admin@example.com", "StrongPass!1234", ("admin",)
    )
    get_settings().bootstrap_super_admin_emails = [user.email]
    token = _login(client, str(user.tenant_id), user.email, user.password)
    monkeypatch.setattr(metrics_api, "METRICS_STREAM_MAX_SECONDS", 0)

    with client.stream(
        "GET",
        "/api/v1/metrics/summary/stream",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    ) as response:
        assert response.status_code == 200
        lines = response.iter_lines()
        initial_line = next(line for line in lines if line.startswith("data: "))
        initial = json.loads(initial_line.removeprefix("data: "))

    assert initial["metrics_scope"] == "service-wide"
    assert isinstance(initial["api_requests_total"], int)
    assert initial["snapshot_at"]


@pytest.mark.asyncio
async def test_metrics_stream_emits_a_shared_redis_counter_update(monkeypatch) -> None:
    settings = get_settings()
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(RUNTIME_METRICS_UPDATE_CHANNEL)
    initial = await read_runtime_metrics_summary_async(client)
    monkeypatch.setattr(metrics_api, "METRICS_STREAM_MAX_SECONDS", 10)
    stream = metrics_api._stream_metrics_snapshots(
        client=client,
        pubsub=pubsub,
        initial_snapshot=initial,
    )

    try:
        initial_event = await anext(stream)
        previous_allocations = initial["deepspace_budget_allocations_total"]
        assert increment_runtime_metric("deepspace_budget_allocations_total") is True
        updated_event = await asyncio.wait_for(anext(stream), timeout=5)
    finally:
        await stream.aclose()

    initial_payload = json.loads(initial_event.split("data: ", maxsplit=1)[1])
    updated_payload = json.loads(updated_event.split("data: ", maxsplit=1)[1])
    assert initial_payload["metrics_scope"] == "service-wide"
    assert updated_payload["deepspace_budget_allocations_total"] == previous_allocations + 1
    assert updated_payload["metrics_scope"] == "service-wide"


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
