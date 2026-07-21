from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.providers.services.base import ProviderRequestError
from app.providers.services.registry import ProviderRegistry
from app.providers.services.types import ProviderModelInfo
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


def _create_provider(client: TestClient, headers: dict[str, str], name: str) -> str:
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "lmstudio",
            "display_name": name,
            "api_base_url": "http://localhost:1234/v1",
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "default_chat_model": "local-chat",
            "default_embedding_model": "local-embed",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {},
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_provider_assignment_crud_respects_scope(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-assign",
        "admin-assign@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    provider_id = _create_provider(client, headers, "LM Studio")

    create_response = client.post(
        "/api/v1/providers/assignments",
        headers=headers,
        json={
            "feature_scope": "chat",
            "provider_config_id": provider_id,
            "model_name": "local-chat",
            "enabled": True,
            "priority": 5,
        },
    )
    assert create_response.status_code == 200
    assignment_id = create_response.json()["id"]
    assert create_response.json()["provider_config_id"] == provider_id

    patch_response = client.patch(
        f"/api/v1/providers/assignments/{assignment_id}",
        headers=headers,
        json={"model_name": "local-chat-v2", "enabled": False},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["model_name"] == "local-chat-v2"
    assert patch_response.json()["enabled"] is False


def test_preview_models_lists_runtime_models_before_provider_save(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-provider-preview",
        "admin-preview@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    class _PreviewDiscovery:
        def list_models(self) -> list[ProviderModelInfo]:
            return [
                ProviderModelInfo(
                    name="mistralai/ministral-3-3b",
                    kind="chat",
                    display_name="Ministral 3B",
                )
            ]

        def list_embedding_models(self) -> list[ProviderModelInfo]:
            return [
                ProviderModelInfo(
                    name="text-embedding-nomic-embed-text-v1.5",
                    kind="embedding",
                    display_name="Nomic Embed",
                )
            ]

    monkeypatch.setattr(
        ProviderRegistry,
        "get_model_discovery_provider_from_config",
        lambda self, provider, api_key=None: _PreviewDiscovery(),
    )

    response = client.post(
        "/api/v1/providers/models/preview",
        headers=headers,
        json={
            "provider_type": "lmstudio",
            "api_base_url": "http://host.docker.internal:1234/v1",
            "auth_mode": "local_no_key",
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["model_name"] for item in items] == [
        "mistralai/ministral-3-3b",
        "text-embedding-nomic-embed-text-v1.5",
    ]


def test_preview_models_lists_server_embedding_models_without_base_url(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-provider-server-embed",
        "admin-server-embed@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    class _EmbeddingDiscovery:
        def list_embedding_models(self) -> list[ProviderModelInfo]:
            return [
                ProviderModelInfo(
                    name="BAAI/bge-small-en-v1.5",
                    kind="embedding",
                    display_name="BGE Small English v1.5",
                ),
                ProviderModelInfo(
                    name="intfloat/multilingual-e5-small",
                    kind="embedding",
                    display_name="Multilingual E5 Small",
                ),
            ]

    monkeypatch.setattr(
        ProviderRegistry,
        "get_model_discovery_provider_from_config",
        lambda self, provider, api_key=None: _EmbeddingDiscovery(),
    )

    response = client.post(
        "/api/v1/providers/models/preview",
        headers=headers,
        json={
            "provider_type": "sentence-transformers",
            "auth_mode": "none",
            "supports_chat": False,
            "supports_embeddings": True,
            "supports_model_listing": True,
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["model_name"] for item in items] == [
        "BAAI/bge-small-en-v1.5",
        "intfloat/multilingual-e5-small",
    ]


def test_preview_models_returns_clear_message_for_invalid_cloud_api_key(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-provider-preview-auth",
        "admin-provider-preview-auth@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    class _BadDiscovery:
        def list_models(self) -> list[ProviderModelInfo]:
            raise ProviderRequestError(
                provider_name="anthropic",
                status_code=401,
                message="invalid x-api-key",
            )

        def list_embedding_models(self) -> list[ProviderModelInfo]:
            return []

    monkeypatch.setattr(
        ProviderRegistry,
        "get_model_discovery_provider_from_config",
        lambda self, provider, api_key=None: _BadDiscovery(),
    )

    response = client.post(
        "/api/v1/providers/models/preview",
        headers=headers,
        json={
            "provider_type": "anthropic",
            "api_base_url": "https://api.anthropic.com/v1",
            "auth_mode": "api_key",
            "supports_chat": True,
            "supports_embeddings": False,
            "supports_model_listing": True,
            "api_key": "bad-key",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "PROVIDER_TEST_FAILED"
    assert (
        payload["error"]["message"]
        == "Anthropic API key is incorrect or does not have access. Please update the key and try again."
    )
