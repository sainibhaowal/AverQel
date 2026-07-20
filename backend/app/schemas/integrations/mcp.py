"""Schemas for MCP server API responses and catalog review."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class MCPServerRead(BaseModel):
    id: uuid.UUID
    name: str
    transport: str
    config: dict[str, Any]
    enabled: bool
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    last_error: str | None
    reconnect_attempts: int

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("config")
    def serialize_safe_config(self, value: dict[str, Any]) -> dict[str, Any]:
        """Never expose OAuth material or PKCE state to browser clients."""
        sensitive = {
            "access_token", "refresh_token", "token", "client_secret",
            "secret", "password", "authorization", "code", "code_verifier",
            "oauth_pending",
        }

        def redact(item: Any, key: str = "") -> Any:
            if key.lower() in sensitive or any(marker in key.lower() for marker in ("token", "secret", "verifier", "key")):
                return "[REDACTED]"
            if isinstance(item, dict):
                return {str(k): redact(v, str(k)) for k, v in item.items()}
            if isinstance(item, list):
                return [redact(v, key) for v in item]
            return item

        return redact(value) if isinstance(value, dict) else {}


class MCPCatalogReviewRequest(BaseModel):
    status: Literal["approved", "rejected", "discovered"]
    verification_source: str = Field(min_length=1, max_length=500)
    popularity_rank: int | None = Field(default=None, ge=1, le=1_000_000)
