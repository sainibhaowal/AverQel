from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.ingestion.services.embedding_service import EmbeddingService
from app.platform.database.session import get_session_factory
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.services.openai_compatible import OpenAICompatibleProvider


def test_embed_many_with_metadata_returns_selected_provider_metadata(
    seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Phase7 Embed Metadata Tenant",
        "phase7-embed-meta@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_MODEL", "env-hash-fallback")
    get_settings.cache_clear()

    session = get_session_factory()()
    try:
        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Metadata Embeddings",
                api_base_url="https://embed-meta.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=False,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model=None,
                default_embedding_model="embed-default",
                timeout_seconds=30,
                priority=1,
                metadata_json={},
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                feature_scope="embeddings",
                provider_config_id=provider.id,
                model_name="embed-meta-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()
        settings = get_settings()

        def _fake_embed_many(self, request):  # type: ignore[no-untyped-def]
            return type(
                "EmbedResponse",
                (),
                {"vectors": [[0.1] * settings.embedding_dimension]},
            )()

        monkeypatch.setattr(OpenAICompatibleProvider, "embed_many", _fake_embed_many)

        service = EmbeddingService(settings, db=session)
        result = service.embed_many_with_metadata(
            ["alpha"],
            tenant_id=seeded.tenant_id,
            actor_user_id=seeded.user_id,
        )
        assert result.vectors == [[0.1] * settings.embedding_dimension]
        assert result.metadata.provider == "openai"
        assert result.metadata.model == "embed-meta-model"
        assert result.metadata.provider_config_id == provider.id
        assert result.metadata.source == "tenant"
        assert result.metadata.fallback_used is False
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()


def test_embedding_errors_surface_redacted_provider_failure_context(
    seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Phase7 Embed Error Tenant",
        "phase7-embed-error@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    monkeypatch.setenv("AKS_EMBEDDING_MODEL", "")
    get_settings.cache_clear()

    session = get_session_factory()()
    try:
        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Broken Embedding Provider",
                api_base_url="https://embed-error.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=False,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model=None,
                default_embedding_model="embed-default",
                timeout_seconds=30,
                priority=1,
                metadata_json={},
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                feature_scope="embeddings",
                provider_config_id=provider.id,
                model_name="embed-error-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        def _broken_embed_many(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("connection refused for https://embed-error.test/v1")

        monkeypatch.setattr(OpenAICompatibleProvider, "embed_many", _broken_embed_many)

        service = EmbeddingService(get_settings(), db=session)
        with pytest.raises(ApiError) as exc_info:
            service.embed_many(
                ["alpha"],
                tenant_id=seeded.tenant_id,
                actor_user_id=seeded.user_id,
            )

        assert exc_info.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"
        assert exc_info.value.details == {
            "provider": {
                "type": "openai",
                "model": "embed-error-model",
                "source": "tenant",
            },
            "reason": "connectivity_failure",
        }
        assert "https://embed-error.test/v1" not in str(exc_info.value.details)
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()
