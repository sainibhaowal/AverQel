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


def test_providers_api_smoke_crud_and_assignment_flow(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-providers-api",
        "providers-api@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    create_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "ollama",
            "display_name": "Ollama Local",
            "api_base_url": "http://localhost:11434",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": True,
            "default_chat_model": "llama3.2",
            "default_embedding_model": "nomic-embed-text",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {},
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    assignment_response = client.post(
        "/api/v1/providers/assignments",
        headers=headers,
        json={
            "feature_scope": "chat",
            "provider_config_id": provider_id,
            "model_name": "llama3.2",
            "enabled": True,
            "priority": 1,
        },
    )
    assert assignment_response.status_code == 200

    list_response = client.get("/api/v1/providers", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == provider_id for item in list_response.json()["items"])

    assignments_response = client.get("/api/v1/providers/assignments", headers=headers)
    assert assignments_response.status_code == 200
    items = assignments_response.json()["items"]
    assert len(items) == 1
    assert items[0]["feature_scope"] == "chat"
    assert items[0]["model_name"] == "llama3.2"
