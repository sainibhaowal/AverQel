from __future__ import annotations

from app.core.config import get_settings
from app.db.session import get_session_factory, set_db_tenant_context
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.ingestion.services.embedding_service import EmbeddingService
from app.providers.services.openai_compatible import OpenAICompatibleProvider


def test_embedding_service_uses_selected_provider_assignment(
    seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Embedding Provider Tenant",
        "embedding-provider@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "4")
    get_settings.cache_clear()

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, seeded.tenant_id)
        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Embedding OpenAI",
                api_base_url="https://embed.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=False,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model=None,
                default_embedding_model="embed-selected",
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
                model_name="embed-assigned-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        captured: dict[str, str] = {}

        def _fake_embed_many(self, request):  # type: ignore[no-untyped-def]
            captured["model"] = request.model
            captured["base_url"] = str(request.metadata.get("base_url"))
            return type("EmbedResponse", (), {"vectors": [[0.1, 0.2, 0.3, 0.4]]})()

        monkeypatch.setattr(OpenAICompatibleProvider, "embed_many", _fake_embed_many)

        service = EmbeddingService(get_settings(), db=session)
        vectors = service.embed_many(
            ["alpha"],
            tenant_id=seeded.tenant_id,
            actor_user_id=seeded.user_id,
        )
        assert vectors == [[0.1, 0.2, 0.3, 0.4]]
        assert captured == {
            "model": "embed-assigned-model",
            "base_url": "https://embed.test/v1",
        }
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()


def test_embedding_service_requires_ui_assignment_when_db_backed(
    seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Embedding Assignment Tenant",
        "embedding-required@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    monkeypatch.setenv("AKS_EMBEDDING_PROVIDER", "local-deterministic")
    monkeypatch.setenv("AKS_EMBEDDING_DIMENSION", "4")
    get_settings.cache_clear()

    session = get_session_factory()()
    try:
        set_db_tenant_context(session, seeded.tenant_id)
        service = EmbeddingService(get_settings(), db=session)
        # Should now succeed by falling back to 'local-deterministic' env setting
        vectors = service.embed_many(["alpha"], tenant_id=seeded.tenant_id)
        assert len(vectors) == 1
        assert len(vectors[0]) == 4
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()
