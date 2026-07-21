from __future__ import annotations

from app.core.ids import generate_uuid7_with_fallback
from app.auth.security import hash_password
from app.db.session import get_session_factory
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.services.selection_service import ProviderSelectionService


def test_provider_selection_prefers_workspace_then_tenant_then_env(settings) -> None:
    session = get_session_factory()()
    try:
        tenant = Tenant(
            id=generate_uuid7_with_fallback(), name="Selection Order Tenant"
        )
        workspace_id = generate_uuid7_with_fallback()
        session.add(tenant)
        session.flush()
        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant.id,
            email="selection-order@example.com",
            collection_code="SELORDER",
            password_hash=hash_password("StrongPass!1234"),
            is_active=True,
        )
        session.add(user)
        session.flush()

        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        tenant_provider = configs.create(
            ProviderConfig(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Tenant Chat",
                api_base_url="https://tenant.example/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="tenant-model",
                default_embedding_model=None,
                timeout_seconds=30,
                priority=1,
                metadata_json={},
            )
        )
        workspace_provider = configs.create(
            ProviderConfig(
                tenant_id=tenant.id,
                workspace_id=workspace_id,
                owner_user_id=user.id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Workspace Chat",
                api_base_url="https://workspace.example/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="workspace-model",
                default_embedding_model=None,
                timeout_seconds=30,
                priority=1,
                metadata_json={},
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=None,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="chat",
                provider_config_id=tenant_provider.id,
                model_name="tenant-model",
                enabled=True,
                priority=1,
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant.id,
                workspace_id=workspace_id,
                owner_user_id=user.id,
                visibility_scope="user",
                feature_scope="chat",
                provider_config_id=workspace_provider.id,
                model_name="workspace-model",
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
        assert selection.candidates[0].provider_config_id == workspace_provider.id
        assert selection.candidates[0].source == "workspace"
        assert selection.candidates[0].model_name == "workspace-model"
    finally:
        session.rollback()
        session.close()
