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


def test_provider_routes_do_not_cross_tenant_boundaries(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    tenant_a = seed_user("tenant-a", "admin-a@tenant.example", "StrongPass!1234", ("admin",))
    tenant_b = seed_user("tenant-b", "admin-b@tenant.example", "StrongPass!1234", ("admin",))

    create_response = client.post(
        "/api/v1/providers",
        headers=_auth_headers(client, tenant_a),
        json={
            "provider_type": "custom",
            "display_name": "Tenant A Provider",
            "api_base_url": "http://localhost:1234/v1",
            "auth_mode": "none",
            "enabled": True,
            "is_local": False,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "timeout_seconds": 30,
            "priority": 1,
            "metadata_json": {},
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    get_response = client.get(
        f"/api/v1/providers/{provider_id}",
        headers=_auth_headers(client, tenant_b),
    )
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "PROVIDER_NOT_FOUND"

    models_response = client.get(
        f"/api/v1/providers/{provider_id}/models",
        headers=_auth_headers(client, tenant_b),
    )
    assert models_response.status_code == 404
    assert models_response.json()["error"]["code"] == "PROVIDER_NOT_FOUND"
