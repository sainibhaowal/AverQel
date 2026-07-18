from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ALLOWED_PROVIDER_FEATURE_SCOPES = {
    "chat",
    "embeddings",
    "reranking",
    "vision",
    "fallback_chat",
    "fallback_embeddings",
    "fallback_reranking",
    "web_search",
    "fallback_web_search",
}


class ProviderAssignmentCreateRequest(BaseModel):
    workspace_id: UUID | None = None
    feature_scope: str
    provider_config_id: UUID
    model_name: str | None = None
    enabled: bool = True
    priority: int = 100

    model_config = ConfigDict(extra="forbid")

    @field_validator("feature_scope")
    @classmethod
    def validate_feature_scope(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in ALLOWED_PROVIDER_FEATURE_SCOPES:
            raise ValueError(
                f"feature_scope must be one of {sorted(ALLOWED_PROVIDER_FEATURE_SCOPES)}"
            )
        return cleaned

    @field_validator("model_name", mode="before")
    @classmethod
    def trim_model_name(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: int) -> int:
        if value < 0:
            raise ValueError("priority must be greater than or equal to 0")
        return value

    @model_validator(mode="after")
    def validate_personal_scope(self) -> ProviderAssignmentCreateRequest:
        if self.workspace_id is not None:
            raise ValueError(
                "workspace-scoped provider assignments are disabled; assignments are personal to each user"
            )
        return self


class ProviderAssignmentUpdateRequest(BaseModel):
    provider_config_id: UUID | None = None
    model_name: str | None = None
    enabled: bool | None = None
    priority: int | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("model_name", mode="before")
    @classmethod
    def trim_update_model_name(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("priority")
    @classmethod
    def validate_update_priority(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("priority must be greater than or equal to 0")
        return value


class ProviderAssignmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    workspace_id: UUID | None = None
    owner_user_id: UUID | None = None
    visibility_scope: str = "user"
    feature_scope: str
    provider_config_id: UUID
    model_name: str | None = None
    enabled: bool
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProviderAssignmentListResponse(BaseModel):
    items: list[ProviderAssignmentResponse]

    model_config = ConfigDict(extra="forbid")
