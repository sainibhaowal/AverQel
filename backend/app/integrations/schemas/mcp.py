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
        """Expose only catalog metadata; never serialize arbitrary server JSON."""
        allowed = {
            "server_url",
            "oauth_mode",
            "auth_type",
            "transport",
            "vendor_slug",
            "registry_entry_id",
            "source",
            "categories",
            "mcp_tools_cache",
            "mcp_prompts_cache",
            "mcp_resources_cache",
            "mcp_resource_templates_cache",
            "mcp_catalog_tool_count",
            "mcp_catalog_last_sync_at",
            "catalog_revision",
        }
        if not isinstance(value, dict):
            return {}
        return {key: value[key] for key in allowed if key in value}


class MCPCatalogReviewRequest(BaseModel):
    status: Literal["approved", "rejected", "discovered"]
    verification_source: str = Field(min_length=1, max_length=500)
    popularity_rank: int | None = Field(default=None, ge=1, le=1_000_000)
