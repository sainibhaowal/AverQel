from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def _auth_headers(client: TestClient, seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"admin"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_provider_oauth_callback_rejects_invalid_state(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-oauth-security",
        "admin-oauth-security@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )

    response = client.get(
        "/api/v1/providers/oauth/openai/callback",
        params={
            "tenant_id": str(seeded.tenant_id),
            "code": "fake-code",
            "state": "invalid",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROVIDER_OAUTH_UNSUPPORTED"
