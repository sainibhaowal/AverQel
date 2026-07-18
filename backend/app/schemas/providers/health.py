from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderHealthResponse(BaseModel):
    status: str
    latency_ms: int | None = None
    http_status: int | None = None
    error_code: str | None = None
    error_message_redacted: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class ProviderTestResponse(ProviderHealthResponse):
    provider_id: str | None = None
