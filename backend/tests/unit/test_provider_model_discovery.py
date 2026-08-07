from __future__ import annotations

from app.auth.models.tenant import Tenant
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory
from app.providers.models.provider_config import ProviderConfig
from app.providers.services.lmstudio_provider import LMStudioProvider
from app.providers.services.provider_models_service import ProviderModelsService
from app.providers.services.registry import ProviderRegistry
from app.providers.services.types import ProviderModelInfo


def test_lmstudio_keeps_quantized_model_keys_distinct() -> None:
    q4 = {
        "key": "gemma-4-e4b-it@q4_k_m",
        "display_name": "Gemma 4 E4B Instruct",
    }
    q6 = {
        "key": "gemma-4-e4b-it@q6_k",
        "display_name": "Gemma 4 E4B Instruct",
    }

    q4_info = LMStudioProvider()._build_model_info(
        item=q4, name="gemma-4-e4b-it@q4_k_m", kind="chat"
    )
    q6_info = LMStudioProvider()._build_model_info(item=q6, name="gemma-4-e4b-it@q6_k", kind="chat")

    assert q4_info.name != q6_info.name
    assert q4_info.display_name == q6_info.display_name == "Gemma 4 E4B Instruct"
    assert q4_info.capabilities["quantization"] == "Q4_K_M"
    assert LMStudioProvider._extract_model_name(q4) == "gemma-4-e4b-it@q4_k_m"


def test_provider_model_discovery_refreshes_chat_and_embedding_models(
    settings, monkeypatch
) -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Discovery Tenant")
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="lmstudio",
            display_name="LM Studio",
            api_base_url="http://localhost:1234/v1",
            auth_mode="local_no_key",
            enabled=True,
            is_local=True,
            supports_chat=True,
            supports_embeddings=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="chat-model",
            default_embedding_model="embed-model",
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        class FakeDiscovery:
            def list_models(self):
                return [
                    ProviderModelInfo(
                        name="chat-model",
                        kind="chat",
                        capabilities={"runtime": "lmstudio", "supports_chat": True},
                    ),
                    # Discovery endpoints may return duplicate entries. The
                    # cache should persist one row per name and kind.
                    ProviderModelInfo(
                        name="chat-model",
                        kind="chat",
                        capabilities={"runtime": "lmstudio", "supports_chat": True},
                    ),
                ]

            def list_embedding_models(self):
                return [
                    ProviderModelInfo(
                        name="embed-model",
                        kind="embedding",
                        capabilities={
                            "runtime": "lmstudio",
                            "supports_embeddings": True,
                        },
                    )
                ]

        monkeypatch.setattr(
            ProviderRegistry,
            "get_model_discovery_provider_from_config",
            lambda self, provider_config, api_key=None: FakeDiscovery(),
        )

        service = ProviderModelsService(session, ProviderRegistry(settings))
        rows = service.refresh_models(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=None,
        )
        assert {row.model_name for row in rows} == {"chat-model", "embed-model"}
        assert {row.model_kind for row in rows} == {"chat", "embedding"}
        assert len(rows) == 2
    finally:
        session.rollback()
        session.close()


def test_provider_model_refresh_does_not_auto_select_embedding_default(
    settings, monkeypatch
) -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="No Auto Embedding Default")
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="lmstudio",
            display_name="LM Studio",
            api_base_url="http://localhost:1234/v1",
            auth_mode="local_no_key",
            enabled=True,
            is_local=True,
            supports_chat=True,
            supports_embeddings=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="chat-model",
            default_embedding_model=None,
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        class FakeDiscovery:
            def list_models(self):
                return [
                    ProviderModelInfo(
                        name="chat-model",
                        kind="chat",
                        capabilities={"runtime": "lmstudio", "supports_chat": True},
                    )
                ]

            def list_embedding_models(self):
                return [
                    ProviderModelInfo(
                        name="embed-model",
                        kind="embedding",
                        capabilities={
                            "runtime": "lmstudio",
                            "supports_embeddings": True,
                        },
                    )
                ]

        monkeypatch.setattr(
            ProviderRegistry,
            "get_model_discovery_provider_from_config",
            lambda self, provider_config, api_key=None: FakeDiscovery(),
        )

        service = ProviderModelsService(session, ProviderRegistry(settings))
        service.refresh_models(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=None,
        )
        session.refresh(provider)
        assert provider.default_embedding_model is None
    finally:
        session.rollback()
        session.close()


def test_sentence_transformers_refresh_uses_static_embedding_dimension(
    settings, monkeypatch
) -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Sentence Transformers Tenant")
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="sentence-transformers",
            display_name="AverQel Server Embeddings",
            api_base_url=None,
            auth_mode="none",
            enabled=True,
            is_local=False,
            supports_chat=False,
            supports_embeddings=True,
            supports_reranking=False,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model=None,
            default_embedding_model="BAAI/bge-small-en-v1.5",
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        monkeypatch.setattr(
            ProviderModelsService,
            "_detect_embedding_dimension",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("dynamic embedding probe should not run")
            ),
        )

        service = ProviderModelsService(session, ProviderRegistry(settings))
        rows = service.refresh_models(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=None,
        )

        embedding_row = next(row for row in rows if row.model_kind == "embedding")
        assert embedding_row.capabilities_json["embedding_dimension"] == 384
    finally:
        session.rollback()
        session.close()


def test_provider_model_discovery_marks_reasoning_capability(settings, monkeypatch) -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Reasoning Tenant")
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="lmstudio",
            display_name="LM Studio",
            api_base_url="http://localhost:1234/v1",
            auth_mode="local_no_key",
            enabled=True,
            is_local=True,
            supports_chat=True,
            supports_embeddings=False,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="nvidia/nemotron-3-nano-4b",
            default_embedding_model=None,
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        class FakeDiscovery:
            def list_models(self):
                return [
                    ProviderModelInfo(
                        name="nvidia/nemotron-3-nano-4b",
                        kind="chat",
                        capabilities={"runtime": "lmstudio", "supports_chat": True},
                    )
                ]

            def list_embedding_models(self):
                return []

        monkeypatch.setattr(
            ProviderRegistry,
            "get_model_discovery_provider_from_config",
            lambda self, provider_config, api_key=None: FakeDiscovery(),
        )
        monkeypatch.setattr(
            ProviderModelsService,
            "_is_chat_model_usable",
            lambda self, provider, api_key, model_name: True,
        )

        service = ProviderModelsService(session, ProviderRegistry(settings))
        rows = service.refresh_models(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=None,
        )
        assert rows[0].capabilities_json["supports_reasoning"] is True
        assert rows[0].capabilities_json["reasoning_visibility"] == "provider_exposed"
        assert rows[0].capabilities_json["supports_thinking_toggle"] is True
        assert "enable_thinking_true" in rows[0].capabilities_json["request_controls_on"]
        assert "enable_thinking_false" in rows[0].capabilities_json["request_controls_off"]
    finally:
        session.rollback()
        session.close()
