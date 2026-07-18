from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.providers.common import ProviderSummaryMixin
from app.schemas.providers.health import ProviderHealthResponse
from app.schemas.providers.secrets import MaskedProviderSecretResponse


class ProviderConfigCreateRequest(BaseModel):
    workspace_id: UUID | None = None
    provider_type: str
    display_name: str
    api_base_url: str | None = None
    auth_mode: str
    enabled: bool = True
    is_local: bool = False
    supports_chat: bool = False
    supports_embeddings: bool = False
    supports_reranking: bool = False
    supports_web_search: bool = False
    supports_model_listing: bool = False
    supports_model_install: bool = False
    default_chat_model: str | None = None
    default_embedding_model: str | None = None
    default_reranker_model: str | None = None
    timeout_seconds: int = 30
    priority: int = 100
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "provider_type",
        "display_name",
        "auth_mode",
        "api_base_url",
        "default_chat_model",
        "default_embedding_model",
        "default_reranker_model",
        "api_key",
        mode="before",
    )
    @classmethod
    def trim_optional_strings(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip().replace("`", "")
            return cleaned or None
        return value

    @field_validator("provider_type", "display_name", "auth_mode")
    @classmethod
    def require_non_empty_strings(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("value must not be empty")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_seconds must be positive")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: int) -> int:
        if value < 0:
            raise ValueError("priority must be greater than or equal to 0")
        return value

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("api_base_url must be a valid http/https URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_auth_secret_requirements(self) -> ProviderConfigCreateRequest:
        if self.workspace_id is not None:
            raise ValueError(
                "workspace-scoped providers are disabled; providers are personal to each user"
            )
        if self.auth_mode == "api_key" and not self.api_key:
            raise ValueError("api_key is required when auth_mode=api_key")
        if self.auth_mode in {"local_no_key", "none"} and self.api_key:
            raise ValueError("api_key is not allowed for the selected auth_mode")
        return self


class ProviderConfigUpdateRequest(BaseModel):
    display_name: str | None = None
    api_base_url: str | None = None
    enabled: bool | None = None
    default_chat_model: str | None = None
    default_embedding_model: str | None = None
    default_reranker_model: str | None = None
    timeout_seconds: int | None = None
    priority: int | None = None
    metadata_json: dict[str, Any] | None = None
    api_key: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "display_name",
        "api_base_url",
        "default_chat_model",
        "default_embedding_model",
        "default_reranker_model",
        "api_key",
        mode="before",
    )
    @classmethod
    def trim_update_strings(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip().replace("`", "")
            return cleaned or None
        return value

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("display_name must not be empty")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_update_timeout_seconds(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be positive")
        return value

    @field_validator("priority")
    @classmethod
    def validate_update_priority(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("priority must be greater than or equal to 0")
        return value

    @field_validator("api_base_url")
    @classmethod
    def validate_update_api_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("api_base_url must be a valid http/https URL")
        return value.rstrip("/")


class ProviderConfigResponse(ProviderSummaryMixin):
    secrets: list[MaskedProviderSecretResponse] = Field(default_factory=list)
    latest_health: ProviderHealthResponse | None = None


class ProviderConfigListResponse(BaseModel):
    items: list[ProviderConfigResponse]

    model_config = ConfigDict(extra="forbid")


class ProviderDeleteResponse(BaseModel):
    provider_id: UUID
    status: str

    model_config = ConfigDict(extra="forbid")
