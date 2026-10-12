from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.auth.dependencies import AuthContext
from app.providers.api import providers as providers_api
from app.providers.schemas.models import ProviderModelPreviewRequest
from app.providers.services.types import ProviderModelInfo

pytestmark = pytest.mark.unit_no_db


def test_provider_model_preview_request_strips_invisible_characters_from_url() -> None:
    payload = ProviderModelPreviewRequest.model_validate(
        {
            "provider_type": "lmstudio",
            "api_base_url": "http://host.docker.internal:1234/v1\ufeff",
            "auth_mode": "local_no_key",
            "supports_model_listing": True,
        }
    )

    assert payload.api_base_url == "http://host.docker.internal:1234/v1"


def test_custom_provider_model_preview_allows_manual_model_ids_without_discovery() -> None:
    payload = ProviderModelPreviewRequest.model_validate(
        {
            "provider_type": "custom",
            "api_base_url": "https://gateway.example/v1",
            "auth_mode": "none",
            "supports_model_listing": False,
            "metadata_json": {
                "openai_compatible": {"models_path": None},
            },
        }
    )

    assert payload.supports_model_listing is False


def test_cline_model_preview_forces_discovery_for_legacy_clients(monkeypatch) -> None:
    tenant_id = uuid.uuid4()
    payload = ProviderModelPreviewRequest.model_validate(
        {
            "provider_type": "cline",
            "api_base_url": "https://api.cline.bot/api/v1",
            "auth_mode": "api_key",
            "supports_chat": True,
            "supports_model_listing": False,
        }
    )

    class FakeDiscovery:
        base_url = "https://api.cline.bot/api/v1"
        supports_model_listing = True

        def list_models(self):
            return [
                ProviderModelInfo(
                    name="anthropic/claude-sonnet-4-6",
                    kind="chat",
                    context_window=200000,
                )
            ]

    class FakeRegistry:
        def __init__(self, _settings) -> None:
            pass

        def get_model_discovery_provider_from_config(self, _provider, *, api_key=None):
            assert api_key is None
            return FakeDiscovery()

    monkeypatch.setattr(providers_api, "ProviderRegistry", FakeRegistry)
    monkeypatch.setattr(providers_api, "acquire_model_discovery_slot", lambda _operation: None)
    monkeypatch.setattr(providers_api, "release_model_discovery_slot", lambda: None)
    auth = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        roles=frozenset(),
        token_id="unit-test",
    )

    response = providers_api.preview_models(
        payload,
        request_tenant_id=tenant_id,
        auth=auth,
        db=MagicMock(),
        settings=MagicMock(),
    )

    assert [item.model_name for item in response.items] == ["anthropic/claude-sonnet-4-6"]


def test_model_preview_includes_verified_reasoning_capabilities(monkeypatch) -> None:
    tenant_id = uuid.uuid4()
    payload = ProviderModelPreviewRequest.model_validate(
        {
            "provider_type": "nvidia-nim",
            "api_base_url": "https://integrate.api.nvidia.com/v1",
            "auth_mode": "api_key",
            "api_key": "test-key",
            "supports_chat": True,
            "supports_model_listing": True,
        }
    )

    class FakeDiscovery:
        base_url = "https://integrate.api.nvidia.com/v1"
        supports_model_listing = True

        def list_models(self):
            return [
                ProviderModelInfo(
                    name="nvidia/nemotron-3-ultra-550b-a55b",
                    kind="chat",
                )
            ]

    class FakeRegistry:
        def __init__(self, _settings) -> None:
            pass

        def get_model_discovery_provider_from_config(self, _provider, *, api_key=None):
            assert api_key == "test-key"
            return FakeDiscovery()

    monkeypatch.setattr(providers_api, "ProviderRegistry", FakeRegistry)
    monkeypatch.setattr(providers_api, "acquire_model_discovery_slot", lambda _operation: None)
    monkeypatch.setattr(providers_api, "release_model_discovery_slot", lambda: None)
    auth = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        roles=frozenset(),
        token_id="unit-test",
    )

    response = providers_api.preview_models(
        payload,
        request_tenant_id=tenant_id,
        auth=auth,
        db=MagicMock(),
        settings=MagicMock(),
    )

    assert response.items[0].capabilities_json["reasoning_capabilities_known"] is True
    assert response.items[0].capabilities_json["supported_reasoning_efforts"] == [
        "medium",
        "high",
    ]


def test_other_api_key_model_previews_still_require_the_key() -> None:
    with pytest.raises(ValidationError, match="api_key is required"):
        ProviderModelPreviewRequest.model_validate(
            {
                "provider_type": "openai",
                "api_base_url": "https://api.openai.com/v1",
                "auth_mode": "api_key",
                "supports_chat": True,
                "supports_model_listing": True,
            }
        )
