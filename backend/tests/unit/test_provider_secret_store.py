from __future__ import annotations

import base64
import json

from app.core.config import Settings
from app.core.ids import generate_uuid7_with_fallback
from app.db.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.models.providers.provider_config import ProviderConfig
from app.services.security.provider_secret_crypto import ProviderSecretCrypto
from app.services.security.provider_secret_service import ProviderSecretService


def _crypto() -> ProviderSecretCrypto:
    settings = Settings(
        provider_secret_active_kid="kid-active",
        provider_secret_keyring_json=json.dumps(
            {"kid-active": base64.urlsafe_b64encode(b"3" * 32).decode("utf-8")}
        ),
    )
    return ProviderSecretCrypto(settings)


def test_provider_secret_store_masks_and_reads_backend_only() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Secret Store Tenant")
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="openai",
            display_name="OpenAI",
            api_base_url="https://api.openai.com/v1",
            auth_mode="api_key",
            enabled=True,
            is_local=False,
            supports_chat=True,
            supports_embeddings=True,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model="gpt-4.1-mini",
            default_embedding_model="text-embedding-3-small",
            timeout_seconds=30,
            priority=10,
            metadata_json={},
        )
        session.add(provider)
        session.flush()

        service = ProviderSecretService(session, crypto=_crypto())
        service.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            secret_value="sk-phase10-secret-7890",
            actor_user_id=None,
        )
        session.commit()

        masked = service.get_masked_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
        )
        assert masked is not None
        assert masked.masked_value == "sk-...7890"

        secret_value = service.get_secret_value(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
        )
        assert secret_value == "sk-phase10-secret-7890"
    finally:
        session.rollback()
        session.close()
