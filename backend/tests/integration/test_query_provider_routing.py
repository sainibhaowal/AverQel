from __future__ import annotations

from typing import cast

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.providers.provider_assignment import ProviderAssignment
from app.models.providers.provider_config import ProviderConfig
from app.repositories.providers.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.repositories.providers.provider_configs import ProviderConfigsRepository
from app.schemas.query.structured_response import StructuredAnswerResponse
from app.services.providers.openai_compatible import OpenAICompatibleProvider
from app.services.query.query_service import QueryService


def test_query_provider_routing_prefers_assignment(seed_user, monkeypatch) -> None:
    seeded = seed_user(
        "Routing Query Tenant",
        "routing-query@example.com",
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
                display_name="Assigned Query Provider",
                api_base_url="https://routing-query.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="gpt-routing",
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
                model_name="gpt-routing",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        monkeypatch.setattr(
            OpenAICompatibleProvider,
            "generate",
            lambda self, request: type(
                "Response",
                (),
                {
                    "content": '{"detailed_analysis":"route:' + request.model + '"}',
                    "usage": {},
                },
            )(),
        )

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="routing-token",
        )
        result = service.execute(
            auth=auth,
            query_text="Route this query",
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
            == "route:gpt-routing"
        )
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()
