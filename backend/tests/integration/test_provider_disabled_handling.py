from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.providers.models.provider_config import ProviderConfig
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


def _create_provider(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "ollama",
            "display_name": "Disabled Ollama",
            "api_base_url": "http://127.0.0.1:11434",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": True,
            "timeout_seconds": 30,
            "priority": 1,
            "metadata_json": {},
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_disabled_provider_cannot_be_tested_or_assigned(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-disabled",
        "admin-disabled@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    provider_id = _create_provider(client, headers)

    disable_response = client.patch(
        f"/api/v1/providers/{provider_id}",
        headers=headers,
        json={"enabled": False},
    )
    assert disable_response.status_code == 200

    test_response = client.post(f"/api/v1/providers/{provider_id}/test", headers=headers)
    assert test_response.status_code == 400
    assert test_response.json()["error"]["code"] == "PROVIDER_ASSIGNMENT_INVALID"

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
    assert assignment_response.status_code == 400
    assert assignment_response.json()["error"]["code"] == "PROVIDER_ASSIGNMENT_INVALID"


def test_duplicate_provider_endpoint_is_rejected(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-duplicate",
        "admin-duplicate@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    _create_provider(client, headers)

    duplicate_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "ollama",
            "display_name": "Duplicate Ollama",
            "api_base_url": "http://127.0.0.1:11434/",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": True,
            "timeout_seconds": 30,
            "priority": 2,
            "metadata_json": {},
        },
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"]["code"] == "DUPLICATE_CONNECTION"


def test_delete_provider_migrates_active_assignments_to_enabled_replacement(
    client: TestClient,
    db_session: object,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-migrate",
        "admin-migrate@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    first_provider_id = _create_provider(client, headers)
    # The public API deliberately rejects a second equivalent endpoint with
    # DUPLICATE_CONNECTION. Seed the valid replacement directly so this test
    # exercises the separate delete/migration contract without weakening that
    # production safety rule.
    first_provider = db_session.execute(
        select(ProviderConfig).where(ProviderConfig.id == first_provider_id)
    ).scalar_one()
    replacement = ProviderConfig(
        tenant_id=first_provider.tenant_id,
        workspace_id=first_provider.workspace_id,
        owner_user_id=first_provider.owner_user_id,
        visibility_scope=first_provider.visibility_scope,
        provider_type=first_provider.provider_type,
        display_name="Replacement Ollama",
        api_base_url=first_provider.api_base_url,
        auth_mode=first_provider.auth_mode,
        enabled=True,
        is_local=first_provider.is_local,
        supports_chat=first_provider.supports_chat,
        supports_embeddings=first_provider.supports_embeddings,
        supports_reranking=first_provider.supports_reranking,
        supports_model_listing=first_provider.supports_model_listing,
        supports_model_install=first_provider.supports_model_install,
        default_chat_model=first_provider.default_chat_model,
        default_embedding_model=first_provider.default_embedding_model,
        default_reranker_model=first_provider.default_reranker_model,
        timeout_seconds=30,
        priority=2,
        metadata_json={},
    )
    db_session.add(replacement)
    db_session.commit()
    second_provider_id = str(replacement.id)

    assignment_response = client.post(
        "/api/v1/providers/assignments",
        headers=headers,
        json={
            "feature_scope": "chat",
            "provider_config_id": first_provider_id,
            "model_name": "llama3.2",
            "enabled": True,
            "priority": 1,
        },
    )
    assert assignment_response.status_code == 200
    assignment_id = assignment_response.json()["id"]

    delete_response = client.delete(f"/api/v1/providers/{first_provider_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    list_response = client.get("/api/v1/providers", headers=headers)
    assert list_response.status_code == 200
    remaining_ids = {item["id"] for item in list_response.json()["items"]}
    assert first_provider_id not in remaining_ids
    assert second_provider_id in remaining_ids

    assignments_response = client.get("/api/v1/providers/assignments", headers=headers)
    assert assignments_response.status_code == 200
    migrated = next(
        item for item in assignments_response.json()["items"] if item["id"] == assignment_id
    )
    assert migrated["provider_config_id"] == second_provider_id
    assert migrated["enabled"] is True
