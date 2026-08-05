from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.platform.database.session import get_session_factory
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.query.schemas.structured_response import StructuredAnswerResponse
from app.query.services.query_service import QueryService


def test_query_service_uses_selected_provider_assignment(seed_user, monkeypatch) -> None:
    seeded = seed_user(
        "Provider Query Tenant",
        "provider-query@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "disabled")
    get_settings.cache_clear()

    session = get_session_factory()()
    try:
        configs = ProviderConfigsRepository(session)
        assignments = ProviderAssignmentsRepository(session)
        provider = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Selected OpenAI",
                api_base_url="https://unit.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="structured-model",
                default_embedding_model=None,
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
                feature_scope="chat",
                provider_config_id=provider.id,
                model_name="assigned-chat-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        def _fake_generate(self, request):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                content='{"detailed_analysis":"selected:'
                + request.model
                + "@"
                + request.base_url
                + '"}',
                usage={},
            )

        monkeypatch.setattr(OpenAICompatibleProvider, "generate", _fake_generate)

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="test-token",
        )
        result = service.execute(
            auth=auth,
            query_text="Compare the options",
            top_k=3,
            filters={},
            document_ids=None,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            conversation_id=None,
            search_mode="hybrid",
        )
        assert (
            cast(StructuredAnswerResponse, result.answer).detailed_analysis
            == "selected:assigned-chat-model@https://unit.test/v1"
        )
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()
