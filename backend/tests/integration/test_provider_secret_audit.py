from __future__ import annotations

import base64
import json

from sqlalchemy import select

from app.core.config import Settings
from app.core.ids import generate_uuid7_with_fallback
from app.db.session import get_session_factory
from app.models.auth.tenant import Tenant
from app.models.providers.provider_config import ProviderConfig
from app.models.system.audit_log import AuditLog
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


def test_provider_secret_lifecycle_is_audited() -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(id=generate_uuid7_with_fallback(), name="Tenant Provider Audit")
        session.add(tenant)
        session.flush()

        provider = ProviderConfig(
            tenant_id=tenant.id,
            workspace_id=None,
            provider_type="openai-compatible",
            display_name="Audited Provider",
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
        service.upsert_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            secret_value="sk-audit-secret-1234",
            actor_user_id=actor_user_id,
        )
        service.revoke_secret(
            tenant_id=tenant.id,
            provider_config_id=provider.id,
            secret_type="api_key",
            actor_user_id=actor_user_id,
        )
        session.commit()

        rows = (
            session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == tenant.id,
                    AuditLog.resource_type == "provider_secret",
                )
            )
            .scalars()
            .all()
        )
        actions = {row.action for row in rows}
        assert "provider.secret.create" in actions
        assert "provider.secret.revoke" in actions
        details_dump = json.dumps([row.details for row in rows])
        assert "sk-audit-secret-1234" not in details_dump
    finally:
        session.rollback()
        session.close()
