from __future__ import annotations

import secrets
from datetime import datetime, timezone

from app.core.ids import generate_uuid7_with_fallback
from app.auth.security import hash_password
from app.db.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.models.provider_health_check import ProviderHealthCheck
from app.providers.models.provider_model_cache import ProviderModelCache
from app.providers.models.provider_secret import ProviderSecret
from app.providers.models.provider_usage_record import ProviderUsageRecord
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.repositories.provider_health_checks import (
    ProviderHealthChecksRepository,
)
from app.providers.repositories.provider_model_cache import ProviderModelCacheRepository
from app.providers.repositories.provider_secrets import ProviderSecretsRepository
from app.providers.repositories.provider_usage_records import (
    ProviderUsageRecordsRepository,
)

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _tenant(name: str) -> Tenant:
    return Tenant(id=generate_uuid7_with_fallback(), name=name)


def _user(*, tenant_id) -> User:
    return User(
        id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        email=f"{generate_uuid7_with_fallback()}@example.com",
        collection_code=secrets.token_hex(4).upper(),
        password_hash=hash_password("StrongPass!1234"),
        is_active=True,
    )


def test_provider_config_repository_is_tenant_scoped() -> None:
    session = get_session_factory()()
    try:
        tenant_a = _tenant("Tenant A")
        tenant_b = _tenant("Tenant B")
        session.add_all([tenant_a, tenant_b])
        session.flush()
        user_a = _user(tenant_id=tenant_a.id)
        user_b = _user(tenant_id=tenant_b.id)
        session.add_all([user_a, user_b])
        session.flush()

        repo = ProviderConfigsRepository(session)
        config_a = repo.create(
            ProviderConfig(
                tenant_id=tenant_a.id,
                workspace_id=None,
                owner_user_id=user_a.id,
                visibility_scope="user",
                provider_type="ollama",
                display_name="Local Ollama",
                api_base_url="http://localhost:11434",
                auth_mode="local_no_key",
                enabled=True,
                is_local=True,
                supports_chat=True,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=True,
                default_chat_model="llama3",
                default_embedding_model="nomic-embed-text",
                timeout_seconds=30,
                priority=10,
                metadata_json={"preset": "ollama"},
            )
        )
        repo.create(
            ProviderConfig(
                tenant_id=tenant_b.id,
                workspace_id=None,
                owner_user_id=user_b.id,
                visibility_scope="user",
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
                default_chat_model="default",
                default_embedding_model=None,
                timeout_seconds=30,
                priority=20,
                metadata_json={"preset": "lmstudio"},
            )
        )
        session.commit()

        assert (
            repo.get_by_id(tenant_id=tenant_a.id, provider_config_id=config_a.id)
            is not None
        )
        assert (
            repo.get_by_id(tenant_id=tenant_b.id, provider_config_id=config_a.id)
            is None
        )
        listed = repo.list_by_tenant(tenant_id=tenant_a.id, owner_user_id=user_a.id)
        assert [item.display_name for item in listed] == ["Local Ollama"]
    finally:
        session.rollback()
        session.close()


def test_provider_secret_rotation_and_revoke() -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Tenant Secrets")
        session.add(tenant)
        session.flush()

        config_repo = ProviderConfigsRepository(session)
        secret_repo = ProviderSecretsRepository(session)
        provider = config_repo.create(
            ProviderConfig(
                tenant_id=tenant.id,
                workspace_id=None,
                provider_type="openai-compatible",
                display_name="OpenAI-Compatible",
                api_base_url="http://localhost:4000/v1",
                auth_mode="api_key",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="gpt-4o-mini",
                default_embedding_model="text-embedding-3-small",
                timeout_seconds=45,
                priority=50,
                metadata_json={},
            )
        )
        secret_repo.create_secret(
            ProviderSecret(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_ciphertext=b"cipher-1",
                secret_nonce=b"nonce-1",
                secret_kid="kid-1",
                secret_type="api_key",
                expires_at=None,
                last_rotated_at=datetime.now(tz=UTC),
                metadata_json={"masked_prefix": "sk-***"},
            )
        )
        rotated = secret_repo.rotate_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            secret_ciphertext=b"cipher-2",
            secret_nonce=b"nonce-2",
            secret_kid="kid-2",
            expires_at=None,
            metadata_json={"masked_prefix": "sk-new"},
        )
        session.commit()
        assert rotated is True

        row = secret_repo.get_by_provider_and_type(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
        )
        assert row is not None
        assert row.secret_ciphertext == b"cipher-2"
        assert row.secret_kid == "kid-2"
        assert secret_repo.list_secret_types_for_provider(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
        ) == ["api_key"]
        assert (
            secret_repo.revoke_secret(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
            )
            is True
        )
        session.commit()
        assert (
            secret_repo.get_by_provider_and_type(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
            )
            is None
        )
    finally:
        session.rollback()
        session.close()


def test_provider_model_cache_assignment_health_and_usage_repositories() -> None:
    session = get_session_factory()()
    try:
        tenant = _tenant("Tenant Runtime")
        session.add(tenant)
        session.flush()
        user = _user(tenant_id=tenant.id)
        session.add(user)
        session.flush()

        config_repo = ProviderConfigsRepository(session)
        cache_repo = ProviderModelCacheRepository(session)
        assignment_repo = ProviderAssignmentsRepository(session)
        health_repo = ProviderHealthChecksRepository(session)
        usage_repo = ProviderUsageRecordsRepository(session)

        provider = config_repo.create(
            ProviderConfig(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                provider_type="ollama",
                display_name="Ollama Runtime",
                api_base_url="http://localhost:11434",
                auth_mode="local_no_key",
                enabled=True,
                is_local=True,
                supports_chat=True,
                supports_embeddings=True,
                supports_model_listing=True,
                supports_model_install=True,
                default_chat_model="llama3",
                default_embedding_model="nomic-embed-text",
                timeout_seconds=30,
                priority=5,
                metadata_json={},
            )
        )

        persisted = cache_repo.upsert_models(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            models=[
                ProviderModelCache(
                    tenant_id=tenant.id,
                    provider_config_id=provider.id,
                    model_name="llama3",
                    model_kind="chat",
                    display_name="Llama 3",
                    context_window=8192,
                    capabilities_json={"streaming": True},
                    is_available=True,
                    last_seen_at=datetime.now(tz=UTC),
                ),
                ProviderModelCache(
                    tenant_id=tenant.id,
                    provider_config_id=provider.id,
                    model_name="nomic-embed-text",
                    model_kind="embedding",
                    display_name="Nomic Embed",
                    context_window=None,
                    capabilities_json={"dimension": 768},
                    is_available=True,
                    last_seen_at=datetime.now(tz=UTC),
                ),
            ],
        )
        assert len(persisted) == 2
        assert (
            len(
                cache_repo.list_models(
                    tenant_id=tenant.id, provider_config_id=provider.id
                )
            )
            == 2
        )
        removed = cache_repo.purge_stale_models(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            seen_names={("llama3", "chat")},
        )
        assert removed == 1

        assignment_repo.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="chat",
                provider_config_id=provider.id,
                model_name="llama3",
                enabled=True,
                priority=1,
            )
        )
        assert (
            assignment_repo.get_active_assignment(
                tenant_id=tenant.id,
                workspace_id=None,
                feature_scope="chat",
                owner_user_id=user.id,
            )
            is not None
        )

        health_repo.record_check(
            ProviderHealthCheck(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                status="healthy",
                latency_ms=123,
                http_status=200,
                error_code=None,
                error_message_redacted=None,
                metadata_json={"source": "test"},
                checked_at=datetime.now(tz=UTC),
            )
        )
        latest = health_repo.get_latest_check(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
        )
        assert latest is not None
        assert latest.status == "healthy"

        usage_repo.create(
            ProviderUsageRecord(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                operation="query_chat",
                model_name="llama3",
                input_tokens=100,
                output_tokens=50,
                cost_estimate=0.0,
            )
        )
        assert (
            len(
                usage_repo.list_by_provider(
                    tenant_id=tenant.id,
                    provider_config_id=provider.id,
                )
            )
            == 1
        )
        session.commit()
    finally:
        session.rollback()
        session.close()
