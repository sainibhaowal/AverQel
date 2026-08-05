from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.repositories.provider_health_checks import (
    ProviderHealthChecksRepository,
)
from app.providers.repositories.provider_model_cache import ProviderModelCacheRepository
from app.providers.services.context_window import resolve_verified_context_window
from app.providers.services.provider_secret_service import ProviderSecretService
from app.providers.services.registry import ProviderRegistry
from app.providers.services.types import (
    ProviderSelectionCandidate,
    ProviderSelectionResult,
)
from app.system.services.audit_service import AuditService

DEFAULT_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "cohere": "https://api.cohere.com/v2",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "opencode-zen": "https://opencode.ai/zen/v1",
    "tavily": "https://api.tavily.com",
    "searxng": "http://searxng:8080",
}


@dataclass
class ProviderSelectionService:
    db: Session
    settings: Settings
    assignments: ProviderAssignmentsRepository = field(init=False)
    configs: ProviderConfigsRepository = field(init=False)
    health_checks: ProviderHealthChecksRepository = field(init=False)
    model_cache: ProviderModelCacheRepository = field(init=False)
    registry: ProviderRegistry = field(init=False)
    secrets: ProviderSecretService = field(init=False)
    audit: AuditService = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "assignments", ProviderAssignmentsRepository(self.db))
        object.__setattr__(self, "configs", ProviderConfigsRepository(self.db))
        object.__setattr__(self, "health_checks", ProviderHealthChecksRepository(self.db))
        object.__setattr__(self, "model_cache", ProviderModelCacheRepository(self.db))
        object.__setattr__(self, "registry", ProviderRegistry(self.settings))
        object.__setattr__(self, "secrets", ProviderSecretService(self.db))
        object.__setattr__(self, "audit", AuditService(self.db))

    def resolve_chat(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        allow_live_model_discovery: bool = False,
    ) -> ProviderSelectionResult:
        return self._resolve(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            feature_scope="chat",
            fallback_scope="fallback_chat",
            allow_live_model_discovery=allow_live_model_discovery,
        )

    def resolve_embeddings(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> ProviderSelectionResult:
        return self._resolve(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            feature_scope="embeddings",
            fallback_scope="fallback_embeddings",
        )

    def resolve_reranking(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> ProviderSelectionResult:
        return self._resolve(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            feature_scope="reranking",
            fallback_scope="fallback_reranking",
        )

    def resolve_web_search(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> ProviderSelectionResult:
        return self._resolve(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            feature_scope="web_search",
            fallback_scope="fallback_web_search",
        )

    def _resolve(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        feature_scope: str,
        fallback_scope: str,
        allow_live_model_discovery: bool = False,
    ) -> ProviderSelectionResult:
        notes: list[str] = []
        ordered_assignments: list[
            tuple[
                Literal["workspace", "tenant", "workspace_fallback", "tenant_fallback"],
                ProviderAssignment | None,
            ]
        ] = []

        if workspace_id is not None:
            ordered_assignments.append(
                (
                    "workspace",
                    self.assignments.get_active_assignment(
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        feature_scope=feature_scope,
                        owner_user_id=actor_user_id,
                    ),
                )
            )
        ordered_assignments.append(
            (
                "tenant",
                self.assignments.get_active_assignment(
                    tenant_id=tenant_id,
                    workspace_id=None,
                    feature_scope=feature_scope,
                    owner_user_id=actor_user_id,
                ),
            )
        )
        if workspace_id is not None:
            ordered_assignments.append(
                (
                    "workspace_fallback",
                    self.assignments.get_active_assignment(
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        feature_scope=fallback_scope,
                        owner_user_id=actor_user_id,
                    ),
                )
            )
        ordered_assignments.append(
            (
                "tenant_fallback",
                self.assignments.get_active_assignment(
                    tenant_id=tenant_id,
                    workspace_id=None,
                    feature_scope=fallback_scope,
                    owner_user_id=actor_user_id,
                ),
            )
        )

        candidates: list[ProviderSelectionCandidate] = []
        seen_provider_configs: set[uuid.UUID] = set()

        for source, assignment in ordered_assignments:
            if assignment is None:
                notes.append(f"{source}:{feature_scope}:no-assignment")
                continue
            if assignment.provider_config_id in seen_provider_configs:
                continue
            candidate = self._assignment_to_candidate(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                feature_scope=feature_scope,
                source=source,
                assignment=assignment,
                notes=notes,
                allow_live_model_discovery=allow_live_model_discovery,
            )
            if candidate is None:
                continue
            seen_provider_configs.add(assignment.provider_config_id)
            candidates.append(candidate)

        if feature_scope == "chat" and not candidates:
            self._append_automatic_chat_candidates(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=actor_user_id,
                notes=notes,
                candidates=candidates,
                seen_provider_configs=seen_provider_configs,
                allow_live_model_discovery=allow_live_model_discovery,
            )

        if feature_scope == "embeddings" and not candidates:
            self._append_automatic_embedding_candidates(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=actor_user_id,
                notes=notes,
                candidates=candidates,
                seen_provider_configs=seen_provider_configs,
            )
        if feature_scope == "reranking" and not candidates:
            self._append_automatic_reranking_candidates(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=actor_user_id,
                notes=notes,
                candidates=candidates,
                seen_provider_configs=seen_provider_configs,
            )
        if feature_scope == "web_search" and not candidates:
            self._append_automatic_web_search_candidates(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=actor_user_id,
                notes=notes,
                candidates=candidates,
                seen_provider_configs=seen_provider_configs,
            )
        if feature_scope == "web_search" and not candidates:
            self._append_builtin_web_search_candidate(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                notes=notes,
                candidates=candidates,
            )

        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.selection.resolve",
            resource_type="provider_selection",
            resource_id=str(candidates[0].provider_config_id if candidates else "none"),
            details={
                "feature_scope": feature_scope,
                "workspace_id": str(workspace_id) if workspace_id else "",
                "selected_source": candidates[0].source if candidates else "none",
                "selected_provider_type": (candidates[0].provider_type if candidates else "none"),
                "selected_model_name": candidates[0].model_name if candidates else "",
            },
        )
        return ProviderSelectionResult(
            feature_scope=feature_scope,
            candidates=candidates,
            selection_notes=notes,
        )

    def _append_automatic_chat_candidates(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None,
        notes: list[str],
        candidates: list[ProviderSelectionCandidate],
        seen_provider_configs: set[uuid.UUID],
        allow_live_model_discovery: bool = False,
    ) -> None:
        scoped_providers = sorted(
            self._providers_in_resolution_scope(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
            ),
            key=lambda provider: (
                -provider.priority,
                str(provider.updated_at),
                str(provider.id),
            ),
        )
        for provider in scoped_providers:
            if (
                not provider.enabled
                or not provider.supports_chat
                or provider.id in seen_provider_configs
            ):
                continue
            model_name = provider.default_chat_model
            if not model_name:
                notes.append(f"auto-chat:missing-model:{provider.id}")
                continue
            resolved_model_name = self._resolve_usable_chat_model_name(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                preferred_model_name=model_name,
                fallback_model_name=provider.default_chat_model,
            )
            if not resolved_model_name:
                notes.append(f"auto-chat:unavailable-model:{provider.id}:{model_name}")
                continue
            latest_health = self.health_checks.get_latest_check(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
            )
            if latest_health is not None and latest_health.status == "unhealthy":
                notes.append(f"auto-chat:health-reject:{provider.id}")
                continue
            api_key = self._resolve_secret_value(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                auth_mode=provider.auth_mode,
            )
            context_window, context_window_source = self._resolve_model_context_window(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                model_name=resolved_model_name,
                allow_live_model_discovery=allow_live_model_discovery,
            )
            candidates.append(
                ProviderSelectionCandidate(
                    provider_type=provider.provider_type,
                    model_name=resolved_model_name,
                    feature_scope="chat",
                    source="env_fallback",
                    provider_config_id=provider.id,
                    tenant_id=tenant_id,
                    workspace_id=provider.workspace_id,
                    base_url=self._dockerize_url(
                        provider.api_base_url
                        or DEFAULT_PROVIDER_BASE_URLS.get(provider.provider_type)
                    ),
                    api_key=api_key,
                    auth_mode=provider.auth_mode,
                    context_window=context_window,
                    context_window_source=context_window_source,
                    priority=provider.priority,
                    health_status=(latest_health.status if latest_health is not None else None),
                    metadata={
                        "display_name": provider.display_name,
                        "auto_selected": True,
                        "is_local": bool(provider.is_local),
                    },
                )
            )
            notes.append(f"auto-chat:{provider.id}")
            return

    def _append_automatic_embedding_candidates(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None,
        notes: list[str],
        candidates: list[ProviderSelectionCandidate],
        seen_provider_configs: set[uuid.UUID],
    ) -> None:
        scoped_providers = self._providers_in_resolution_scope(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
        )
        managed_provider = next(
            (
                provider
                for provider in scoped_providers
                if provider.enabled
                and provider.supports_embeddings
                and provider.provider_type == "sentence-transformers"
                and provider.id not in seen_provider_configs
            ),
            None,
        )
        if managed_provider is not None:
            candidate = self._provider_to_auto_embedding_candidate(
                tenant_id=tenant_id,
                provider=managed_provider,
                source="env_fallback",
                model_name=managed_provider.default_embedding_model
                or self.settings.embedding_model,
                notes=notes,
            )
            if candidate is not None:
                candidates.append(candidate)
                seen_provider_configs.add(managed_provider.id)
                notes.append(f"auto-managed-embeddings:{managed_provider.id}")
                return

        lmstudio_provider = next(
            (
                provider
                for provider in scoped_providers
                if provider.enabled
                and provider.supports_embeddings
                and provider.provider_type == "lmstudio"
                and provider.id not in seen_provider_configs
            ),
            None,
        )
        if lmstudio_provider is None:
            return
        model_name = self._resolve_auto_lmstudio_embedding_model(
            tenant_id=tenant_id,
            provider_config_id=lmstudio_provider.id,
            configured_default=lmstudio_provider.default_embedding_model,
        )
        if not model_name:
            notes.append(f"auto-lmstudio:no-embedding-model:{lmstudio_provider.id}")
            return
        candidate = self._provider_to_auto_embedding_candidate(
            tenant_id=tenant_id,
            provider=lmstudio_provider,
            source="env_fallback",
            model_name=model_name,
            notes=notes,
        )
        if candidate is not None:
            candidates.append(candidate)
            notes.append(f"auto-lmstudio-embeddings:{lmstudio_provider.id}")

    def _append_automatic_reranking_candidates(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None,
        notes: list[str],
        candidates: list[ProviderSelectionCandidate],
        seen_provider_configs: set[uuid.UUID],
    ) -> None:
        scoped_providers = sorted(
            self._providers_in_resolution_scope(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
            ),
            key=lambda provider: (
                provider.provider_type != "sentence-transformers",
                -provider.priority,
                str(provider.updated_at),
                str(provider.id),
            ),
        )
        for provider in scoped_providers:
            if (
                not provider.enabled
                or not provider.supports_reranking
                or provider.id in seen_provider_configs
            ):
                continue
            model_name = provider.default_reranker_model or self.settings.reranking_model
            latest_health = self.health_checks.get_latest_check(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
            )
            if latest_health is not None and latest_health.status == "unhealthy":
                notes.append(f"auto-reranking:health-reject:{provider.id}")
                continue
            api_key = self._resolve_secret_value(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                auth_mode=provider.auth_mode,
            )
            candidates.append(
                ProviderSelectionCandidate(
                    provider_type=provider.provider_type,
                    model_name=model_name,
                    feature_scope="reranking",
                    source="env_fallback",
                    provider_config_id=provider.id,
                    tenant_id=tenant_id,
                    workspace_id=provider.workspace_id,
                    base_url=self._dockerize_url(
                        provider.api_base_url
                        or DEFAULT_PROVIDER_BASE_URLS.get(provider.provider_type)
                    ),
                    api_key=api_key,
                    auth_mode=provider.auth_mode,
                    priority=provider.priority,
                    health_status=(latest_health.status if latest_health is not None else None),
                    metadata={
                        "display_name": provider.display_name,
                        "auto_selected": True,
                        "is_local": bool(provider.is_local),
                    },
                )
            )
            notes.append(f"auto-reranking:{provider.id}")
            return

    def _append_automatic_web_search_candidates(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None,
        notes: list[str],
        candidates: list[ProviderSelectionCandidate],
        seen_provider_configs: set[uuid.UUID],
    ) -> None:
        scoped_providers = sorted(
            self._providers_in_resolution_scope(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
            ),
            key=lambda provider: (
                -provider.priority,
                str(provider.updated_at),
                str(provider.id),
            ),
        )
        for provider in scoped_providers:
            if (
                not provider.enabled
                or provider.provider_type not in {"tavily", "searxng"}
                or provider.id in seen_provider_configs
            ):
                continue
            latest_health = self.health_checks.get_latest_check(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
            )
            if latest_health is not None and latest_health.status == "unhealthy":
                notes.append(f"auto-web-search:health-reject:{provider.id}")
                continue
            api_key = self._resolve_secret_value(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                auth_mode=provider.auth_mode,
            )
            candidates.append(
                ProviderSelectionCandidate(
                    provider_type=provider.provider_type,
                    model_name="web-search",
                    feature_scope="web_search",
                    source="env_fallback",
                    provider_config_id=provider.id,
                    tenant_id=tenant_id,
                    workspace_id=provider.workspace_id,
                    base_url=self._dockerize_url(
                        provider.api_base_url
                        or DEFAULT_PROVIDER_BASE_URLS.get(provider.provider_type)
                    ),
                    api_key=api_key,
                    auth_mode=provider.auth_mode,
                    priority=provider.priority,
                    health_status=(latest_health.status if latest_health is not None else None),
                    metadata={
                        **dict(provider.metadata_json or {}),
                        "display_name": provider.display_name,
                        "auto_selected": True,
                        "is_local": bool(provider.is_local),
                    },
                )
            )
            seen_provider_configs.add(provider.id)
            notes.append(f"auto-web-search:{provider.id}")
            return

    def _append_builtin_web_search_candidate(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        notes: list[str],
        candidates: list[ProviderSelectionCandidate],
    ) -> None:
        """Expose the isolated deployment SearXNG service without a DB provider row."""
        endpoint = str(
            getattr(self.settings, "searxng_base_url", "http://searxng:8080") or ""
        ).strip()
        if not endpoint:
            notes.append("builtin-web-search:missing-endpoint")
            return
        notes.append("builtin-web-search:searxng")
        candidates.append(
            ProviderSelectionCandidate(
                provider_type="searxng",
                model_name="web-search",
                feature_scope="web_search",
                source="builtin",
                provider_config_id=None,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                base_url=self._dockerize_url(endpoint),
                api_key=None,
                auth_mode="none",
                priority=1000,
                metadata={
                    "display_name": "SearXNG (Self-hosted)",
                    "auto_selected": True,
                    "builtin": True,
                },
            )
        )

    def _providers_in_resolution_scope(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None,
    ) -> list[ProviderConfig]:
        scoped = list(
            self.configs.list_by_workspace(
                tenant_id=tenant_id,
                workspace_id=None,
                owner_user_id=owner_user_id,
            )
        )
        if owner_user_id is None:
            scoped = [
                provider for provider in scoped if provider.visibility_scope in {"tenant", "system"}
            ]
        return scoped

    def _dockerize_url(self, url: str | None) -> str | None:
        """
        Rewrites localhost/127.0.0.1 to host.docker.internal if running in Docker.
        This allows the containerized backend to reach local models like LM Studio.
        """
        if not url:
            return url

        import os

        # Check if running in Docker
        if os.path.exists("/.dockerenv") or os.environ.get("AKS_DOCKER_CONTAINER"):
            return url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )

        return url

    def _provider_to_auto_embedding_candidate(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: ProviderConfig,
        source: Literal["env_fallback"],
        model_name: str,
        notes: list[str],
    ) -> ProviderSelectionCandidate | None:
        latest_health = self.health_checks.get_latest_check(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
        )
        if latest_health is not None and latest_health.status == "unhealthy":
            notes.append(f"{source}:health-reject:{provider.id}")
            return None
        api_key = self._resolve_secret_value(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        context_window, context_window_source = self._resolve_model_context_window(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            model_name=model_name,
        )

        base_url = provider.api_base_url or DEFAULT_PROVIDER_BASE_URLS.get(provider.provider_type)
        docker_url = self._dockerize_url(base_url)

        return ProviderSelectionCandidate(
            provider_type=provider.provider_type,
            model_name=model_name,
            feature_scope="embeddings",
            source=source,
            provider_config_id=provider.id,
            tenant_id=tenant_id,
            workspace_id=provider.workspace_id,
            base_url=docker_url,
            api_key=api_key,
            auth_mode=provider.auth_mode,
            context_window=context_window,
            context_window_source=context_window_source,
            priority=provider.priority,
            health_status=latest_health.status if latest_health is not None else None,
            metadata={
                "display_name": provider.display_name,
                "auto_selected": True,
                "is_local": bool(provider.is_local),
            },
        )

    def _resolve_auto_lmstudio_embedding_model(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        configured_default: str | None,
    ) -> str | None:
        if configured_default:
            return configured_default
        cached_models = self.model_cache.list_models(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            model_kind="embedding",
        )
        preferred_tokens = ("embed", "embedding", "bge", "e5", "nomic")
        for model in cached_models:
            if any(token in model.model_name.lower() for token in preferred_tokens):
                return model.model_name
        return cached_models[0].model_name if cached_models else None

    def _assignment_to_candidate(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        feature_scope: str,
        source: str,
        assignment: ProviderAssignment,
        notes: list[str],
        allow_live_model_discovery: bool = False,
    ) -> ProviderSelectionCandidate | None:
        config = (
            self.configs.get_accessible_by_id(
                tenant_id=tenant_id,
                provider_config_id=assignment.provider_config_id,
                owner_user_id=actor_user_id,
            )
            if actor_user_id is not None
            else self.configs.get_by_id(
                tenant_id=tenant_id,
                provider_config_id=assignment.provider_config_id,
            )
        )
        if config is None:
            notes.append(f"{source}:missing-config:{assignment.provider_config_id}")
            return None
        if not config.enabled:
            notes.append(f"{source}:disabled-config:{config.id}")
            return None
        if feature_scope == "chat" and not config.supports_chat:
            notes.append(f"{source}:missing-chat-capability:{config.id}")
            return None
        if feature_scope == "embeddings" and not config.supports_embeddings:
            notes.append(f"{source}:missing-embedding-capability:{config.id}")
            return None
        if feature_scope == "reranking" and not config.supports_reranking:
            notes.append(f"{source}:missing-reranking-capability:{config.id}")
            return None
        if feature_scope == "web_search" and config.provider_type not in {"tavily", "searxng"}:
            notes.append(f"{source}:missing-web-search-capability:{config.id}")
            return None

        latest_health = self.health_checks.get_latest_check(
            tenant_id=tenant_id,
            provider_config_id=config.id,
        )
        if latest_health is not None and latest_health.status == "unhealthy":
            notes.append(f"{source}:health-reject:{config.id}")
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=None,
                action="provider.selection.health_reject",
                resource_type="provider_config",
                resource_id=str(config.id),
                details={
                    "feature_scope": feature_scope,
                    "status": latest_health.status,
                    "workspace_id": str(workspace_id) if workspace_id else "",
                },
            )
            return None

        model_name = assignment.model_name or (
            config.default_chat_model
            if feature_scope == "chat"
            else (
                config.default_embedding_model
                if feature_scope == "embeddings"
                else (
                    config.default_reranker_model if feature_scope == "reranking" else "web-search"
                )
            )
        )
        if not model_name:
            notes.append(f"{source}:missing-model:{config.id}")
            return None
        if feature_scope == "chat":
            resolved_chat_model = self._resolve_usable_chat_model_name(
                tenant_id=tenant_id,
                provider_config_id=config.id,
                preferred_model_name=model_name,
                fallback_model_name=config.default_chat_model,
            )
            if resolved_chat_model is None:
                notes.append(f"{source}:unavailable-chat-model:{config.id}:{model_name}")
                return None
            if resolved_chat_model != model_name:
                notes.append(
                    f"{source}:fallback-chat-model:{config.id}:{model_name}->{resolved_chat_model}"
                )
            model_name = resolved_chat_model
            context_window, context_window_source = self._resolve_model_context_window(
                tenant_id=tenant_id,
                provider_config_id=config.id,
                model_name=model_name,
                allow_live_model_discovery=allow_live_model_discovery,
            )
        else:
            context_window = None
            context_window_source = None

        api_key = self._resolve_secret_value(
            tenant_id=tenant_id,
            provider_config_id=config.id,
            auth_mode=config.auth_mode,
        )

        return ProviderSelectionCandidate(
            provider_type=config.provider_type,
            model_name=model_name,
            feature_scope=feature_scope,
            source=source,  # type: ignore[arg-type]
            provider_config_id=config.id,
            tenant_id=tenant_id,
            workspace_id=assignment.workspace_id,
            base_url=self._dockerize_url(
                config.api_base_url or DEFAULT_PROVIDER_BASE_URLS.get(config.provider_type)
            ),
            api_key=api_key,
            auth_mode=config.auth_mode,
            context_window=context_window,
            context_window_source=context_window_source,
            priority=assignment.priority,
            health_status=latest_health.status if latest_health is not None else None,
            metadata={
                **dict(config.metadata_json or {}),
                "display_name": config.display_name,
                "is_local": bool(config.is_local),
            },
        )

    def _resolve_usable_chat_model_name(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        preferred_model_name: str,
        fallback_model_name: str | None,
    ) -> str | None:
        preferred = self.model_cache.get_model(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            model_name=preferred_model_name,
            model_kind="chat",
        )
        if preferred is None or preferred.is_available:
            return preferred_model_name

        if fallback_model_name and fallback_model_name != preferred_model_name:
            fallback = self.model_cache.get_model(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                model_name=fallback_model_name,
                model_kind="chat",
            )
            if fallback is None or fallback.is_available:
                return fallback_model_name

        cached_rows = self.model_cache.list_models(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            model_kind="chat",
        )
        first_available = next((row for row in cached_rows if row.is_available), None)
        return first_available.model_name if first_available is not None else None

    def _resolve_secret_value(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        auth_mode: str,
    ) -> str | None:
        if auth_mode in {"none", "local_no_key"}:
            return None
        for secret_type in ("api_key", "oauth_access_token", "session_token"):
            value = self.secrets.get_secret_value(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                secret_type=secret_type,
            )
            if value:
                return value
        return None

    def _resolve_model_context_window(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        model_name: str,
        allow_live_model_discovery: bool = False,
    ) -> tuple[int | None, str | None]:
        provider = self.configs.get_by_id(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
        )
        if provider is None:
            return None, None

        model_infos = []
        if allow_live_model_discovery:
            api_key = self._resolve_secret_value(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                auth_mode=provider.auth_mode,
            )
            try:
                discovery = self.registry.get_model_discovery_provider_from_config(
                    provider,
                    api_key=api_key,
                )
                model_infos = list(discovery.list_models()) if provider.supports_chat else []
            except Exception:  # noqa: BLE001
                model_infos = []

        normalized_requested_model = self._normalize_model_name(model_name)
        for model in model_infos:
            if self._normalize_model_name(model.name) != normalized_requested_model:
                continue
            if isinstance(model.context_window, int) and model.context_window > 0:
                context_window_source = model.context_window_source or "live_model"
                return model.context_window, context_window_source
            break

        verified_context_window = resolve_verified_context_window(
            model_name,
            provider_type=provider.provider_type,
        )
        if (
            isinstance(verified_context_window.context_window, int)
            and verified_context_window.context_window > 0
        ):
            context_window_source = verified_context_window.source or "verified_docs"
            return verified_context_window.context_window, context_window_source

        return None, None

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", name.lower())
