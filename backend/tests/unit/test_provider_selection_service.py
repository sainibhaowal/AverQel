from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.ids import generate_uuid7_with_fallback
from app.auth.security import hash_password
from app.platform.database.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.models.provider_health_check import ProviderHealthCheck
from app.providers.models.provider_model_cache import ProviderModelCache
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.repositories.provider_health_checks import (
    ProviderHealthChecksRepository,
)
from app.providers.services.selection_service import ProviderSelectionService
from app.providers.services.types import ProviderModelInfo
from tests.conftest import _generate_test_collection_code

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _tenant(name: str) -> Tenant:
    return Tenant(id=generate_uuid7_with_fallback(), name=name)


def _user(tenant_id: uuid.UUID, email: str) -> User:
    return User(
        id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        email=email,
        collection_code=_generate_test_collection_code(),
        password_hash=hash_password("StrongPass!1234"),
        is_active=True,
    )


def _provider(
    *,
    tenant_id: uuid.UUID,
    display_name: str,
    provider_type: str = "ollama",
    supports_chat: bool = True,
    supports_embeddings: bool = True,
    supports_reranking: bool = False,
    workspace_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        visibility_scope="user" if owner_user_id is not None else "system",
        provider_type=provider_type,
        display_name=display_name,
        api_base_url="http://localhost:11434",
        auth_mode="local_no_key",
        enabled=True,
        is_local=True,
        supports_chat=supports_chat,
        supports_embeddings=supports_embeddings,
        supports_reranking=supports_reranking,
        supports_model_listing=True,
        supports_model_install=True,
        default_chat_model="llama3",
        default_embedding_model="nomic-embed-text",
        default_reranker_model="BAAI/bge-reranker-v2-m3",
        timeout_seconds=30,
        priority=10,
        metadata_json={},
    )


def test_personal_assignment_is_selected_with_workspace_context(settings) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Selection Tenant")
        user = _user(tenant.id, "selection-user@example.com")
        workspace_id = generate_uuid7_with_fallback()
        session.add_all([tenant, user])
        session.flush()

        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="Personal Provider",
                owner_user_id=user.id,
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="chat",
                provider_config_id=provider.id,
                model_name="personal-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_chat(
            tenant_id=tenant.id,
            workspace_id=workspace_id,
            actor_user_id=user.id,
        )
        assert selection.candidates[0].provider_config_id == provider.id
        assert selection.candidates[0].source == "workspace"
        assert selection.candidates[0].model_name == "personal-model"
    finally:
        session.rollback()
        session.close()


def test_unhealthy_provider_falls_back_to_tenant_fallback(settings) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Fallback Tenant")
        user = _user(tenant.id, "fallback-user@example.com")
        session.add_all([tenant, user])
        session.flush()

        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        health = ProviderHealthChecksRepository(session)

        primary = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="Primary",
                owner_user_id=user.id,
            )
        )
        fallback = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="Fallback",
                owner_user_id=user.id,
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="chat",
                provider_config_id=primary.id,
                model_name="primary-model",
                enabled=True,
                priority=1,
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="fallback_chat",
                provider_config_id=fallback.id,
                model_name="fallback-model",
                enabled=True,
                priority=1,
            )
        )
        health.record_check(
            ProviderHealthCheck(
                tenant_id=tenant.id,
                provider_config_id=primary.id,
                status="unhealthy",
                latency_ms=999,
                error_code="TIMEOUT",
                error_message_redacted="timeout",
                metadata_json={},
                checked_at=datetime.now(tz=UTC),
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_chat(
            tenant_id=tenant.id,
            actor_user_id=user.id,
        )
        assert selection.candidates[0].provider_config_id == fallback.id
        assert selection.candidates[0].source == "tenant_fallback"
        assert any("health-reject" in note for note in selection.selection_notes)
    finally:
        session.rollback()
        session.close()


def test_missing_assignment_returns_no_candidates(settings) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Env Fallback Tenant")
        session.add(tenant)
        session.flush()

        selection = ProviderSelectionService(session, settings).resolve_embeddings(
            tenant_id=tenant.id,
            actor_user_id=None,
        )
        assert selection.candidates == []
    finally:
        session.rollback()
        session.close()


def test_context_window_does_not_fall_back_to_stale_cache_when_live_discovery_is_unknown(
    settings,
    monkeypatch,
) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Context Window Cache Guard Tenant")
        session.add(tenant)
        session.flush()

        configs = ProviderConfigsRepository(session)
        provider = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="LM Studio",
                provider_type="lmstudio",
            )
        )
        session.add(
            ProviderModelCache(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                model_name="qwen2.5-14b-instruct",
                model_kind="chat",
                display_name="Stale cached model",
                context_window=128000,
                capabilities_json={},
                is_available=True,
            )
        )
        session.commit()

        class _FakeDiscovery:
            @staticmethod
            def list_models() -> list[ProviderModelInfo]:
                return []

        service = ProviderSelectionService(session, settings)
        monkeypatch.setattr(
            service.registry,
            "get_model_discovery_provider_from_config",
            lambda *args, **kwargs: _FakeDiscovery(),
        )

        context_window, context_window_source = service._resolve_model_context_window(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            model_name="qwen2.5-14b-instruct",
        )

        assert context_window is None
        assert context_window_source is None
    finally:
        session.rollback()
        session.close()


def test_context_window_uses_verified_docs_when_live_discovery_is_missing(
    settings,
    monkeypatch,
) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Context Window Verified Docs Tenant")
        session.add(tenant)
        session.flush()

        configs = ProviderConfigsRepository(session)
        provider = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="OpenCode Zen",
                provider_type="opencode-zen",
            )
        )
        session.commit()

        class _FakeDiscovery:
            @staticmethod
            def list_models() -> list[ProviderModelInfo]:
                return []

        service = ProviderSelectionService(session, settings)
        monkeypatch.setattr(
            service.registry,
            "get_model_discovery_provider_from_config",
            lambda *args, **kwargs: _FakeDiscovery(),
        )

        context_window, context_window_source = service._resolve_model_context_window(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            model_name="gemini-3-pro",
        )

        assert context_window == 1_048_576
        assert context_window_source == "official_docs:google"
    finally:
        session.rollback()
        session.close()


def test_reranking_auto_selects_sentence_transformers_provider(settings) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Reranking Tenant")
        session.add(tenant)
        session.flush()

        configs = ProviderConfigsRepository(session)
        reranker = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="AverQel Server Retrieval",
                provider_type="sentence-transformers",
                supports_chat=False,
                supports_embeddings=True,
                supports_reranking=True,
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_reranking(
            tenant_id=tenant.id,
            actor_user_id=None,
        )
        assert selection.candidates[0].provider_config_id == reranker.id
        assert selection.candidates[0].model_name == "BAAI/bge-reranker-v2-m3"
        assert selection.candidates[0].feature_scope == "reranking"
        assert selection.candidates[0].source == "env_fallback"
    finally:
        session.rollback()
        session.close()


def test_chat_auto_selects_enabled_provider_when_assignment_points_to_disabled_provider(
    settings,
) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Auto Chat Fallback Tenant")
        user = _user(tenant.id, "auto-chat-user@example.com")
        session.add_all([tenant, user])
        session.flush()

        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        disabled_lmstudio = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="LM Studio",
                provider_type="lmstudio",
                supports_chat=True,
                supports_embeddings=True,
                owner_user_id=user.id,
            )
        )
        disabled_lmstudio.enabled = False
        groq = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="Groq",
                provider_type="custom",
                supports_chat=True,
                supports_embeddings=False,
                owner_user_id=user.id,
            )
        )
        groq.is_local = False
        groq.auth_mode = "api_key"
        groq.api_base_url = "https://api.groq.com/openai/v1"
        groq.default_chat_model = "llama-3.3-70b-versatile"
        groq.priority = 100
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="chat",
                provider_config_id=disabled_lmstudio.id,
                model_name="qwen/qwen3.5-9b",
                enabled=True,
                priority=100,
            )
        )
        session.add(
            ProviderModelCache(
                tenant_id=tenant.id,
                provider_config_id=groq.id,
                model_name="llama-3.3-70b-versatile",
                model_kind="chat",
                display_name="Llama 3.3 70B Versatile",
                context_window=131072,
                capabilities_json={"runtime": "openai-compatible"},
                is_available=True,
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_chat(
            tenant_id=tenant.id,
            actor_user_id=user.id,
        )
        assert selection.candidates[0].provider_config_id == groq.id
        assert selection.candidates[0].provider_type == "custom"
        assert selection.candidates[0].model_name == "llama-3.3-70b-versatile"
        assert selection.candidates[0].source == "env_fallback"
        assert any("disabled-config" in note for note in selection.selection_notes)
        assert any(note.startswith("auto-chat:") for note in selection.selection_notes)
    finally:
        session.rollback()
        session.close()


def test_context_window_falls_back_to_live_discovery_when_cache_missing(
    settings,
    monkeypatch,
) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Context Discovery Tenant")
        session.add(tenant)
        session.flush()

        configs = ProviderConfigsRepository(session)
        provider = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="LM Studio",
                provider_type="lmstudio",
                supports_chat=True,
                supports_embeddings=True,
            )
        )
        provider.default_chat_model = "qwen2.5-14b-instruct"
        session.commit()

        session.add(
            ProviderModelCache(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                model_name="qwen2.5-14b-instruct",
                model_kind="chat",
                display_name="Qwen2.5 14B Instruct",
                context_window=24_576,
                capabilities_json={"runtime": "lmstudio"},
                is_available=True,
            )
        )
        session.commit()

        service = ProviderSelectionService(session, settings)

        class _Discovery:
            def list_models(self) -> list[ProviderModelInfo]:
                return [
                    ProviderModelInfo(
                        name="qwen2.5-14b-instruct",
                        kind="chat",
                        context_window=131072,
                        capabilities={},
                    )
                ]

        with monkeypatch.context() as mp:
            mp.setattr(service.model_cache, "get_model", lambda **_: None)
            mp.setattr(service.configs, "get_by_id", lambda **_: provider)
            mp.setattr(service, "_resolve_secret_value", lambda **_: None)
            mp.setattr(
                service.registry,
                "get_model_discovery_provider_from_config",
                lambda *_, **__: _Discovery(),
            )

            resolved, source = service._resolve_model_context_window(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                model_name="qwen2.5-14b-instruct",
            )
        assert resolved == 131072
        assert source == "live_model"

        refreshed = service.model_cache.get_model(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            model_name="qwen2.5-14b-instruct",
            model_kind="chat",
        )
        assert refreshed is not None
        assert refreshed.context_window == 131072
    finally:
        session.rollback()
        session.close()


def test_embeddings_auto_select_managed_server_provider_before_lmstudio(
    settings,
) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Managed Embedding Priority Tenant")
        session.add(tenant)
        session.flush()

        configs = ProviderConfigsRepository(session)
        managed = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="AverQel Server Embeddings",
                provider_type="sentence-transformers",
                supports_chat=False,
                supports_embeddings=True,
            )
        )
        managed.default_chat_model = None
        managed.default_embedding_model = None
        lmstudio = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="LM Studio",
                provider_type="lmstudio",
                supports_chat=True,
                supports_embeddings=True,
            )
        )
        lmstudio.default_embedding_model = "text-embedding-nomic-embed-text-v1.5"
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_embeddings(
            tenant_id=tenant.id,
            actor_user_id=None,
        )
        assert selection.candidates[0].provider_config_id == managed.id
        assert selection.candidates[0].provider_type == "sentence-transformers"
        assert selection.candidates[0].model_name == settings.embedding_model
    finally:
        session.rollback()
        session.close()


def test_embeddings_auto_fall_back_to_lmstudio_when_managed_provider_disabled(
    settings,
) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("LM Fallback Tenant")
        user = _user(tenant.id, "embedding-fallback-user@example.com")
        session.add_all([tenant, user])
        session.flush()

        configs = ProviderConfigsRepository(session)
        managed = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="AverQel Server Embeddings",
                provider_type="sentence-transformers",
                supports_chat=False,
                supports_embeddings=True,
            )
        )
        managed.enabled = False
        managed.default_chat_model = None
        managed.default_embedding_model = None
        lmstudio = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="LM Studio",
                provider_type="lmstudio",
                supports_chat=True,
                supports_embeddings=True,
                owner_user_id=user.id,
            )
        )
        lmstudio.default_embedding_model = None
        session.add(
            ProviderModelCache(
                tenant_id=tenant.id,
                provider_config_id=lmstudio.id,
                model_name="text-embedding-nomic-embed-text-v1.5",
                model_kind="embedding",
                display_name="Nomic Embed",
                context_window=8192,
                capabilities_json={"runtime": "lmstudio"},
                is_available=True,
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_embeddings(
            tenant_id=tenant.id,
            actor_user_id=user.id,
        )
        assert selection.candidates[0].provider_config_id == lmstudio.id
        assert selection.candidates[0].provider_type == "lmstudio"
        assert (
            selection.candidates[0].model_name == "text-embedding-nomic-embed-text-v1.5"
        )
    finally:
        session.rollback()
        session.close()


def test_missing_capability_is_ignored_without_env_fallback(settings) -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Capability Tenant")
        user = _user(tenant.id, "capability-user@example.com")
        session.add_all([tenant, user])
        session.flush()

        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            _provider(
                tenant_id=tenant.id,
                display_name="Chat Only",
                supports_chat=True,
                supports_embeddings=False,
                owner_user_id=user.id,
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="embeddings",
                provider_config_id=provider.id,
                model_name="bad-embed-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_embeddings(
            tenant_id=tenant.id,
            actor_user_id=user.id,
        )
        assert selection.candidates == []
        assert any(
            "missing-embedding-capability" in note for note in selection.selection_notes
        )
    finally:
        session.rollback()
        session.close()
