from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class ProviderOAuthStartRequest(BaseModel):
    provider_type: str = "openai"

    model_config = ConfigDict(extra="forbid")

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned != "openai":
            raise ValueError("provider_type must be openai")
        return cleaned


class ProviderOAuthStartResponse(BaseModel):
    available: bool
    authorization_url: str | None = None
    message: str

    model_config = ConfigDict(extra="forbid")


class ProviderOAuthCallbackResponse(BaseModel):
    connected: bool
    message: str

    model_config = ConfigDict(extra="forbid")


class ProviderOAuthStatusResponse(BaseModel):
    available: bool
    connected: bool
    provider_type: str
    message: str

    model_config = ConfigDict(extra="forbid")
