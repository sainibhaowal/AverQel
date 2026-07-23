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
    registry_entry_id: uuid.UUID | None = None
    provider_slug: str | None = None
    account_identity: dict[str, Any] = Field(default_factory=dict)
    connection_policy_id: uuid.UUID | None = None
    catalog_revision: int = 0
    status: str
    last_error: str | None
    reconnect_attempts: int

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("account_identity")
    def serialize_safe_account_identity(self, value: dict[str, Any]) -> dict[str, Any]:
        """Expose only non-secret account labels; never identity credentials."""
        if not isinstance(value, dict):
            return {}
        allowed = {"email", "display_name", "provider_subject", "account_id"}
        return {
            key: value[key]
            for key in allowed
            if key in value and isinstance(value[key], str | int)
        }

    @field_serializer("config")
    def serialize_safe_config(self, value: dict[str, Any]) -> dict[str, Any]:
        """Expose only catalog metadata; never serialize arbitrary server JSON."""
        allowed = {
            "server_url",
            "oauth_mode",
            "auth_type",
            "transport",
            "provider_slug",
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


MCPToolMode = Literal["always_allow", "needs_approval", "blocked"]
MCPRiskCeiling = Literal["read", "write", "delete", "external_message"]


class MCPConnectionPolicyRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    server_id: uuid.UUID
    allowed_tools: list[str]
    denied_tools: list[str]
    read_only: bool
    risk_ceiling: MCPRiskCeiling
    approval_rules: dict[str, MCPToolMode]
    tool_modes: dict[str, MCPToolMode]
    default_enabled: bool
    deepspace_overrides: dict[str, bool]
    conversation_overrides: dict[str, bool]
    created_at: Any
    updated_at: Any

    model_config = ConfigDict(from_attributes=True)


class MCPConnectionPolicyUpdate(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list, max_length=1000)
    denied_tools: list[str] = Field(default_factory=list, max_length=1000)
    read_only: bool = True
    risk_ceiling: MCPRiskCeiling = "read"
    approval_rules: dict[str, MCPToolMode] = Field(default_factory=dict)
    tool_modes: dict[str, MCPToolMode] = Field(default_factory=dict)
    default_enabled: bool = False
    deepspace_overrides: dict[str, bool] = Field(default_factory=dict)
    conversation_overrides: dict[str, bool] = Field(default_factory=dict)
