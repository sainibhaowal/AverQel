from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.providers.repositories.provider_health_checks import ProviderHealthChecksRepository
from app.providers.repositories.provider_model_cache import ProviderModelCacheRepository
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.provider_models_service import ProviderModelsService
from app.providers.services.types import HealthCheckResult, ProviderModelInfo

pytestmark = pytest.mark.unit_no_db


def test_disabled_custom_model_route_preserves_cached_models_without_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_models = [object()]
    provider = SimpleNamespace(
        id=uuid.uuid4(),
        provider_type="custom",
        supports_model_listing=True,
        supports_chat=True,
        supports_embeddings=False,
        supports_reranking=False,
        api_base_url="https://gateway.example/v1",
        metadata_json={"openai_compatible": {"models_path": None}},
    )
    discovery = OpenAICompatibleProvider(
        provider_name="custom",
        base_url=provider.api_base_url,
        provider_metadata=provider.metadata_json,
    )
    registry = MagicMock()
    registry.get_model_discovery_provider_from_config.return_value = discovery
    service = ProviderModelsService(db=MagicMock(), registry=registry)
    monkeypatch.setattr(ProviderModelsService, "_get_provider", lambda self, **kwargs: provider)
    monkeypatch.setattr(ProviderModelsService, "_resolve_api_key", lambda self, **kwargs: None)
    monkeypatch.setattr(
        ProviderModelCacheRepository, "list_models", lambda self, **kwargs: cached_models
    )

    result = service.refresh_models(
        tenant_id=uuid.uuid4(),
        provider_config_id=provider.id,
        actor_user_id=None,
    )

    assert result == cached_models
    registry.get_model_discovery_provider_from_config.assert_called_once_with(
        provider, api_key=None
    )


def test_refresh_discovers_models_for_legacy_cline_config_with_listing_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    provider = SimpleNamespace(
        id=provider_id,
        tenant_id=tenant_id,
        workspace_id=None,
        provider_type="cline",
        display_name="Cline API",
        auth_mode="api_key",
        enabled=True,
        supports_model_listing=False,
        supports_chat=True,
        supports_embeddings=False,
        supports_reranking=False,
        api_base_url="https://api.cline.bot/api/v1",
        metadata_json={},
        default_chat_model="anthropic/claude-sonnet-4-6",
        default_embedding_model=None,
        default_reranker_model=None,
        timeout_seconds=30,
    )

    class FakeDiscovery:
        supports_model_listing = True

        def list_models(self):
            return [
                ProviderModelInfo(
                    name="anthropic/claude-sonnet-4-6",
                    kind="chat",
                    capabilities={},
                )
            ]

    registry = MagicMock()
    registry.get_model_discovery_provider_from_config.return_value = FakeDiscovery()
    service = ProviderModelsService(db=MagicMock(), registry=registry)
    captured_models = []
    monkeypatch.setattr(ProviderModelsService, "_get_provider", lambda self, **kwargs: provider)
    monkeypatch.setattr(
        ProviderModelsService,
        "_resolve_api_key",
        lambda self, **kwargs: pytest.fail("Cline catalog refresh must not read the API key"),
    )
    monkeypatch.setattr(
        ProviderModelCacheRepository,
        "upsert_models",
        lambda self, **kwargs: captured_models.extend(kwargs["models"]) or captured_models,
    )
    monkeypatch.setattr(
        ProviderModelCacheRepository,
        "list_models",
        lambda self, **kwargs: captured_models,
    )
    monkeypatch.setattr(
        ProviderModelCacheRepository,
        "purge_stale_models",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        ProviderModelsService,
        "_backfill_provider_defaults_and_assignments",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        ProviderModelsService,
        "_resolve_usable_chat_model_names",
        lambda *args, **kwargs: {"anthropic/claude-sonnet-4-6"},
    )

    result = service.refresh_models(
        tenant_id=tenant_id,
        provider_config_id=provider_id,
        actor_user_id=None,
    )

    assert len(result) == 1
    assert result[0].model_name == "anthropic/claude-sonnet-4-6"
    registry.get_model_discovery_provider_from_config.assert_called_once_with(
        provider,
        api_key=None,
    )


def test_cline_health_test_does_not_read_key_for_public_model_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    provider = SimpleNamespace(
        id=provider_id,
        tenant_id=tenant_id,
        workspace_id=None,
        provider_type="cline",
        display_name="Cline API",
        auth_mode="api_key",
        enabled=True,
        supports_model_listing=True,
        supports_chat=True,
        supports_embeddings=False,
        supports_reranking=False,
        api_base_url="https://api.cline.bot/api/v1",
        metadata_json={},
        default_chat_model="anthropic/claude-sonnet-4-6",
        default_embedding_model=None,
        default_reranker_model=None,
        timeout_seconds=30,
    )

    class FakeDiscovery:
        def health_check(self):
            return HealthCheckResult(
                status="degraded",
                error_code="chat_access_not_verified",
                error_message_redacted=(
                    "Cline's public model catalog is reachable; chat access was not probed."
                ),
                metadata={"listing": "public_catalog", "chat_probe": "not_run"},
            )

    registry = MagicMock()
    registry.get_model_discovery_provider_from_config.return_value = FakeDiscovery()
    service = ProviderModelsService(db=MagicMock(), registry=registry)
    monkeypatch.setattr(ProviderModelsService, "_get_provider", lambda self, **kwargs: provider)
    monkeypatch.setattr(
        ProviderModelsService,
        "_resolve_api_key",
        lambda self, **kwargs: pytest.fail("Cline catalog health test must not read the API key"),
    )
    monkeypatch.setattr(
        ProviderHealthChecksRepository,
        "record_check",
        lambda self, row: SimpleNamespace(status=row.status),
    )

    result = service.test_provider(
        tenant_id=tenant_id,
        provider_config_id=provider_id,
        actor_user_id=None,
    )

    assert result.status == "degraded"
    registry.get_model_discovery_provider_from_config.assert_called_once_with(
        provider,
        api_key=None,
    )
