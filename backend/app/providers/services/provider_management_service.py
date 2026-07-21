from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.providers.models.provider_assignment import ProviderAssignment
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
from app.providers.services.provider_secret_crypto import ProviderSecretCryptoError
from app.providers.services.provider_secret_service import (
    MaskedProviderSecret,
    ProviderSecretService,
)
from app.providers.services.registry import ProviderRegistry
from app.providers.services.sentence_transformers_provider import (
    SentenceTransformersEmbeddingProvider,
)
from app.providers.services.types import (
    EmbeddingRequest,
    ProviderModelInfo,
    ProviderSelectionCandidate,
)
from app.system.services.audit_service import AuditService

SUPPORTED_PROVIDER_CATALOG: dict[str, dict[str, object]] = {
    "openai": {
        "display_name": "OpenAI API",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "groq": {
        "display_name": "Groq",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "groq-openai-compatible": {
        "display_name": "Groq OpenAI-Compatible",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "custom": {
        "display_name": "OpenAI-Compatible",
        "auth_modes": ["api_key", "none"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "lmstudio": {
        "display_name": "LM Studio",
        "auth_modes": ["local_no_key", "api_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": True,
    },
    "ollama": {
        "display_name": "Ollama",
        "auth_modes": ["local_no_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": True,
        "supports_account_linking": False,
        "is_local": True,
    },
    "anthropic": {
        "display_name": "Anthropic",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": False,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "google": {
        "display_name": "Google",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": False,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "opencode-zen": {
        "display_name": "OpenCode Zen",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": False,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "cohere": {
        "display_name": "Cohere",
        "auth_modes": ["api_key"],
        "supports_chat": False,
        "supports_embeddings": False,
        "supports_reranking": True,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "sentence-transformers": {
        "display_name": "AverQel Server Retrieval",
        "auth_modes": ["none"],
        "supports_chat": False,
        "supports_embeddings": True,
        "supports_reranking": True,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "tavily": {
        "display_name": "Tavily Web Search",
        "auth_modes": ["api_key"],
        "supports_chat": False,
        "supports_embeddings": False,
        "supports_reranking": False,
        "supports_web_search": True,
        "supports_model_listing": False,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    },
}

ALLOWED_SECRET_TYPES_BY_AUTH_MODE: dict[str, frozenset[str]] = {
    "api_key": frozenset({"api_key"}),
    "local_no_key": frozenset(),
    "none": frozenset(),
    "oauth_pkce": frozenset({"oauth_access_token", "oauth_refresh_token"}),
}

MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE = "sentence-transformers"
MANAGED_EMBEDDINGS_PROVIDER_NAME = "AverQel Server Embeddings"
MANAGED_RERANKER_PROVIDER_NAME = "AverQel Server ReRanker"


@dataclass(slots=True)
class ProviderManagementService:
    db: Session
    configs: ProviderConfigsRepository = field(init=False)
    assignments: ProviderAssignmentsRepository = field(init=False)
    cache: ProviderModelCacheRepository = field(init=False)
    secrets: ProviderSecretService = field(init=False)
    health_checks: ProviderHealthChecksRepository = field(init=False)
    audit: AuditService = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "configs", ProviderConfigsRepository(self.db))
        object.__setattr__(self, "assignments", ProviderAssignmentsRepository(self.db))
        object.__setattr__(self, "cache", ProviderModelCacheRepository(self.db))
        object.__setattr__(self, "secrets", ProviderSecretService(self.db))
        object.__setattr__(
            self, "health_checks", ProviderHealthChecksRepository(self.db)
        )
        object.__setattr__(self, "audit", AuditService(self.db))

    def list_supported_types(self) -> list[dict[str, object]]:
        return [
            {"provider_type": provider_type, **catalog}
            for provider_type, catalog in sorted(SUPPORTED_PROVIDER_CATALOG.items())
        ]

    def list_providers(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> list[ProviderConfig]:
        self._ensure_managed_sentence_transformer_providers(tenant_id=tenant_id)
        return list(
            self.configs.list_by_workspace(
                tenant_id=tenant_id,
                workspace_id=None,
                owner_user_id=actor_user_id,
            )
        )

    def get_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> ProviderConfig:
        provider = (
            self.configs.get_accessible_by_id(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                owner_user_id=actor_user_id,
            )
            if actor_user_id is not None
            else self.configs.get_by_id(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
            )
        )
        if provider is None:
            raise ApiError(
                code="PROVIDER_NOT_FOUND",
                message="Provider configuration not found.",
                status_code=404,
            )
        return provider

    def create_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID,
        provider_type: str,
        display_name: str,
        api_base_url: str | None,
        auth_mode: str,
        enabled: bool,
        is_local: bool,
        supports_chat: bool,
        supports_embeddings: bool,
        supports_model_listing: bool,
        supports_model_install: bool,
        default_chat_model: str | None,
        default_embedding_model: str | None,
        timeout_seconds: int,
        priority: int,
        metadata_json: dict[str, object],
        supports_web_search: bool | None = None,
        supports_reranking: bool | None = None,
        default_reranker_model: str | None = None,
        api_key: str | None = None,
    ) -> ProviderConfig:
        effective_supports_reranking = (
            bool(SUPPORTED_PROVIDER_CATALOG[provider_type]["supports_reranking"])
            if supports_reranking is None
            else supports_reranking
        )
        self._validate_provider_definition(
            provider_type=provider_type,
            api_base_url=api_base_url,
            auth_mode=auth_mode,
            supports_chat=supports_chat,
            supports_embeddings=supports_embeddings,
            supports_reranking=effective_supports_reranking,
            supports_model_listing=supports_model_listing,
            supports_model_install=supports_model_install,
            is_local=is_local,
            api_key=api_key,
        )
        effective_default_embedding_model = default_embedding_model
        if (
            provider_type == "lmstudio"
            and supports_embeddings
            and self._managed_server_embeddings_enabled(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        ):
            effective_default_embedding_model = None

        owner_user_id = (
            None
            if provider_type == MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE
            else actor_user_id
        )
        visibility_scope = (
            "system"
            if provider_type == MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE
            else "user"
        )
        row = self.configs.create(
            ProviderConfig(
                tenant_id=tenant_id,
                workspace_id=None,
                owner_user_id=owner_user_id,
                visibility_scope=visibility_scope,
                provider_type=provider_type,
                display_name=display_name.strip(),
                api_base_url=api_base_url.strip() if api_base_url else None,
                auth_mode=auth_mode,
                enabled=enabled,
                is_local=is_local,
                supports_chat=supports_chat,
                supports_embeddings=supports_embeddings,
                supports_reranking=effective_supports_reranking,
                supports_model_listing=supports_model_listing,
                supports_model_install=supports_model_install,
                default_chat_model=default_chat_model,
                default_embedding_model=effective_default_embedding_model,
                default_reranker_model=default_reranker_model,
                timeout_seconds=timeout_seconds,
                priority=priority,
                metadata_json={
                    **dict(metadata_json),
                    "supports_web_search": bool(
                        supports_web_search
                        if supports_web_search is not None
                        else SUPPORTED_PROVIDER_CATALOG[provider_type].get(
                            "supports_web_search", False
                        )
                    ),
                },
            )
        )
        if api_key:
            try:
                self.secrets.upsert_secret(  # nosec B106
                    tenant_id=tenant_id,
                    provider_config_id=row.id,
                    secret_type="api_key",
                    secret_value=api_key,
                    actor_user_id=actor_user_id,
                )
            except ProviderSecretCryptoError as exc:
                raise ApiError(
                    code="PROVIDER_SECRET_STORAGE_UNAVAILABLE",
                    message="Provider secret encryption is not configured.",
                    status_code=503,
                ) from exc
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.config.create",
            resource_type="provider_config",
            resource_id=str(row.id),
            details={
                "provider_type": provider_type,
                "workspace_id": str(workspace_id or ""),
            },
        )
        if row.provider_type == "sentence-transformers" and row.enabled:
            self._clear_lmstudio_embedding_defaults(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                reason="managed_embeddings_enabled",
            )
        return row

    def update_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        values: dict[str, object],
        api_key: str | None = None,
    ) -> ProviderConfig:
        provider = self.get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )
        if (
            provider.owner_user_id is not None
            and provider.owner_user_id != actor_user_id
        ):
            raise ApiError(
                code="PROVIDER_CONFIG_NOT_FOUND",
                message="Provider configuration not found.",
                status_code=404,
            )
        update_values = dict(values)
        if "display_name" in update_values and isinstance(
            update_values["display_name"], str
        ):
            update_values["display_name"] = update_values["display_name"].strip()
        if "api_base_url" in update_values and isinstance(
            update_values["api_base_url"], str
        ):
            update_values["api_base_url"] = update_values["api_base_url"].strip()
        merged_auth_mode = (
            str(update_values["auth_mode"])
            if "auth_mode" in update_values and update_values["auth_mode"] is not None
            else provider.auth_mode
        )
        merged_api_base_url = (
            str(update_values["api_base_url"])
            if "api_base_url" in update_values
            and update_values["api_base_url"] is not None
            else provider.api_base_url
        )
        merged_provider_type = (
            str(update_values["provider_type"])
            if "provider_type" in update_values
            and update_values["provider_type"] is not None
            else provider.provider_type
        )
        merged_enabled = bool(update_values.get("enabled", provider.enabled))
        managed_embeddings_enabled = self._managed_server_embeddings_enabled(
            tenant_id=tenant_id,
            workspace_id=provider.workspace_id,
            exclude_provider_id=(
                provider.id if merged_provider_type == "sentence-transformers" else None
            ),
        )
        if (
            merged_provider_type == "lmstudio"
            and bool(
                update_values.get("supports_embeddings", provider.supports_embeddings)
            )
            and managed_embeddings_enabled
        ):
            update_values["default_embedding_model"] = None
        # For capability fields not being explicitly updated, use the catalog value
        # as fallback rather than the DB value. This prevents stale DB data from
        # blocking updates to unrelated fields (e.g. changing default_chat_model).
        _catalog_caps = SUPPORTED_PROVIDER_CATALOG.get(merged_provider_type, {})
        self._validate_provider_definition(
            provider_type=merged_provider_type,
            api_base_url=merged_api_base_url,
            auth_mode=merged_auth_mode,
            supports_chat=bool(
                update_values.get(
                    "supports_chat",
                    _catalog_caps.get("supports_chat", provider.supports_chat),
                )
            ),
            supports_embeddings=bool(
                update_values.get(
                    "supports_embeddings",
                    _catalog_caps.get(
                        "supports_embeddings", provider.supports_embeddings
                    ),
                )
            ),
            supports_reranking=bool(
                update_values.get(
                    "supports_reranking",
                    _catalog_caps.get(
                        "supports_reranking", provider.supports_reranking
                    ),
                )
            ),
            supports_model_listing=bool(
                update_values.get(
                    "supports_model_listing",
                    _catalog_caps.get(
                        "supports_model_listing", provider.supports_model_listing
                    ),
                )
            ),
            supports_model_install=bool(
                update_values.get(
                    "supports_model_install",
                    _catalog_caps.get(
                        "supports_model_install", provider.supports_model_install
                    ),
                )
            ),
            is_local=bool(
                update_values.get(
                    "is_local", _catalog_caps.get("is_local", provider.is_local)
                )
            ),
            api_key=api_key,
            existing_auth_mode=provider.auth_mode,
        )
        if update_values:
            self.configs.update_fields(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                values=update_values,
            )
        if api_key:
            try:
                self.secrets.upsert_secret(  # nosec B106
                    tenant_id=tenant_id,
                    provider_config_id=provider_config_id,
                    secret_type="api_key",
                    secret_value=api_key,
                    actor_user_id=actor_user_id,
                )
            except ProviderSecretCryptoError as exc:
                raise ApiError(
                    code="PROVIDER_SECRET_STORAGE_UNAVAILABLE",
                    message="Provider secret encryption is not configured.",
                    status_code=503,
                ) from exc
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.config.update",
            resource_type="provider_config",
            resource_id=str(provider.id),
            details={"updated_fields": ",".join(sorted(update_values.keys()))},
        )
        if (
            merged_provider_type == "sentence-transformers"
            and merged_enabled
            and bool(
                update_values.get("supports_embeddings", provider.supports_embeddings)
            )
        ):
            self._clear_lmstudio_embedding_defaults(
                tenant_id=tenant_id,
                workspace_id=provider.workspace_id,
                actor_user_id=actor_user_id,
                reason="managed_embeddings_enabled",
                exclude_provider_id=provider.id,
            )
        return self.get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )

    def _managed_server_embeddings_enabled(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        exclude_provider_id: uuid.UUID | None = None,
    ) -> bool:
        for candidate in self._providers_in_resolution_scope(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        ):
            if exclude_provider_id is not None and candidate.id == exclude_provider_id:
                continue
            if (
                candidate.provider_type == "sentence-transformers"
                and candidate.enabled
                and candidate.supports_embeddings
            ):
                return True
        return False

    def _providers_in_resolution_scope(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        owner_user_id: uuid.UUID | None = None,
    ) -> list[ProviderConfig]:
        scoped = list(
            self.configs.list_by_workspace(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=owner_user_id,
            )
        )
        if workspace_id is None:
            return scoped
        tenant_defaults = [
            candidate
            for candidate in self.configs.list_by_workspace(
                tenant_id=tenant_id,
                workspace_id=None,
                owner_user_id=owner_user_id,
            )
            if candidate.id not in {provider.id for provider in scoped}
        ]
        return scoped + tenant_defaults

    def _clear_lmstudio_embedding_defaults(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        actor_user_id: uuid.UUID,
        reason: str,
        exclude_provider_id: uuid.UUID | None = None,
    ) -> None:
        for candidate in self._providers_in_resolution_scope(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_user_id=actor_user_id,
        ):
            if exclude_provider_id is not None and candidate.id == exclude_provider_id:
                continue
            if (
                candidate.provider_type != "lmstudio"
                or not candidate.supports_embeddings
                or not candidate.default_embedding_model
            ):
                continue
            self.configs.update_fields(
                tenant_id=tenant_id,
                provider_config_id=candidate.id,
                values={"default_embedding_model": None},
            )
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.config.clear_embedding_default",
                resource_type="provider_config",
                resource_id=str(candidate.id),
                details={"reason": reason},
            )

    def _ensure_managed_sentence_transformer_providers(
        self, *, tenant_id: uuid.UUID
    ) -> None:
        tenant_defaults = list(
            self.configs.list_by_workspace(tenant_id=tenant_id, workspace_id=None)
        )
        managed_rows = [
            row
            for row in tenant_defaults
            if row.provider_type == MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE
        ]
        managed_rows = self._collapse_duplicate_managed_sentence_transformer_providers(
            tenant_id=tenant_id,
            managed_rows=managed_rows,
        )

        embeddings_provider = next(
            (
                row
                for row in managed_rows
                if row.display_name == MANAGED_EMBEDDINGS_PROVIDER_NAME
                or (row.supports_embeddings and not row.supports_reranking)
            ),
            None,
        )
        reranker_provider = next(
            (
                row
                for row in managed_rows
                if row.display_name == MANAGED_RERANKER_PROVIDER_NAME
                or (row.supports_reranking and not row.supports_embeddings)
            ),
            None,
        )
        mixed_provider = next(
            (
                row
                for row in managed_rows
                if row.supports_embeddings and row.supports_reranking
            ),
            None,
        )

        changed = False
        if embeddings_provider is None and mixed_provider is None:
            embeddings_provider = self._create_managed_sentence_transformer_provider(
                tenant_id=tenant_id,
                display_name=MANAGED_EMBEDDINGS_PROVIDER_NAME,
                supports_embeddings=True,
                supports_reranking=False,
                default_embedding_model=get_settings().embedding_model,
                default_reranker_model=None,
                enabled=True,
            )
            changed = True

        if mixed_provider is not None:
            embeddings_provider = self._convert_mixed_provider_to_embeddings(
                tenant_id=tenant_id,
                provider=mixed_provider,
            )
            reranker_provider = self._ensure_split_reranker_provider(
                tenant_id=tenant_id,
                source_provider=mixed_provider,
                existing_reranker=reranker_provider,
            )
            self._migrate_reranking_assignments(
                tenant_id=tenant_id,
                from_provider_id=mixed_provider.id,
                to_provider_id=reranker_provider.id,
                default_model_name=(
                    reranker_provider.default_reranker_model
                    or get_settings().reranking_model
                ),
            )
            self._seed_managed_provider_model_cache(
                tenant_id=tenant_id,
                provider=embeddings_provider,
            )
            self._seed_managed_provider_model_cache(
                tenant_id=tenant_id,
                provider=reranker_provider,
            )
            changed = True
        else:
            if embeddings_provider is None:
                fallback_source = reranker_provider
                embeddings_provider = (
                    self._create_managed_sentence_transformer_provider(
                        tenant_id=tenant_id,
                        display_name=MANAGED_EMBEDDINGS_PROVIDER_NAME,
                        supports_embeddings=True,
                        supports_reranking=False,
                        default_embedding_model=get_settings().embedding_model,
                        default_reranker_model=None,
                        enabled=(
                            fallback_source.enabled
                            if fallback_source is not None
                            else True
                        ),
                    )
                )
                changed = True
            if reranker_provider is None:
                reranker_provider = self._create_managed_sentence_transformer_provider(
                    tenant_id=tenant_id,
                    display_name=MANAGED_RERANKER_PROVIDER_NAME,
                    supports_embeddings=False,
                    supports_reranking=True,
                    default_embedding_model=None,
                    default_reranker_model=get_settings().reranking_model,
                    enabled=(
                        embeddings_provider.enabled
                        if embeddings_provider is not None
                        else True
                    ),
                )
                changed = True

        if embeddings_provider is not None:
            self._seed_managed_provider_model_cache(
                tenant_id=tenant_id,
                provider=embeddings_provider,
            )
        if reranker_provider is not None:
            self._seed_managed_provider_model_cache(
                tenant_id=tenant_id,
                provider=reranker_provider,
            )
        if changed:
            self.db.commit()

    def _collapse_duplicate_managed_sentence_transformer_providers(
        self,
        *,
        tenant_id: uuid.UUID,
        managed_rows: list[ProviderConfig],
    ) -> list[ProviderConfig]:
        embeddings_rows = [
            row
            for row in managed_rows
            if row.display_name == MANAGED_EMBEDDINGS_PROVIDER_NAME
            or (row.supports_embeddings and not row.supports_reranking)
        ]
        reranker_rows = [
            row
            for row in managed_rows
            if row.display_name == MANAGED_RERANKER_PROVIDER_NAME
            or (row.supports_reranking and not row.supports_embeddings)
        ]

        changed = False
        if len(embeddings_rows) > 1:
            self._delete_duplicate_managed_provider_rows(
                tenant_id=tenant_id,
                canonical=min(embeddings_rows, key=lambda row: row.created_at),
                duplicates=[
                    row
                    for row in embeddings_rows
                    if row.id
                    != min(
                        embeddings_rows, key=lambda candidate: candidate.created_at
                    ).id
                ],
            )
            changed = True
        if len(reranker_rows) > 1:
            self._delete_duplicate_managed_provider_rows(
                tenant_id=tenant_id,
                canonical=min(reranker_rows, key=lambda row: row.created_at),
                duplicates=[
                    row
                    for row in reranker_rows
                    if row.id
                    != min(reranker_rows, key=lambda candidate: candidate.created_at).id
                ],
            )
            changed = True
        if changed:
            self.db.flush()
            refreshed_defaults = list(
                self.configs.list_by_workspace(tenant_id=tenant_id, workspace_id=None)
            )
            return [
                row
                for row in refreshed_defaults
                if row.provider_type == MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE
            ]
        return managed_rows

    def _delete_duplicate_managed_provider_rows(
        self,
        *,
        tenant_id: uuid.UUID,
        canonical: ProviderConfig,
        duplicates: list[ProviderConfig],
    ) -> None:
        if not duplicates:
            return
        canonical_enabled = canonical.enabled
        for duplicate in duplicates:
            if duplicate.enabled:
                canonical_enabled = True
            for assignment in self.assignments.list_for_provider(
                tenant_id=tenant_id,
                provider_config_id=duplicate.id,
                enabled_only=False,
            ):
                self.assignments.update_fields(
                    tenant_id=tenant_id,
                    assignment_id=assignment.id,
                    values={"provider_config_id": canonical.id},
                )
            self.configs.delete(
                tenant_id=tenant_id,
                provider_config_id=duplicate.id,
            )
        if canonical.enabled != canonical_enabled:
            self.configs.update_fields(
                tenant_id=tenant_id,
                provider_config_id=canonical.id,
                values={"enabled": canonical_enabled},
            )

    def _create_managed_sentence_transformer_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        display_name: str,
        supports_embeddings: bool,
        supports_reranking: bool,
        default_embedding_model: str | None,
        default_reranker_model: str | None,
        enabled: bool,
    ) -> ProviderConfig:
        row = ProviderConfig(
            tenant_id=tenant_id,
            workspace_id=None,
            owner_user_id=None,
            visibility_scope="system",
            provider_type=MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE,
            display_name=display_name,
            api_base_url=None,
            auth_mode="none",
            enabled=enabled,
            is_local=False,
            supports_chat=False,
            supports_embeddings=supports_embeddings,
            supports_reranking=supports_reranking,
            supports_model_listing=True,
            supports_model_install=False,
            default_chat_model=None,
            default_embedding_model=default_embedding_model,
            default_reranker_model=default_reranker_model,
            timeout_seconds=30,
            priority=100,
            metadata_json={"managed_by_averqel": True},
        )
        return self.configs.create(row)

    def _convert_mixed_provider_to_embeddings(
        self, *, tenant_id: uuid.UUID, provider: ProviderConfig
    ) -> ProviderConfig:
        self.configs.update_fields(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            values={
                "display_name": MANAGED_EMBEDDINGS_PROVIDER_NAME,
                "supports_embeddings": True,
                "supports_reranking": False,
                "default_reranker_model": None,
                "metadata_json": {
                    **dict(provider.metadata_json or {}),
                    "managed_by_averqel": True,
                },
            },
        )
        refreshed = self.get_provider(
            tenant_id=tenant_id, provider_config_id=provider.id
        )
        return refreshed

    def _ensure_split_reranker_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        source_provider: ProviderConfig,
        existing_reranker: ProviderConfig | None,
    ) -> ProviderConfig:
        if existing_reranker is not None:
            self.configs.update_fields(
                tenant_id=tenant_id,
                provider_config_id=existing_reranker.id,
                values={
                    "display_name": MANAGED_RERANKER_PROVIDER_NAME,
                    "supports_embeddings": False,
                    "supports_reranking": True,
                    "default_embedding_model": None,
                    "default_reranker_model": existing_reranker.default_reranker_model
                    or source_provider.default_reranker_model
                    or get_settings().reranking_model,
                    "enabled": source_provider.enabled,
                    "metadata_json": {
                        **dict(existing_reranker.metadata_json or {}),
                        "managed_by_averqel": True,
                    },
                },
            )
            return self.get_provider(
                tenant_id=tenant_id, provider_config_id=existing_reranker.id
            )

        return self._create_managed_sentence_transformer_provider(
            tenant_id=tenant_id,
            display_name=MANAGED_RERANKER_PROVIDER_NAME,
            supports_embeddings=False,
            supports_reranking=True,
            default_embedding_model=None,
            default_reranker_model=source_provider.default_reranker_model
            or get_settings().reranking_model,
            enabled=source_provider.enabled,
        )

    def _migrate_reranking_assignments(
        self,
        *,
        tenant_id: uuid.UUID,
        from_provider_id: uuid.UUID,
        to_provider_id: uuid.UUID,
        default_model_name: str | None,
    ) -> None:
        rows = list(
            self.assignments.list_for_provider(
                tenant_id=tenant_id,
                provider_config_id=from_provider_id,
                enabled_only=False,
            )
        )
        for row in rows:
            if row.feature_scope not in {"reranking", "fallback_reranking"}:
                continue
            self.assignments.update_fields(
                tenant_id=tenant_id,
                assignment_id=row.id,
                values={
                    "provider_config_id": to_provider_id,
                    "model_name": row.model_name or default_model_name,
                },
            )

    def _seed_managed_provider_model_cache(
        self, *, tenant_id: uuid.UUID, provider: ProviderConfig
    ) -> None:
        if provider.provider_type != MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE:
            return
        registry = ProviderRegistry(get_settings())
        discovery = registry.get_model_discovery_provider_from_config(provider)
        model_infos: list[ProviderModelInfo] = []
        if provider.supports_embeddings:
            model_infos.extend(list(discovery.list_embedding_models()))
        if provider.supports_reranking:
            model_infos.extend(list(discovery.list_reranker_models()))
        rows = [
            ProviderModelCache(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                model_name=model.name,
                model_kind=model.kind,
                display_name=model.display_name,
                context_window=model.context_window,
                capabilities_json=dict(model.capabilities),
                is_available=True,
            )
            for model in model_infos
        ]
        self.cache.upsert_models(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            models=rows,
        )
        seen = {(model.model_name, model.model_kind) for model in rows}
        self.cache.purge_stale_models(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            seen_names=seen,
        )

    def delete_or_disable_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> str:
        provider = self.get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )
        if (
            provider.owner_user_id is not None
            and provider.owner_user_id != actor_user_id
        ):
            raise ApiError(
                code="PROVIDER_CONFIG_NOT_FOUND",
                message="Provider configuration not found.",
                status_code=404,
            )
        is_managed_builtin = self._is_managed_sentence_transformer_provider(provider)
        provider_assignments = list(
            self.assignments.list_for_provider(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
                enabled_only=False,
            )
        )
        active_assignments = [
            assignment for assignment in provider_assignments if assignment.enabled
        ]
        if active_assignments:
            replacement = self._find_replacement_provider(
                tenant_id=tenant_id,
                provider=provider,
            )
            if replacement is not None:
                for assignment in active_assignments:
                    migrated_model_name = assignment.model_name
                    if assignment.feature_scope == "chat":
                        migrated_model_name = (
                            replacement.default_chat_model or migrated_model_name
                        )
                    elif assignment.feature_scope == "embeddings":
                        migrated_model_name = (
                            replacement.default_embedding_model or migrated_model_name
                        )
                    self.assignments.update_fields(
                        tenant_id=tenant_id,
                        assignment_id=assignment.id,
                        values={
                            "provider_config_id": replacement.id,
                            "model_name": migrated_model_name,
                            "enabled": True,
                            "priority": replacement.priority,
                        },
                    )
                    self.audit.write_event(
                        tenant_id=tenant_id,
                        actor_user_id=actor_user_id,
                        action="provider.assignment.migrate",
                        resource_type="provider_assignment",
                        resource_id=str(assignment.id),
                        details={
                            "from_provider_config_id": str(provider.id),
                            "to_provider_config_id": str(replacement.id),
                            "feature_scope": assignment.feature_scope,
                        },
                    )
                provider_assignments = [
                    assignment
                    for assignment in provider_assignments
                    if assignment.id not in {active.id for active in active_assignments}
                ]

        for assignment in provider_assignments:
            deleted = self.assignments.delete(
                tenant_id=tenant_id,
                assignment_id=assignment.id,
            )
            if not deleted:
                continue
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.assignment.delete",
                resource_type="provider_assignment",
                resource_id=str(assignment.id),
                details={
                    "feature_scope": assignment.feature_scope,
                    "provider_config_id": str(provider.id),
                    "reason": "provider_deleted",
                },
            )

        if is_managed_builtin:
            self.configs.disable(
                tenant_id=tenant_id,
                provider_config_id=provider.id,
            )
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.config.disable",
                resource_type="provider_config",
                resource_id=str(provider.id),
                details={"reason": "managed_provider_delete_requested"},
            )
            return "disabled"

        self.secrets.disconnect_provider(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            actor_user_id=actor_user_id,
        )
        self.configs.delete(tenant_id=tenant_id, provider_config_id=provider.id)
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.config.delete",
            resource_type="provider_config",
            resource_id=str(provider.id),
            details={},
        )
        return "deleted"

    def _is_managed_sentence_transformer_provider(
        self, provider: ProviderConfig
    ) -> bool:
        if provider.provider_type != MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE:
            return False
        metadata = dict(provider.metadata_json or {})
        if metadata.get("managed_by_averqel") is True:
            return True
        return provider.workspace_id is None and provider.display_name in {
            MANAGED_EMBEDDINGS_PROVIDER_NAME,
            MANAGED_RERANKER_PROVIDER_NAME,
        }

    def _find_replacement_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: ProviderConfig,
    ) -> ProviderConfig | None:
        candidates = self.configs.list_by_workspace(
            tenant_id=tenant_id,
            workspace_id=provider.workspace_id,
            owner_user_id=provider.owner_user_id,
        )
        for candidate in candidates:
            if candidate.id == provider.id or not candidate.enabled:
                continue
            if (
                provider.visibility_scope == "user"
                and candidate.owner_user_id != provider.owner_user_id
            ):
                continue
            if (
                provider.visibility_scope != "user"
                and candidate.visibility_scope == "user"
            ):
                continue
            if candidate.provider_type != provider.provider_type:
                continue
            if (candidate.api_base_url or "") != (provider.api_base_url or ""):
                continue
            return candidate
        return None

    def list_masked_secrets(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> list[MaskedProviderSecret]:
        secret_types = self.secrets.repo.list_secret_types_for_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
        )
        results: list[MaskedProviderSecret] = []
        for secret_type in secret_types:
            masked = self.secrets.get_masked_secret(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                secret_type=secret_type,
            )
            if masked is not None:
                results.append(masked)
        return results

    def create_assignment(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        feature_scope: str,
        provider_config_id: uuid.UUID,
        model_name: str | None,
        enabled: bool,
        priority: int,
    ) -> ProviderAssignment:
        provider = self.get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )
        self._validate_assignment(feature_scope=feature_scope, provider=provider)
        resolved_model_name = self._resolve_assignment_model_name(
            provider=provider,
            feature_scope=feature_scope,
            model_name=model_name,
        )
        self._validate_embedding_assignment(
            tenant_id=tenant_id,
            provider=provider,
            feature_scope=feature_scope,
            model_name=resolved_model_name,
        )
        assignment = self.assignments.upsert_assignment(
            ProviderAssignment(
                tenant_id=tenant_id,
                workspace_id=None,
                owner_user_id=actor_user_id,
                visibility_scope="user",
                feature_scope=feature_scope,
                provider_config_id=provider_config_id,
                model_name=resolved_model_name,
                enabled=enabled,
                priority=priority,
            )
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.assignment.upsert",
            resource_type="provider_assignment",
            resource_id=str(assignment.id),
            details={
                "feature_scope": feature_scope,
                "provider_config_id": str(provider_config_id),
            },
        )
        return assignment

    def list_assignments(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
    ) -> list[ProviderAssignment]:
        self._ensure_managed_sentence_transformer_providers(tenant_id=tenant_id)
        rows = list(
            self.assignments.list_assignments(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_user_id=actor_user_id,
            )
        )
        if workspace_id is not None:
            tenant_rows = [
                row
                for row in self.assignments.list_assignments(
                    tenant_id=tenant_id,
                    workspace_id=None,
                    owner_user_id=actor_user_id,
                )
                if row.id not in {item.id for item in rows}
            ]
            rows.extend(tenant_rows)
        return rows

    def update_assignment(
        self,
        *,
        tenant_id: uuid.UUID,
        assignment_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        values: dict[str, object],
    ) -> ProviderAssignment:
        assignment = self.assignments.get_by_id(
            tenant_id=tenant_id, assignment_id=assignment_id
        )
        if assignment is None:
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Provider assignment not found.",
                status_code=404,
            )
        if (
            assignment.owner_user_id is not None
            and assignment.owner_user_id != actor_user_id
        ):
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Provider assignment not found.",
                status_code=404,
            )
        if "provider_config_id" in values:
            provider_id = values["provider_config_id"]
            if not isinstance(provider_id, uuid.UUID):
                raise ApiError(
                    code="PROVIDER_ASSIGNMENT_INVALID",
                    message="Provider assignment references an invalid provider.",
                    status_code=400,
                )
            provider = self.get_provider(
                tenant_id=tenant_id,
                provider_config_id=provider_id,
                actor_user_id=actor_user_id,
            )
            self._validate_assignment(
                feature_scope=assignment.feature_scope, provider=provider
            )
        else:
            provider = self.get_provider(
                tenant_id=tenant_id,
                provider_config_id=assignment.provider_config_id,
                actor_user_id=actor_user_id,
            )

        resolved_model_name = self._resolve_assignment_model_name(
            provider=provider,
            feature_scope=assignment.feature_scope,
            model_name=values.get("model_name", assignment.model_name),
        )
        self._validate_embedding_assignment(
            tenant_id=tenant_id,
            provider=provider,
            feature_scope=assignment.feature_scope,
            model_name=resolved_model_name,
        )
        if "model_name" in values or "provider_config_id" in values:
            values["model_name"] = resolved_model_name
        self.assignments.update_fields(
            tenant_id=tenant_id,
            assignment_id=assignment_id,
            values=values,
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.assignment.update",
            resource_type="provider_assignment",
            resource_id=str(assignment_id),
            details={"updated_fields": ",".join(sorted(values.keys()))},
        )
        refreshed = self.assignments.get_by_id(
            tenant_id=tenant_id, assignment_id=assignment_id
        )
        if refreshed is None:  # pragma: no cover - defensive
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Provider assignment update could not be reloaded.",
                status_code=500,
            )
        return refreshed

    def delete_assignment(
        self,
        *,
        tenant_id: uuid.UUID,
        assignment_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> bool:
        assignment = self.assignments.get_by_id(
            tenant_id=tenant_id, assignment_id=assignment_id
        )
        if assignment is None:
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Provider assignment not found.",
                status_code=404,
            )
        if (
            assignment.owner_user_id is not None
            and assignment.owner_user_id != actor_user_id
        ):
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Provider assignment not found.",
                status_code=404,
            )
        deleted = self.assignments.delete(
            tenant_id=tenant_id,
            assignment_id=assignment_id,
        )
        if deleted:
            self.audit.write_event(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="provider.assignment.delete",
                resource_type="provider_assignment",
                resource_id=str(assignment_id),
                details={"feature_scope": assignment.feature_scope},
            )
        return deleted

    def disconnect_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> int:
        provider = self.get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )
        if (
            provider.owner_user_id is not None
            and provider.owner_user_id != actor_user_id
        ):
            raise ApiError(
                code="PROVIDER_CONFIG_NOT_FOUND",
                message="Provider configuration not found.",
                status_code=404,
            )
        revoked_count = self.secrets.disconnect_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )
        self.configs.disable(tenant_id=tenant_id, provider_config_id=provider_config_id)
        self.audit.write_event(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="provider.config.disconnect",
            resource_type="provider_config",
            resource_id=str(provider_config_id),
            details={"revoked_secret_count": str(revoked_count)},
        )
        return revoked_count

    def rotate_secret(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        secret_type: str,
        secret_value: str,
        actor_user_id: uuid.UUID,
    ) -> None:
        provider = self.get_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )
        if (
            provider.owner_user_id is not None
            and provider.owner_user_id != actor_user_id
        ):
            raise ApiError(
                code="PROVIDER_CONFIG_NOT_FOUND",
                message="Provider configuration not found.",
                status_code=404,
            )
        allowed_types = ALLOWED_SECRET_TYPES_BY_AUTH_MODE.get(
            provider.auth_mode, frozenset()
        )
        if secret_type not in allowed_types:
            raise ApiError(
                code="PROVIDER_AUTH_MODE_NOT_ALLOWED",
                message="Secret type is not allowed for this provider auth mode.",
                status_code=400,
            )
        try:
            self.secrets.upsert_secret(
                tenant_id=tenant_id,
                provider_config_id=provider_config_id,
                secret_type=secret_type,
                secret_value=secret_value,
                actor_user_id=actor_user_id,
            )
        except ProviderSecretCryptoError as exc:
            raise ApiError(
                code="PROVIDER_SECRET_STORAGE_UNAVAILABLE",
                message="Provider secret encryption is not configured.",
                status_code=503,
            ) from exc

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

    def _validate_provider_definition(
        self,
        *,
        provider_type: str,
        api_base_url: str | None,
        auth_mode: str,
        supports_chat: bool,
        supports_embeddings: bool,
        supports_reranking: bool,
        supports_model_listing: bool,
        supports_model_install: bool,
        is_local: bool,
        api_key: str | None,
        existing_auth_mode: str | None = None,
    ) -> None:
        catalog = SUPPORTED_PROVIDER_CATALOG.get(provider_type)
        if catalog is None:
            raise ApiError(
                code="PROVIDER_UNSUPPORTED_TYPE",
                message="Provider type is not supported.",
                status_code=400,
            )
        auth_modes = catalog.get("auth_modes")
        if not isinstance(auth_modes, list) or any(
            not isinstance(item, str) for item in auth_modes
        ):
            raise ApiError(
                code="PROVIDER_UNSUPPORTED_TYPE",
                message="Provider catalog is misconfigured.",
                status_code=500,
            )
        if auth_mode not in auth_modes:
            raise ApiError(
                code="PROVIDER_AUTH_MODE_NOT_ALLOWED",
                message="Authentication mode is not allowed for this provider.",
                status_code=400,
            )
        if api_base_url:
            parsed = urlparse(api_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ApiError(
                    code="PROVIDER_ASSIGNMENT_INVALID",
                    message="Provider base URL must be a valid http or https URL.",
                    status_code=400,
                )
        if auth_mode == "api_key" and existing_auth_mode != "api_key" and not api_key:
            raise ApiError(
                code="PROVIDER_SECRET_REQUIRED",
                message="An API key is required for this provider.",
                status_code=400,
            )
        if auth_mode != "api_key" and api_key:
            raise ApiError(
                code="PROVIDER_AUTH_MODE_NOT_ALLOWED",
                message="API keys are only allowed when auth mode is api_key.",
                status_code=400,
            )
        expected_local = bool(catalog["is_local"])
        if expected_local != is_local:
            raise ApiError(
                code="PROVIDER_UNSUPPORTED_TYPE",
                message="Provider locality does not match the supported provider type.",
                status_code=400,
            )
        if is_local and auth_mode not in auth_modes:
            raise ApiError(
                code="PROVIDER_AUTH_MODE_NOT_ALLOWED",
                message="Authentication mode is not allowed for this local provider.",
                status_code=400,
            )
        if is_local and auth_mode not in {"local_no_key", "api_key"}:
            raise ApiError(
                code="PROVIDER_AUTH_MODE_NOT_ALLOWED",
                message="Local providers must use a supported local authentication mode.",
                status_code=400,
            )
        if provider_type == MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE:
            if supports_chat:
                raise ApiError(
                    code="PROVIDER_UNSUPPORTED_TYPE",
                    message="Sentence-transformers providers do not support chat.",
                    status_code=400,
                )
            if not supports_embeddings and not supports_reranking:
                raise ApiError(
                    code="PROVIDER_UNSUPPORTED_TYPE",
                    message="Sentence-transformers providers must support embeddings or reranking.",
                    status_code=400,
                )
            for field_name, value in {
                "supports_model_listing": supports_model_listing,
                "supports_model_install": supports_model_install,
                "is_local": is_local,
            }.items():
                if bool(catalog[field_name]) != value:
                    raise ApiError(
                        code="PROVIDER_UNSUPPORTED_TYPE",
                        message=f"Provider capability mismatch for {field_name}.",
                        status_code=400,
                    )
            return
        for field_name, value in {
            "supports_chat": supports_chat,
            "supports_embeddings": supports_embeddings,
            "supports_reranking": supports_reranking,
            "supports_model_listing": supports_model_listing,
            "supports_model_install": supports_model_install,
            "is_local": is_local,
        }.items():
            if bool(catalog[field_name]) != value:
                raise ApiError(
                    code="PROVIDER_UNSUPPORTED_TYPE",
                    message=f"Provider capability mismatch for {field_name}.",
                    status_code=400,
                )

    @staticmethod
    def _validate_assignment(*, feature_scope: str, provider: ProviderConfig) -> None:
        if not provider.enabled:
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Disabled providers cannot be assigned.",
                status_code=400,
            )
        if feature_scope in {"chat", "fallback_chat"} and not provider.supports_chat:
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Selected provider does not support chat.",
                status_code=400,
            )
        if (
            feature_scope in {"embeddings", "fallback_embeddings"}
            and not provider.supports_embeddings
        ):
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Selected provider does not support embeddings.",
                status_code=400,
            )
        if (
            feature_scope in {"reranking", "fallback_reranking"}
            and not provider.supports_reranking
        ):
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Selected provider does not support reranking.",
                status_code=400,
            )
        if (
            feature_scope in {"web_search", "fallback_web_search"}
            and provider.provider_type != "tavily"
        ):
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Selected provider does not support web search.",
                status_code=400,
            )

    @staticmethod
    def _resolve_assignment_model_name(
        *,
        provider: ProviderConfig,
        feature_scope: str,
        model_name: object,
    ) -> str | None:
        resolved = model_name if isinstance(model_name, str) and model_name else None
        if resolved is not None:
            return resolved
        if feature_scope in {"embeddings", "fallback_embeddings"}:
            return provider.default_embedding_model
        if feature_scope in {"reranking", "fallback_reranking"}:
            return provider.default_reranker_model
        if feature_scope in {"chat", "fallback_chat"}:
            return provider.default_chat_model
        if feature_scope in {"web_search", "fallback_web_search"}:
            return None
        return None

    def _validate_embedding_assignment(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: ProviderConfig,
        feature_scope: str,
        model_name: str | None,
    ) -> None:
        if feature_scope not in {"embeddings", "fallback_embeddings"} or not model_name:
            return

        settings = get_settings()
        expected_dimension = settings.embedding_dimension
        cached_model = self.cache.get_model(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            model_name=model_name,
            model_kind="embedding",
        )

        cached_dimension: int | None = None
        if cached_model is not None:
            raw_dimension = cached_model.capabilities_json.get("embedding_dimension")
            if isinstance(raw_dimension, int) and raw_dimension > 0:
                cached_dimension = raw_dimension

        static_dimension: int | None = None
        if provider.provider_type == MANAGED_SENTENCE_TRANSFORMERS_PROVIDER_TYPE:
            static_dimension = (
                SentenceTransformersEmbeddingProvider.get_embedding_dimension(
                    model_name
                )
            )

        discovered_dimension = (
            cached_dimension
            or static_dimension
            or self._probe_embedding_dimension(
                tenant_id=tenant_id,
                provider=provider,
                model_name=model_name,
            )
        )
        if cached_model is not None and discovered_dimension != cached_dimension:
            cached_model.capabilities_json = {
                **dict(cached_model.capabilities_json or {}),
                "embedding_dimension": discovered_dimension,
            }

        if discovered_dimension != expected_dimension:
            raise ApiError(
                code="EMBEDDING_DIMENSION_MISMATCH",
                message=(
                    f'Selected embedding model "{model_name}" is incompatible with this '
                    f"workspace. Expected {expected_dimension} dimensions, got "
                    f"{discovered_dimension}."
                ),
                status_code=400,
            )

    def _probe_embedding_dimension(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: ProviderConfig,
        model_name: str,
    ) -> int:
        settings = get_settings()
        api_key = self._resolve_secret_value(
            tenant_id=tenant_id,
            provider_config_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        provider_client = ProviderRegistry(
            settings
        ).get_embedding_provider_from_selection(
            ProviderSelectionCandidate(
                provider_type=provider.provider_type,
                model_name=model_name,
                feature_scope="embeddings",
                source="tenant",
                provider_config_id=provider.id,
                tenant_id=tenant_id,
                workspace_id=provider.workspace_id,
                base_url=provider.api_base_url,
                api_key=api_key,
                auth_mode=provider.auth_mode,
                priority=provider.priority,
            )
        )
        try:
            response = provider_client.embed_many(
                EmbeddingRequest(
                    texts=["dimension probe"],
                    model=model_name,
                    batch_size=1,
                    normalize=settings.embedding_normalize,
                    dimension=settings.embedding_dimension,
                    timeout_seconds=min(provider.timeout_seconds, 15),
                    provider_name=provider.provider_type,
                    metadata={
                        "base_url": provider.api_base_url,
                        "api_key": api_key,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message=(
                    f'Unable to validate embedding model "{model_name}". Refresh the '
                    "provider models or choose a different embedding model."
                ),
                status_code=400,
            ) from exc

        if not response.vectors or not response.vectors[0]:
            raise ApiError(
                code="PROVIDER_ASSIGNMENT_INVALID",
                message="Selected embedding model did not return a probe vector.",
                status_code=400,
            )
        return len(response.vectors[0])

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
