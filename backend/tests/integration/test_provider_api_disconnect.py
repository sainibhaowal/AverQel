from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.repositories.providers.provider_secrets import ProviderSecretsRepository
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


def test_provider_disconnect_revokes_local_secret_state(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-disconnect",
        "admin-disconnect@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)

    create_response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "provider_type": "openai",
            "display_name": "disconnect-provider",
            "api_base_url": "https://api.openai.com/v1",
            "auth_mode": "api_key",
            "enabled": True,
            "is_local": False,
            "supports_chat": True,
            "supports_embeddings": True,
            "supports_model_listing": True,
            "supports_model_install": False,
            "default_chat_model": "gpt-4.1-mini",
            "default_embedding_model": "text-embedding-3-small",
            "timeout_seconds": 30,
            "priority": 10,
            "metadata_json": {},
            "api_key": "sk-provider-disconnect-1234",
        },
    )
    assert create_response.status_code == 200
    provider_id = create_response.json()["id"]

    disconnect_response = client.post(
        f"/api/v1/providers/{provider_id}/disconnect", headers=headers
    )
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["revoked_secret_count"] == 1

    session = get_session_factory()()
    try:
        repo = ProviderSecretsRepository(session)
        assert (
            repo.list_for_provider(
                tenant_id=seeded.tenant_id,
                provider_config_id=provider_id,
            )
            == []
        )
    finally:
        session.close()
