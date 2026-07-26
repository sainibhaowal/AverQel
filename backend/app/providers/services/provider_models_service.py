from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.providers.models.provider_config import ProviderConfig
from app.providers.models.provider_health_check import ProviderHealthCheck
from app.providers.models.provider_model_cache import ProviderModelCache
from app.providers.repositories.provider_assignments import (
    ProviderAssignmentsRepository,
)
from app.providers.repositories.provider_configs import ProviderConfigsRepository
from app.providers.repositories.provider_health_checks import (
    ProviderHealthChecksRepository,
)
from app.providers.repositories.provider_model_cache import ProviderModelCacheRepository
from app.providers.services.base import (
    ChatProvider,
    EmbeddingProvider,
    ModelDiscoveryProvider,
    ProviderCapabilityError,
    ProviderRequestError,
)
from app.providers.services.provider_secret_service import ProviderSecretService
from app.providers.services.reasoning_capabilities import (
    model_supports_reasoning,
    reasoning_capabilities,
)
from app.providers.services.registry import ProviderRegistry
from app.providers.services.sentence_transformers_provider import (
    SentenceTransformersEmbeddingProvider,
)
from app.providers.services.types import (
    EmbeddingRequest,
    HealthCheckResult,
    ProviderSelectionCandidate,
)
from app.system.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _looks_like_auth_failure(status_code: int, message: str | None) -> bool:
    if status_code in {401, 403}:
        return True
    normalized = (message or "").lower()
    auth_markers = (
        "incorrect api key",
        "invalid api key",
        "invalid x-api-key",
        "unauthorized",
        "authentication",
        "invalid argument",
        "api key not valid",
        "permission denied",
        "forbidden",
    )
    return any(marker in normalized for marker in auth_markers)


def provider_request_error_to_api_error(
    exc: ProviderRequestError,
    *,
    operation: str,
) -> ApiError:
    provider_label = exc.provider_name.replace("-", " ").title()
    if _looks_like_auth_failure(exc.status_code, exc.message):
        return ApiError(
            code="PROVIDER_TEST_FAILED",
            message=f"{provider_label} API key is incorrect or does not have access. Please update the key and try again.",
            status_code=400,
        )
    if exc.status_code == 429:
        return ApiError(
            code="PROVIDER_TEST_FAILED",
            message=f"{provider_label} rate limited the request. Please try again in a moment.",
            status_code=429,
        )
    if exc.status_code >= 500:
        return ApiError(
            code="PROVIDER_TEST_FAILED",
            message=f"{provider_label} is temporarily unavailable during model {operation}. Please try again shortly.",
            status_code=502,
        )
    detail = (
        exc.message.strip()
        if isinstance(exc.message, str) and exc.message.strip()
        else None
    )
    return ApiError(
        code="PROVIDER_TEST_FAILED",
        message=detail or f"{provider_label} model {operation} failed.",
        status_code=502,
    )


@dataclass(slots=True)
class ProviderModelsService:
    db: Session
    registry: ProviderRegistry
    configs: ProviderConfigsRepository = field(init=False)
    assignments: ProviderAssignmentsRepository = field(init=False)
    cache: ProviderModelCacheRepository = field(init=False)
    health_checks: ProviderHealthChecksRepository = field(init=False)
    secrets: ProviderSecretService = field(init=False)
    audit: AuditService = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "configs", ProviderConfigsRepository(self.db))
        object.__setattr__(self, "assignments", ProviderAssignmentsRepository(self.db))
        object.__setattr__(self, "cache", ProviderModelCacheRepository(self.db))
        object.__setattr__(
            self, "health_checks", ProviderHealthChecksRepository(self.db)
        )
        object.__setattr__(self, "secrets", ProviderSecretService(self.db))
        object.__setattr__(self, "audit", AuditService(self.db))

    def list_models(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[ProviderModelCache]:
        self._get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
            require_enabled=False,
        )
        return list(
            self.cache.list_models(
                tenant_id=tenant_id, provider_config_id=provider_config_id
            )
        )

    def refresh_models(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> list[ProviderModelCache]:
        provider = self._get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
            require_enabled=True,
        )
        api_key = self._resolve_api_key(tenant_id=tenant_id, provider=provider)
        try:
            discovery = self.registry.get_model_discovery_provider_from_config(
                provider, api_key=api_key
            )
            chat_models = (
                list(discovery.list_models()) if provider.supports_chat else []
            )
            embedding_models = []
            reranker_models = []
            if provider.supports_embeddings:
                try:
                    embedding_models = list(discovery.list_embedding_models())
                except ProviderCapabilityError:
                    embedding_models = []
            if provider.supports_reranking:
                try:
                    reranker_models = list(discovery.list_reranker_models())
                except ProviderCapabilityError:
                    reranker_models = []
        except ProviderCapabilityError as exc:
            raise ApiError(
                code="PROVIDER_TEST_FAILED",
                message=str(exc),
                status_code=400,
            ) from exc
        except ProviderRequestError as exc:
            raise provider_request_error_to_api_error(exc, operation="refresh") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Provider model refresh failed during discovery",
                extra={
                    "tenant_id": str(tenant_id),
                    "provider_config_id": str(provider_config_id),
                    "provider_type": provider.provider_type,
                },
            )
            raise ApiError(
                code="PROVIDER_TEST_FAILED",
                message="Provider model refresh failed.",
                status_code=502,
            ) from exc

        rows: list[ProviderModelCache] = []
        seen: set[tuple[str, str]] = set()
        usable_chat_model_names = self._resolve_usable_chat_model_names(
            provider=provider,
            api_key=api_key,
            chat_models=chat_models,
        )
        for model in chat_models + embedding_models + reranker_models:
            kind = model.kind
            is_available = True
            capabilities = dict(model.capabilities)
            if kind == "chat" and provider.provider_type == "lmstudio":
                is_available = model.name in usable_chat_model_names
                capabilities["chat_usable"] = is_available
                if not is_available:
                    capabilities["availability_reason"] = (
                        "lmstudio_chat_model_load_failed"
                    )
            if kind == "embedding":
                capabilities["embedding_dimension"] = capabilities.get(
                    "embedding_dimension"
                ) or self._detect_embedding_dimension(
                    provider=provider,
                    api_key=api_key,
                    model_name=model.name,
                )
            if kind == "chat":
                capabilities.setdefault(
                    "supports_reasoning",
                    model_supports_reasoning(provider.provider_type, model.name),
                )
                for key, value in reasoning_capabilities(
                    provider.provider_type,
                    model.name,
                    base_url=provider.api_base_url,
                ).items():
                    capabilities.setdefault(key, value)
            row = ProviderModelCache(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                model_name=model.name,
                model_kind=kind,
                display_name=model.display_name,
                context_window=model.context_window,
                capabilities_json={
                    **capabilities,
                    **(
                        {"context_window_source": model.context_window_source}
                        if model.context_window_source
                        else {}
                    ),
                },
                is_available=is_available,
            )
            rows.append(row)
            seen.add((model.name, kind))

        persisted = self.cache.upsert_models(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            models=rows,
        )
        self.cache.purge_stale_models(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            seen_names=seen,
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.models.refresh",
            resource_type="provider_config",
            resource_id=str(provider.id),
            details={"model_count": str(len(persisted))},
        )
        self._backfill_provider_defaults_and_assignments(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            provider=provider,
            chat_models=chat_models,
            embedding_models=embedding_models,
            reranker_models=reranker_models,
            usable_chat_model_names=usable_chat_model_names,
        )
        return list(
            self.cache.list_models(tenant_id=tenant_id, provider_config_id=provider.id)
        )

    def pull_model(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        model_name: str,
        actor_user_id: uuid.UUID | None,
    ) -> str:
        provider = self._get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
            require_enabled=True,
        )
        if not provider.supports_model_install:
            raise ApiError(
                code="PROVIDER_MODEL_PULL_UNSUPPORTED",
                message="Provider does not support model pull.",
                status_code=400,
            )
        api_key = self._resolve_api_key(tenant_id=tenant_id, provider=provider)
        try:
            installer = self.registry.get_install_provider_from_config(
                provider, api_key=api_key
            )
            installer.pull_model(model_name)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="PROVIDER_MODEL_PULL_UNSUPPORTED",
                message="Model pull failed or is unsupported for this provider.",
                status_code=400,
            ) from exc

        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.models.pull",
            resource_type="provider_config",
            resource_id=str(provider.id),
            details={"model_name": model_name},
        )
        return model_name

    def test_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> ProviderHealthCheck:
        provider = self._get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
            require_enabled=True,
        )
        api_key = self._resolve_api_key(tenant_id=tenant_id, provider=provider)
        try:
            runtime: ModelDiscoveryProvider | ChatProvider | EmbeddingProvider
            if provider.provider_type in {"tavily", "searxng"}:
                runtime = self.registry.get_web_search_provider_from_config(
                    provider, api_key=api_key
                )
            elif provider.supports_model_listing:
                runtime = self.registry.get_model_discovery_provider_from_config(
                    provider, api_key=api_key
                )
            elif provider.supports_chat:
                runtime = self.registry.get_chat_provider_from_selection(
                    self._provider_to_selection(provider, api_key)
                )
            elif provider.supports_reranking:
                runtime = self.registry.get_reranker_provider_from_selection(
                    self._provider_to_selection(
                        provider,
                        api_key,
                        feature_scope="reranking",
                    )
                )
            else:
                runtime = self.registry.get_embedding_provider_from_selection(
                    self._provider_to_selection(provider, api_key)
                )
            result = runtime.health_check()
        except Exception as exc:  # noqa: BLE001
            result = None
            error: str | None = str(exc)
        else:
            error = None
        if (
            result is not None
            and provider.provider_type == "lmstudio"
            and provider.supports_chat
            and provider.default_chat_model
            and not self._is_chat_model_usable(
                provider=provider,
                api_key=api_key,
                model_name=provider.default_chat_model,
            )
        ):
            result = HealthCheckResult(
                status="unhealthy",
                error_code="provider_model_unavailable",
                error_message_redacted=(
                    "Configured LM Studio chat model could not be loaded for completions."
                ),
                metadata={"model_name": provider.default_chat_model},
            )

        h_status = result.status if result is not None else "unhealthy"
        h_latency = result.latency_ms if result is not None else None
        h_error_code = (
            result.error_code if result is not None else "provider_test_failed"
        )
        h_error_msg = result.error_message_redacted if result is not None else error
        h_metadata = dict(result.metadata) if result is not None else {}

        row = self.health_checks.record_check(
            ProviderHealthCheck(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                status=h_status,
                latency_ms=h_latency,
                http_status=None,
                error_code=h_error_code,
                error_message_redacted=h_error_msg,
                metadata_json=h_metadata,
            )
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.health.test",
            resource_type="provider_config",
            resource_id=str(provider.id),
            details={"status": row.status},
        )
        return row

    def get_latest_health(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> ProviderHealthCheck | None:
        return self.health_checks.get_latest_check(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
        )

    def _get_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        require_enabled: bool,
    ) -> ProviderConfig:
        provider = (
            self.configs.get_accessible_by_id(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                owner_user_id=actor_user_id,
            )
            if actor_user_id is not None
            else self.configs.get_by_id(
                tenant_id=tenant_id, provider_config_id=provider_config_id
            )
        )
        if provider is None:
            raise ApiError(
                code="PROVIDER_NOT_FOUND",
                message="Provider configuration not found.",
                status_code=404,
            )
        if require_enabled and not provider.enabled:
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Provider is disabled.",
                status_code=400,
            )
        return provider

    def _resolve_api_key(
        self, *, tenant_id: uuid.UUID, provider: ProviderConfig
    ) -> str | None:
        if provider.auth_mode in {"none", "local_no_key"}:
            return None
        return self.secrets.get_secret_value(  # nosec B106
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            secret_type="api_key",
        )

    def _backfill_provider_defaults_and_assignments(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        provider: ProviderConfig,
        chat_models: list[Any],
        embedding_models: list[Any],
        reranker_models: list[Any],
        usable_chat_model_names: set[str],
    ) -> None:
        update_values: dict[str, object] = {}
        discovered_chat_model_names = {
            model.name
            for model in chat_models
            if isinstance(getattr(model, "name", None), str) and model.name
        }
        embedding_model_names = {
            model.name
            for model in embedding_models
            if isinstance(getattr(model, "name", None), str) and model.name
        }
        reranker_model_names = {
            model.name
            for model in reranker_models
            if isinstance(getattr(model, "name", None), str) and model.name
        }

        if provider.supports_chat:
            selected_chat_models = (
                usable_chat_model_names or discovered_chat_model_names
            )
            if (
                not provider.default_chat_model
                or provider.default_chat_model not in selected_chat_models
            ):
                default_chat_model = self._select_default_chat_model(
                    chat_models,
                    valid_model_names=selected_chat_models,
                )
                update_values["default_chat_model"] = default_chat_model
                provider.default_chat_model = default_chat_model

        # Embedding defaults must remain an explicit user choice. Model refresh can
        # validate an existing setting, but it must not silently pick a new default.
        if (
            provider.supports_embeddings
            and provider.default_embedding_model
            and provider.default_embedding_model not in embedding_model_names
        ):
            update_values["default_embedding_model"] = None
            provider.default_embedding_model = None
        if (
            provider.provider_type == "lmstudio"
            and provider.default_embedding_model
            and self._managed_server_embeddings_enabled(
                tenant_id=tenant_id,
                workspace_id=provider.workspace_id,
            )
        ):
            update_values["default_embedding_model"] = None
            provider.default_embedding_model = None

        if provider.supports_reranking:
            if (
                not provider.default_reranker_model
                or provider.default_reranker_model not in reranker_model_names
            ):
                default_reranker_model = self._select_default_reranker_model(
                    reranker_models
                )
                update_values["default_reranker_model"] = default_reranker_model
                provider.default_reranker_model = default_reranker_model

        if update_values:
            self.configs.update_fields(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                values=update_values,
            )
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.config.auto_defaults",
                resource_type="provider_config",
                resource_id=str(provider.id),
                details={key: str(value) for key, value in update_values.items()},
            )

        # Provider model refresh must not silently change the tenant's active
        # routing assignments. Defaults may be updated here, but assignments are
        # now explicit user decisions made through the assignments API/UI.

    def _managed_server_embeddings_enabled(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
    ) -> bool:
        scoped = list(
            self.configs.list_by_workspace(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        )
        if workspace_id is not None:
            scoped_ids = {provider.id for provider in scoped}
            scoped.extend(
                provider
                for provider in self.configs.list_by_workspace(
                    tenant_id=tenant_id,
                    workspace_id=None,
                )
                if provider.id not in scoped_ids
            )
        return any(
            provider.enabled
            and provider.provider_type == "sentence-transformers"
            and provider.supports_embeddings
            for provider in scoped
        )

    @staticmethod
    def _looks_like_embedding_model(model_name: str) -> bool:
        lowered = model_name.lower()
        return any(
            token in lowered for token in ("embed", "embedding", "bge", "e5", "nomic")
        )

    def _detect_embedding_dimension(
        self,
        *,
        provider: ProviderConfig,
        api_key: str | None,
        model_name: str,
    ) -> int | None:
        if provider.provider_type == "sentence-transformers":
            return SentenceTransformersEmbeddingProvider.get_embedding_dimension(
                model_name
            )
        try:
            response = self.registry.get_embedding_provider_from_selection(
                self._provider_to_selection(
                    provider,
                    api_key,
                    model_name=model_name,
                )
            ).embed_many(
                EmbeddingRequest(
                    texts=["dimension probe"],
                    model=model_name,
                    batch_size=1,
                    normalize=False,
                    dimension=self.registry.settings.embedding_dimension,
                    timeout_seconds=min(provider.timeout_seconds, 15),
                    provider_name=provider.provider_type,
                    metadata={
                        "base_url": provider.api_base_url,
                        "api_key": api_key,
                    },
                )
            )
        except Exception:
            return None
        if not response.vectors or not response.vectors[0]:
            return None
        return len(response.vectors[0])

    def _select_default_chat_model(
        self,
        chat_models: list[Any],
        *,
        valid_model_names: set[str],
    ) -> str | None:
        names = [
            model.name
            for model in chat_models
            if isinstance(getattr(model, "name", None), str)
            and model.name
            and model.name in valid_model_names
        ]
        if not names:
            return None
        for name in names:
            if not self._looks_like_embedding_model(name):
                return name
        return names[0]

    def _resolve_usable_chat_model_names(
        self,
        *,
        provider: ProviderConfig,
        api_key: str | None,
        chat_models: list[Any],
    ) -> set[str]:
        # For LM Studio, return ALL discovered models without testing.
        # LM Studio's /models endpoint returns what's available.
        # Don't test load each model - user chooses which to use.
        if provider.provider_type == "lmstudio":
            return {
                model.name
                for model in chat_models
                if isinstance(getattr(model, "name", None), str) and model.name
            }
        return {
            model.name
            for model in chat_models
            if isinstance(getattr(model, "name", None), str) and model.name
        }

    def _is_chat_model_usable(
        self,
        *,
        provider: ProviderConfig,
        api_key: str | None,
        model_name: str,
    ) -> bool:
        candidate = ProviderSelectionCandidate(
            provider_type=provider.provider_type,
            model_name=model_name,
            feature_scope="chat",
            source="tenant",
            provider_config_id=provider.id,
            tenant_id=provider.tenant_id,
            workspace_id=provider.workspace_id,
            base_url=provider.api_base_url,
            api_key=api_key,
            auth_mode=provider.auth_mode,
            metadata={"display_name": provider.display_name},
        )
        try:
            runtime = self.registry.get_chat_provider_from_selection(candidate)
            probe = getattr(runtime, "chat_model_is_usable", None)
            if callable(probe):
                return bool(probe(model_name))
            request = self._build_probe_request(
                provider=provider, api_key=api_key, model_name=model_name
            )
            runtime.generate(request)
            return True
        except Exception:
            return False

    @staticmethod
    def _build_probe_request(
        *,
        provider: ProviderConfig,
        api_key: str | None,
        model_name: str,
    ):
        from app.providers.services.types import ChatGenerateRequest

        return ChatGenerateRequest(
            model=model_name,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            max_tokens=1,
            base_url=provider.api_base_url or "",
            api_key=api_key,
            stream=False,
        )

    def _select_default_embedding_model(
        self, embedding_models: list[Any]
    ) -> str | None:
        names = [
            model.name
            for model in embedding_models
            if isinstance(getattr(model, "name", None), str) and model.name
        ]
        if not names:
            return None
        for name in names:
            if self._looks_like_embedding_model(name):
                return name
        return names[0]

    @staticmethod
    def _select_default_reranker_model(reranker_models: list[Any]) -> str | None:
        names = [
            model.name
            for model in reranker_models
            if isinstance(getattr(model, "name", None), str) and model.name
        ]
        if not names:
            return None
        for preferred in (
            "BAAI/bge-reranker-v2-m3",
            "cross-encoder/ms-marco-MiniLM-L-12-v2",
        ):
            if preferred in names:
                return preferred
        return names[0]

    @staticmethod
    def _provider_to_selection(
        provider: ProviderConfig,
        api_key: str | None,
        *,
        model_name: str | None = None,
        feature_scope: str | None = None,
    ) -> ProviderSelectionCandidate:
        return ProviderSelectionCandidate(
            provider_type=provider.provider_type,
            model_name=model_name
            or provider.default_chat_model
            or provider.default_embedding_model
            or provider.default_reranker_model
            or "default",
            feature_scope=feature_scope
            or (
                "chat"
                if provider.supports_chat
                else "embeddings" if provider.supports_embeddings else "reranking"
            ),
            source="tenant",
            provider_config_id=provider.id,
            tenant_id=provider.tenant_id,
            workspace_id=provider.workspace_id,
            base_url=provider.api_base_url,
            api_key=api_key,
            auth_mode=provider.auth_mode,
            metadata={"display_name": provider.display_name},
        )
