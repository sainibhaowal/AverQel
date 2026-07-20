from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.services.providers.types import HealthCheckResult
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
            "provider_type": "lmstudio",
            "display_name": "lmstudio",
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


def test_provider_test_and_health_endpoints(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-provider-health",
        "admin-health@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    provider_id = _create_provider(client, headers)

    class FakeDiscovery:
        def list_models(self):
            return []

        def health_check(self):
            return HealthCheckResult(status="healthy", latency_ms=12)

        def chat_model_is_usable(self, model_name: str) -> bool:
            return True

    monkeypatch.setattr(
        "app.services.providers.registry.ProviderRegistry.get_model_discovery_provider_from_config",
        lambda self, provider_config, api_key=None: FakeDiscovery(),
    )
    # LM Studio health check performs a usability probe on the chat model.
    # We must mock the chat provider factory to ensure this probe succeeds.
    monkeypatch.setattr(
        "app.services.providers.registry.ProviderRegistry.get_chat_provider_from_selection",
        lambda self, selection: FakeDiscovery(),
    )

    test_response = client.post(
        f"/api/v1/providers/{provider_id}/test", headers=headers
    )
    assert test_response.status_code == 200
    assert test_response.json()["status"] == "healthy"

    health_response = client.get(
        f"/api/v1/providers/{provider_id}/health", headers=headers
    )
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "healthy"
