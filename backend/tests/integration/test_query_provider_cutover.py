from __future__ import annotations

from typing import cast

from sqlalchemy import select

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.providers.provider_assignment import ProviderAssignment
from app.models.providers.provider_config import ProviderConfig
from app.models.providers.provider_health_check import ProviderHealthCheck
from app.models.query.message import Message
from app.repositories.providers.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.repositories.providers.provider_configs import ProviderConfigsRepository
from app.repositories.providers.provider_health_checks import (
    ProviderHealthChecksRepository,
)
from app.schemas.query.structured_response import StructuredAnswerResponse
from app.services.providers.openai_compatible import OpenAICompatibleProvider
from app.services.query.query_service import QueryService


def test_query_cutover_prefers_assigned_provider_and_records_metadata(
    seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Phase7 Query Tenant",
        "phase7-query@example.com",
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
                display_name="Assigned Chat Provider",
                api_base_url="https://query-cutover.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="chat-default",
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
                model_name="chat-assigned-model",
                enabled=True,
                priority=1,
            )
        )
        session.commit()

        def _fake_generate(self, request):  # type: ignore[no-untyped-def]
            return type(
                "Response",
                (),
                {
                    "content": '{"detailed_analysis":"cutover:'
                    + request.model
                    + "@"
                    + request.base_url
                    + '"}',
                    "usage": {},
                },
            )()

        monkeypatch.setattr(OpenAICompatibleProvider, "generate", _fake_generate)

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="phase7-query-token",
        )
        result = service.execute(
            auth=auth,
            query_text="Compare the providers",
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
            == "cutover:chat-assigned-model@https://query-cutover.test/v1"
        )

        assistant = (
            session.execute(
                select(Message)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc(), Message.id.desc())
            )
            .scalars()
            .first()
        )
        assert assistant is not None
        assert assistant.metadata_json["provider"] == {
            "type": "openai",
            "model": "chat-assigned-model",
            "source": "tenant",
            "fallback_used": False,
        }
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()


def test_query_cutover_uses_fallback_assignment_when_primary_is_unhealthy(
    seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Phase7 Query Fallback Tenant",
        "phase7-query-fallback@example.com",
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
        health_checks = ProviderHealthChecksRepository(session)

        primary = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Primary Chat",
                api_base_url="https://query-primary.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="primary-model",
                default_embedding_model=None,
                timeout_seconds=30,
                priority=1,
                metadata_json={},
            )
        )
        fallback = configs.create(
            ProviderConfig(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                provider_type="openai",
                display_name="Fallback Chat",
                api_base_url="https://query-fallback.test/v1",
                auth_mode="none",
                enabled=True,
                is_local=False,
                supports_chat=True,
                supports_embeddings=False,
                supports_model_listing=True,
                supports_model_install=False,
                default_chat_model="fallback-model",
                default_embedding_model=None,
                timeout_seconds=30,
                priority=2,
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
                provider_config_id=primary.id,
                model_name="primary-model",
                enabled=True,
                priority=1,
            )
        )
        assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=seeded.tenant_id,
                workspace_id=None,
                owner_user_id=seeded.user_id,
                visibility_scope="user",
                feature_scope="fallback_chat",
                provider_config_id=fallback.id,
                model_name="fallback-model",
                enabled=True,
                priority=1,
            )
        )
        health_checks.record_check(
            ProviderHealthCheck(
                tenant_id=seeded.tenant_id,
                provider_config_id=primary.id,
                status="unhealthy",
                latency_ms=2500,
                http_status=503,
                error_code="PROVIDER_TEST_FAILED",
                error_message_redacted="provider unavailable",
                metadata_json={},
            )
        )
        session.commit()

        def _fake_generate(self, request):  # type: ignore[no-untyped-def]
            return type(
                "Response",
                (),
                {
                    "content": '{"detailed_analysis":"fallback:'
                    + request.model
                    + "@"
                    + request.base_url
                    + '"}',
                    "usage": {},
                },
            )()

        monkeypatch.setattr(OpenAICompatibleProvider, "generate", _fake_generate)

        service = QueryService(session, get_settings())
        auth = AuthContext(
            user_id=seeded.user_id,
            tenant_id=seeded.tenant_id,
            roles=frozenset({"admin"}),
            token_id="phase7-query-fallback-token",
        )
        result = service.execute(
            auth=auth,
            query_text="How should we route fallback?",
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
            == "fallback:fallback-model@https://query-fallback.test/v1"
        )

        assistant = (
            session.execute(
                select(Message)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc(), Message.id.desc())
            )
            .scalars()
            .first()
        )
        assert assistant is not None
        assert assistant.metadata_json["provider"] == {
            "type": "openai",
            "model": "fallback-model",
            "source": "tenant_fallback",
            "fallback_used": False,
        }
    finally:
        session.rollback()
        session.close()
        get_settings.cache_clear()
