from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderModelResponse(BaseModel):
    id: UUID | None = None
    provider_config_id: UUID | None = None
    model_name: str
    model_kind: str
    display_name: str | None = None
    context_window: int | None = None
    capabilities_json: dict[str, Any] = Field(default_factory=dict)
    is_available: bool = True
    last_seen_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class ProviderModelListResponse(BaseModel):
    items: list[ProviderModelResponse]

    model_config = ConfigDict(extra="forbid")


class ProviderModelPreviewRequest(BaseModel):
    workspace_id: UUID | None = None
    provider_type: str
    api_base_url: str | None = None
    auth_mode: str
    supports_chat: bool = False
    supports_embeddings: bool = False
    supports_reranking: bool = False
    supports_model_listing: bool = False
    api_key: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "provider_type", "api_base_url", "auth_mode", "api_key", mode="before"
    )
    @classmethod
    def trim_strings(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = (
                value.replace("\u200b", "")
                .replace("\u200c", "")
                .replace("\u200d", "")
                .replace("\u2060", "")
                .replace("\ufeff", "")
                .strip()
                .replace("`", "")
            )
            return cleaned or None
        return value

    @field_validator("provider_type", "auth_mode")
    @classmethod
    def require_non_empty_strings(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("value must not be empty")
        return value

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("api_base_url must be a valid http/https URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_auth_secret_requirements(self) -> ProviderModelPreviewRequest:
        if not self.supports_model_listing:
            raise ValueError("supports_model_listing must be true for model preview")
        if self.auth_mode == "api_key" and not self.api_key:
            raise ValueError("api_key is required when auth_mode=api_key")
        if self.auth_mode in {"local_no_key", "none"} and self.api_key:
            raise ValueError("api_key is not allowed for the selected auth_mode")
        return self


class ProviderModelPullRequest(BaseModel):
    model_name: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model_name must not be empty")
        return cleaned


class ProviderModelPullResponse(BaseModel):
    status: str
    message: str

    model_config = ConfigDict(extra="forbid")
