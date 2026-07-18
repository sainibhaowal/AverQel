from __future__ import annotations

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.providers.provider_config import ProviderConfig
from app.models.system.audit_log import AuditLog
from app.repositories.providers.provider_configs import ProviderConfigsRepository
from app.services.providers.selection_service import ProviderSelectionService


def test_provider_selection_records_audit_event(seed_user, settings) -> None:
    seeded = seed_user(
        "Selection Audit Tenant",
        "selection-audit@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    session = get_session_factory()()
    try:
        ProviderConfigsRepository(session).create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="ollama",
                display_name="Audit Provider",
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
                priority=1,
                metadata_json={},
            )
        )
        session.commit()

        selection = ProviderSelectionService(session, settings).resolve_chat(
            tenant_id=seeded.tenant_id,
            actor_user_id=seeded.user_id,
        )
        assert len(selection.candidates) == 1
        assert selection.candidates[0].provider_type == "ollama"
        assert selection.candidates[0].source == "env_fallback"

        rows = (
            session.execute(
                select(AuditLog).where(
                    AuditLog.tenant_id == seeded.tenant_id,
                    AuditLog.action == "provider.selection.resolve",
                )
            )
            .scalars()
            .all()
        )
        assert rows
        assert rows[-1].details["feature_scope"] == "chat"
        assert rows[-1].details["selected_source"] == "env_fallback"
        assert rows[-1].details["selected_provider_type"] == "ollama"
    finally:
        session.rollback()
        session.close()
