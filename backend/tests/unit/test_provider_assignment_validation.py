from __future__ import annotations

import uuid

import pytest

from app.core.errors import ApiError
from app.providers.models.provider_config import ProviderConfig
from app.providers.services.provider_management_service import ProviderManagementService


def _provider(**overrides: object) -> ProviderConfig:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "workspace_id": None,
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
        "default_chat_model": None,
        "default_embedding_model": None,
        "timeout_seconds": 30,
        "priority": 1,
        "metadata_json": {},
    }
    values.update(overrides)
    return ProviderConfig(**values)


def test_validate_assignment_rejects_disabled_provider() -> None:
    provider = _provider(enabled=False)

    with pytest.raises(ApiError) as exc:
        ProviderManagementService._validate_assignment(feature_scope="chat", provider=provider)

    assert exc.value.code == "PROVIDER_ASSIGNMENT_INVALID"
