from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
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


def _create_provider(
    client: TestClient, headers: dict[str, str], provider_type: str
) -> str:
    is_ollama = provider_type == "ollama"
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": provider_type,
            "display_name": provider_type,
            "api_base_url": (
                "http://localhost:11434" if is_ollama else "http://localhost:1234/v1"
            ),
            "auth_mode": "local_no_key",
            "enabled": True,
            "is_local": True,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": is_ollama,
            "default_chat_model": "local-chat",
            "default_embedding_model": "local-embed",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {},
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_provider_models_refresh_and_list(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-provider-models",
        "admin-models@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    provider_id = _create_provider(client, headers, "lmstudio")

    class FakeDiscovery:
        def list_models(self):
            return [
                ProviderModelInfo(
                    name="chat-model",
                    kind="chat",
                    capabilities={
                        "runtime": "lmstudio",
                        "selection_only": True,
                        "supports_chat": True,
                        "supports_embeddings": True,
                        "install_supported": False,
                    },
                )
            ]

        def list_embedding_models(self):
            return [
                ProviderModelInfo(
                    name="embed-model",
                    kind="embedding",
                    capabilities={
                        "runtime": "lmstudio",
                        "selection_only": True,
                        "supports_chat": False,
                        "supports_embeddings": True,
                        "install_supported": False,
                    },
                )
            ]

    monkeypatch.setattr(
        "app.providers.services.registry.ProviderRegistry.get_model_discovery_provider_from_config",
        lambda self, provider_config, api_key=None: FakeDiscovery(),
    )

    refresh_response = client.post(
        f"/api/v1/providers/{provider_id}/models/refresh", headers=headers
    )
    assert refresh_response.status_code == 200
    assert len(refresh_response.json()["items"]) == 2
    items = refresh_response.json()["items"]
    chat_row = next(item for item in items if item["model_kind"] == "chat")
    embed_row = next(item for item in items if item["model_kind"] == "embedding")
    assert chat_row["capabilities_json"]["runtime"] == "lmstudio"
    assert chat_row["capabilities_json"]["selection_only"] is True
    assert embed_row["capabilities_json"]["supports_embeddings"] is True

    list_response = client.get(
        f"/api/v1/providers/{provider_id}/models", headers=headers
    )
    assert list_response.status_code == 200
    assert {item["model_name"] for item in list_response.json()["items"]} == {
        "chat-model",
        "embed-model",
    }


def test_provider_model_pull_supported_only_where_allowed(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-provider-pull",
        "admin-pull@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    provider_id = _create_provider(client, headers, "ollama")

    class FakeInstaller:
        def pull_model(self, model_name: str):
            return None

    monkeypatch.setattr(
        "app.providers.services.registry.ProviderRegistry.get_install_provider_from_config",
        lambda self, provider_config, api_key=None: FakeInstaller(),
    )

    response = client.post(
        f"/api/v1/providers/{provider_id}/models/pull",
        headers=headers,
        json={"model_name": "llama3.2"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_provider_model_pull_is_rejected_for_selection_only_runtime(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-lmstudio-pull",
        "admin-lmstudio-pull@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    provider_id = _create_provider(client, headers, "lmstudio")

    response = client.post(
        f"/api/v1/providers/{provider_id}/models/pull",
        headers=headers,
        json={"model_name": "qwen2.5-coder-7b-instruct"},
    )
    assert response.status_code == 400
    assert "unsupported" in response.text.lower()
