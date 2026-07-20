from __future__ import annotations

from app.core.ids import generate_uuid7_with_fallback
from app.auth.security import hash_password
from app.db.session import get_session_factory, set_db_tenant_context
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.models.providers.provider_assignment import ProviderAssignment
from app.models.providers.provider_config import ProviderConfig
from app.services.providers.provider_management_service import ProviderManagementService
from tests.conftest import _generate_test_collection_code


def test_provider_management_service_lists_supported_catalog() -> None:
    session = get_session_factory()()
    try:
        service = ProviderManagementService(session)
        catalog = service.list_supported_types()
        provider_types = {item["provider_type"] for item in catalog}
        assert "openai" in provider_types
        assert "groq" in provider_types
        assert "ollama" in provider_types
        assert "opencode-zen" in provider_types
        assert "tavily" in provider_types
    finally:
        session.close()


def test_provider_management_service_accepts_opencode_zen_provider() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Zen Tenant")
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="zen-provider@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        service = ProviderManagementService(session)
        provider = service.create_provider(
            tenant_id=tenant.id,
            workspace_id=None,
            actor_user_id=user.id,
            provider_type="opencode-zen",
            display_name="OpenCode Zen",
            api_base_url="https://opencode.ai/zen/v1",
            auth_mode="api_key",
            enabled=True,
            is_local=False,
            supports_chat=True,
            supports_embeddings=False,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="gpt-5.4",
            default_embedding_model=None,
            timeout_seconds=30,
            priority=10,
            metadata_json={},
            api_key="zen_test_1234567890",
        )
        session.commit()

        assert provider.provider_type == "opencode-zen"
        assert provider.api_base_url == "https://opencode.ai/zen/v1"
        assert provider.owner_user_id == user.id
    finally:
        session.rollback()
        session.close()


def test_provider_management_service_accepts_groq_provider() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Groq Tenant")
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="groq-provider@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        service = ProviderManagementService(session)
        provider = service.create_provider(
            tenant_id=tenant.id,
            workspace_id=None,
            actor_user_id=user.id,
            provider_type="groq",
            display_name="Groq",
            api_base_url="https://api.groq.com/openai/v1",
            auth_mode="api_key",
            enabled=True,
            is_local=False,
            supports_chat=True,
            supports_embeddings=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="llama-3.3-70b-versatile",
            default_embedding_model="text-embedding-3-large",
            timeout_seconds=30,
            priority=10,
            metadata_json={},
            api_key="gsk_test_1234567890",
        )
        session.commit()

        assert provider.provider_type == "groq"
        assert provider.api_base_url == "https://api.groq.com/openai/v1"
        assert provider.owner_user_id == user.id
    finally:
        session.rollback()
        session.close()


def test_enabling_managed_server_embeddings_clears_lmstudio_embedding_default() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Provider Tenant")
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="provider-admin@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        service = ProviderManagementService(session)
        lmstudio = service.create_provider(
            tenant_id=tenant.id,
            workspace_id=None,
            actor_user_id=user.id,
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
            default_chat_model="mistralai/ministral-3-3b",
            default_embedding_model="text-embedding-nomic-embed-text-v1.5",
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        service.create_provider(
            tenant_id=tenant.id,
            workspace_id=None,
            actor_user_id=user.id,
            provider_type="sentence-transformers",
            display_name="AverQel Server Embeddings",
            api_base_url=None,
            auth_mode="none",
            enabled=True,
            is_local=False,
            supports_chat=False,
            supports_embeddings=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model=None,
            default_embedding_model=None,
            timeout_seconds=30,
            priority=1,
            metadata_json={},
        )
        session.commit()

        refreshed = service.get_provider(
            tenant_id=tenant.id, provider_config_id=lmstudio.id
        )
        assert refreshed.default_embedding_model is None
    finally:
        session.rollback()
        session.close()


def test_updating_lmstudio_while_managed_embeddings_enabled_clears_embedding_default() -> (
    None
):
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Provider Update Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="provider-update@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        lmstudio = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=user.id,
            visibility_scope="user",
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
            default_chat_model="qwen/qwen3.5-9b",
            default_embedding_model=None,
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        managed = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
            provider_type="sentence-transformers",
            display_name="AverQel Server Embeddings",
            api_base_url=None,
            auth_mode="none",
            enabled=True,
            is_local=False,
            supports_chat=False,
            supports_embeddings=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model=None,
            default_embedding_model=None,
            timeout_seconds=30,
            priority=1,
            metadata_json={},
        )
        session.add_all([lmstudio, managed])
        session.commit()

        service = ProviderManagementService(session)
        updated = service.update_provider(
            tenant_id=tenant.id,
            provider_config_id=lmstudio.id,
            actor_user_id=user.id,
            values={"default_embedding_model": "text-embedding-nomic-embed-text-v1.5"},
        )
        session.commit()

        assert updated.default_embedding_model is None
    finally:
        session.rollback()
        session.close()


def test_delete_provider_removes_active_assignments_when_no_replacement_exists() -> (
    None
):
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Provider Delete Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="provider-delete@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=user.id,
            visibility_scope="user",
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
            default_chat_model="qwen/qwen3.5-9b",
            default_embedding_model=None,
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        assignment = ProviderAssignment(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=user.id,
            visibility_scope="user",
            feature_scope="chat",
            provider_config_id=provider.id,
            model_name="qwen/qwen3.5-9b",
            enabled=True,
            priority=100,
        )
        session.add(assignment)
        session.commit()

        service = ProviderManagementService(session)
        status = service.delete_or_disable_provider(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=user.id,
        )
        session.commit()

        assert status == "deleted"
        assert (
            service.configs.get_by_id(
                tenant_id=tenant.id, provider_config_id=provider.id
            )
            is None
        )
        assert (
            service.assignments.get_by_id(
                tenant_id=tenant.id, assignment_id=assignment.id
            )
            is None
        )
    finally:
        session.rollback()
        session.close()


def test_delete_managed_sentence_transformer_provider_disables_instead_of_recreating() -> (
    None
):
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Managed Provider Delete Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="managed-provider-delete@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
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
            default_reranker_model=None,
            timeout_seconds=30,
            priority=100,
            metadata_json={"managed_by_averqel": True},
        )
        session.add(provider)
        session.flush()

        assignment = ProviderAssignment(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
            feature_scope="embeddings",
            provider_config_id=provider.id,
            model_name="BAAI/bge-small-en-v1.5",
            enabled=True,
            priority=100,
        )
        session.add(assignment)
        session.commit()

        service = ProviderManagementService(session)
        status = service.delete_or_disable_provider(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=user.id,
        )
        session.commit()

        assert status == "disabled"
        refreshed = service.get_provider(
            tenant_id=tenant.id, provider_config_id=provider.id
        )
        assert refreshed.enabled is False
        assert (
            service.assignments.get_by_id(
                tenant_id=tenant.id, assignment_id=assignment.id
            )
            is None
        )

        listed = service.list_providers(tenant_id=tenant.id)
        assert (
            sum(1 for row in listed if row.display_name == "AverQel Server Embeddings")
            == 1
        )
        assert (
            next(
                row for row in listed if row.display_name == "AverQel Server Embeddings"
            ).enabled
            is False
        )
    finally:
        session.rollback()
        session.close()


def test_disconnect_provider_disables_runtime_and_revokes_tokens() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Disconnect Provider Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="disconnect-provider@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=user.id,
            visibility_scope="user",
            provider_type="opencode-zen",
            display_name="OpenCode Zen",
            api_base_url="https://opencode.ai/zen/v1",
            auth_mode="api_key",
            enabled=True,
            is_local=False,
            supports_chat=True,
            supports_embeddings=False,
            supports_reranking=False,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="gpt-4.1",
            default_embedding_model=None,
            default_reranker_model=None,
            timeout_seconds=30,
            priority=100,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        service = ProviderManagementService(session)
        service.secrets.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            secret_value="zen-api-key-123",
            actor_user_id=user.id,
        )
        session.commit()

        revoked = service.disconnect_provider(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=user.id,
        )
        session.commit()

        refreshed = service.get_provider(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=user.id,
        )
        assert revoked == 1
        assert refreshed.enabled is False
        assert (
            service.secrets.get_secret_value(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
            )
            is None
        )
    finally:
        session.rollback()
        session.close()


def test_list_providers_collapses_duplicate_managed_sentence_transformer_rows() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Managed Provider Dedupe Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)

        session.add_all(
            [
                ProviderConfig(
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
                    default_reranker_model=None,
                    timeout_seconds=30,
                    priority=100,
                    metadata_json={"managed_by_averqel": True},
                ),
                ProviderConfig(
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
                    default_reranker_model=None,
                    timeout_seconds=30,
                    priority=100,
                    metadata_json={"managed_by_averqel": True},
                ),
                ProviderConfig(
                    tenant_id=tenant.id,
                    workspace_id=None,
                    provider_type="sentence-transformers",
                    display_name="AverQel Server ReRanker",
                    api_base_url=None,
                    auth_mode="none",
                    enabled=True,
                    is_local=False,
                    supports_chat=False,
                    supports_embeddings=False,
                    supports_reranking=True,
                    supports_model_listing=True,
                    supports_model_install=False,
                    default_chat_model=None,
                    default_embedding_model=None,
                    default_reranker_model="BAAI/bge-reranker-v2-m3",
                    timeout_seconds=30,
                    priority=100,
                    metadata_json={"managed_by_averqel": True},
                ),
                ProviderConfig(
                    tenant_id=tenant.id,
                    workspace_id=None,
                    provider_type="sentence-transformers",
                    display_name="AverQel Server ReRanker",
                    api_base_url=None,
                    auth_mode="none",
                    enabled=True,
                    is_local=False,
                    supports_chat=False,
                    supports_embeddings=False,
                    supports_reranking=True,
                    supports_model_listing=True,
                    supports_model_install=False,
                    default_chat_model=None,
                    default_embedding_model=None,
                    default_reranker_model="BAAI/bge-reranker-v2-m3",
                    timeout_seconds=30,
                    priority=100,
                    metadata_json={"managed_by_averqel": True},
                ),
            ]
        )
        session.commit()

        service = ProviderManagementService(session)
        rows = service.list_providers(tenant_id=tenant.id)

        assert (
            len(
                [row for row in rows if row.display_name == "AverQel Server Embeddings"]
            )
            == 1
        )
        assert (
            len([row for row in rows if row.display_name == "AverQel Server ReRanker"])
            == 1
        )
        assert len(rows) == 2
    finally:
        session.rollback()
        session.close()


def test_update_split_sentence_transformer_provider_allows_default_model_changes() -> (
    None
):
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Managed Provider Update Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="managed-provider-update@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        embeddings = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
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
            default_reranker_model=None,
            timeout_seconds=30,
            priority=100,
            metadata_json={"managed_by_averqel": True},
        )
        reranker = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
            provider_type="sentence-transformers",
            display_name="AverQel Server ReRanker",
            api_base_url=None,
            auth_mode="none",
            enabled=True,
            is_local=False,
            supports_chat=False,
            supports_embeddings=False,
            supports_reranking=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model=None,
            default_embedding_model=None,
            default_reranker_model="BAAI/bge-reranker-v2-m3",
            timeout_seconds=30,
            priority=100,
            metadata_json={"managed_by_averqel": True},
        )
        session.add_all([embeddings, reranker])
        session.commit()

        service = ProviderManagementService(session)
        updated_embeddings = service.update_provider(
            tenant_id=tenant.id,
            provider_config_id=embeddings.id,
            actor_user_id=user.id,
            values={"default_embedding_model": "intfloat/multilingual-e5-small"},
        )
        updated_reranker = service.update_provider(
            tenant_id=tenant.id,
            provider_config_id=reranker.id,
            actor_user_id=user.id,
            values={"default_reranker_model": "cross-encoder/ms-marco-MiniLM-L-12-v2"},
        )

        assert (
            updated_embeddings.default_embedding_model
            == "intfloat/multilingual-e5-small"
        )
        assert (
            updated_reranker.default_reranker_model
            == "cross-encoder/ms-marco-MiniLM-L-12-v2"
        )
    finally:
        session.rollback()
        session.close()


def test_sentence_transformers_embedding_assignment_uses_static_dimension(
    monkeypatch,
) -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Provider Assignment Tenant"
        )
        session.add(tenant)
        session.flush()
        set_db_tenant_context(session, tenant.id)
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="provider-assignment@example.com",
            collection_code=_generate_test_collection_code(),
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
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
            ProviderManagementService,
            "_probe_embedding_dimension",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("dynamic embedding probe should not run")
            ),
        )

        service = ProviderManagementService(session)
        assignment = service.create_assignment(
            tenant_id=tenant.id,
            actor_user_id=user.id,
            workspace_id=None,
            feature_scope="embeddings",
            provider_config_id=provider.id,
            model_name="BAAI/bge-small-en-v1.5",
            enabled=True,
            priority=100,
        )

        assert assignment.model_name == "BAAI/bge-small-en-v1.5"
    finally:
        session.rollback()
        session.close()
