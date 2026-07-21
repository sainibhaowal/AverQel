from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MaskedProviderSecretResponse(BaseModel):
    secret_type: str
    masked_value: str
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ProviderRotateSecretRequest(BaseModel):
    secret_type: str = "api_key"
    secret_value: str

    model_config = ConfigDict(extra="forbid")


class ProviderDisconnectResponse(BaseModel):
    provider_id: str
    revoked_secret_count: int

    model_config = ConfigDict(extra="forbid")
