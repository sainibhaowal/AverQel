from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProviderCatalogEntry(BaseModel):
    provider_type: str
    display_name: str
    auth_modes: list[str]
    supports_chat: bool
    supports_embeddings: bool
    supports_reranking: bool
    supports_web_search: bool = False
    supports_model_listing: bool
    supports_model_install: bool
    supports_account_linking: bool
    is_local: bool

    model_config = ConfigDict(extra="forbid")


class ProviderCatalogResponse(BaseModel):
    items: list[ProviderCatalogEntry]

    model_config = ConfigDict(extra="forbid")


class ProviderSummaryMixin(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None = None
    owner_user_id: UUID | None = None
    visibility_scope: str = "user"
    provider_type: str
    display_name: str
    api_base_url: str | None = None
    auth_mode: str
    enabled: bool
    is_local: bool
    supports_chat: bool
    supports_embeddings: bool
    supports_reranking: bool
    supports_web_search: bool = False
    supports_model_listing: bool
    supports_model_install: bool
    default_chat_model: str | None = None
    default_embedding_model: str | None = None
    default_reranker_model: str | None = None
    timeout_seconds: int
    priority: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")
