from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.ids import generate_uuid7_with_fallback
from app.db.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.providers.models.provider_config import ProviderConfig
from app.providers.services.provider_secret_crypto import ProviderSecretCrypto
from app.providers.services.provider_secret_service import ProviderSecretService

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _crypto() -> ProviderSecretCrypto:
    settings = Settings(
        provider_secret_active_kid="kid-active",
        provider_secret_keyring_json=json.dumps(
            {"kid-active": base64.urlsafe_b64encode(b"2" * 32).decode("utf-8")}
        ),
    )
    return ProviderSecretCrypto(settings)


def test_provider_secret_service_encrypts_masks_rotates_and_revokes() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Tenant Provider Secret Service"
        )
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
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
        session.add(provider)
        session.flush()

        service = ProviderSecretService(session, crypto=_crypto())
        actor_user_id = None
        created = service.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            secret_value="sk-super-secret-1234",
            actor_user_id=actor_user_id,
            expires_at=None,
            metadata_json={"label": "Primary Key"},
        )
        session.commit()

        assert created.secret_ciphertext != b"sk-super-secret-1234"
        assert (
            service.get_secret_value(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
            )
            == "sk-super-secret-1234"
        )

        masked = service.get_masked_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
        )
        assert masked is not None
        assert masked.masked_value == "sk-...1234"

        rotated = service.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            secret_value="sk-new-secret-5678",
            actor_user_id=actor_user_id,
            expires_at=datetime.now(tz=UTC),
            metadata_json={"label": "Rotated Key"},
        )
        session.commit()
        assert rotated.secret_kid == "kid-active"
        assert (
            service.get_secret_value(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
            )
            == "sk-new-secret-5678"
        )

        assert (
            service.revoke_secret(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
                actor_user_id=actor_user_id,
            )
            is True
        )
        session.commit()
        assert (
            service.get_secret_value(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="api_key",
            )
            is None
        )
    finally:
        session.rollback()
        session.close()


def test_provider_secret_service_disconnects_all_provider_tokens() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Tenant OAuth Secret Service"
        )
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="openai-codex-account-link",
            display_name="Connected OpenAI Account",
            api_base_url="https://api.openai.com/v1",
            auth_mode="oauth_pkce",
            enabled=True,
            is_local=False,
            supports_chat=True,
            supports_embeddings=False,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="codex",
            default_embedding_model=None,
            timeout_seconds=45,
            priority=50,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        service = ProviderSecretService(session, crypto=_crypto())
        actor_user_id = None
        service.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="oauth_access_token",
            secret_value="access-token-value",
            actor_user_id=actor_user_id,
        )
        service.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="oauth_refresh_token",
            secret_value="refresh-token-value",
            actor_user_id=actor_user_id,
        )
        session.commit()

        revoked = service.disconnect_provider(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            actor_user_id=actor_user_id,
        )
        session.commit()

        assert revoked == 2
        assert (
            service.get_masked_secret(
                tenant_id=tenant.id,
                provider_config_id=provider.id,
                secret_type="oauth_access_token",
            )
            is None
        )
    finally:
        session.rollback()
        session.close()
