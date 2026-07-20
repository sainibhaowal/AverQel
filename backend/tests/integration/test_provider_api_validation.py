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


def test_provider_create_rejects_invalid_base_url(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-validation",
        "admin-validation@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "custom",
            "display_name": "Broken URL",
            "api_base_url": "ftp://localhost:9999",
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

    assert response.status_code == 422


def test_provider_create_requires_api_key_for_api_key_auth(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-validation-2",
        "admin-validation2@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "openai",
            "display_name": "OpenAI",
            "api_base_url": "https://api.openai.com/v1",
            "auth_mode": "api_key",
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

    assert response.status_code == 422


def test_provider_assignment_rejects_provider_without_embedding_support(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-validation-3",
        "admin-validation3@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    create_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "anthropic",
            "display_name": "Anthropic",
            "api_base_url": "https://api.anthropic.com",
            "auth_mode": "api_key",
            "enabled": True,
            "is_local": False,
            "supports_chat": True,
            "supports_embeddings": False,
            "supports_model_listing": True,
            "supports_model_install": False,
            "timeout_seconds": 30,
            "priority": 1,
            "metadata_json": {},
            "api_key": "anthropic-secret",
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    assignment_response = client.post(
        "/api/v1/providers/assignments",
        headers=headers,
        json={
            "feature_scope": "embeddings",
            "provider_config_id": provider_id,
            "model_name": "text-embedding-004",
            "enabled": True,
            "priority": 1,
        },
    )

    assert assignment_response.status_code == 400
    assert assignment_response.json()["error"]["code"] == "PROVIDER_ASSIGNMENT_INVALID"
