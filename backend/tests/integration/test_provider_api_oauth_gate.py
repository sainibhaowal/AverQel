from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.auth import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def _auth_headers(
    client: TestClient,
    seeded: SeededUser,
    *,
    roles: tuple[str, ...] | None = None,
) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles or ("admin",)),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_provider_oauth_gate_is_safe_by_default(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-oauth",
        "admin-oauth@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    status_response = client.get(
        "/api/v1/providers/oauth/openai/status", headers=headers
    )
    assert status_response.status_code == 200
    assert status_response.json()["available"] is False
    assert status_response.json()["connected"] is False

    start_response = client.post(
        "/api/v1/providers/oauth/openai/start",
        headers=headers,
        json={"provider_type": "openai"},
    )
    assert start_response.status_code == 400
    assert start_response.json()["error"]["code"] == "PROVIDER_OAUTH_UNSUPPORTED"


def test_user_role_can_reach_provider_oauth_gate(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-oauth-user",
        "user-oauth@tenant.example",
        "StrongPass!1234",
        ("user",),
    )
    headers = _auth_headers(client, seeded)

    status_response = client.get(
        "/api/v1/providers/oauth/openai/status", headers=headers
    )
    assert status_response.status_code == 200
    assert status_response.json()["available"] is False
    assert status_response.json()["connected"] is False

    start_response = client.post(
        "/api/v1/providers/oauth/openai/start",
        headers=headers,
        json={"provider_type": "openai"},
    )
    assert start_response.status_code == 400
    assert start_response.json()["error"]["code"] == "PROVIDER_OAUTH_UNSUPPORTED"
