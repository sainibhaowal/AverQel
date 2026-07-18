from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.auth import create_access_token
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


def test_provider_responses_never_expose_secret_material(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "tenant-provider-redaction",
        "admin-redaction@tenant.example",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(client, seeded)
    secret_value = "sk-secret-value-1234"

    create_response = client.post(
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
            "api_key": secret_value,
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert secret_value not in create_response.text
    assert "secret_ciphertext" not in payload
    assert "secret_nonce" not in payload
    assert payload["secrets"][0]["masked_value"] != secret_value
