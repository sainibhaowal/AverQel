"""Schemas for MCP server API responses and catalog review."""

import uuid
from datetime import datetime
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
    granted_scopes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("account_identity")
    def serialize_safe_account_identity(self, value: dict[str, Any]) -> dict[str, Any]:
        """Expose only non-secret account labels; never identity credentials."""
        if not isinstance(value, dict):
            return {}
        allowed = {"email", "display_name", "provider_subject", "account_id", "identity_source"}
        return {
            key: value[key] for key in allowed if key in value and isinstance(value[key], str | int)
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

    @field_serializer("last_error")
    def serialize_safe_last_error(self, value: str | None) -> str | None:
        """Never return endpoint, provider, or transport error details."""
        return "MCP connection failed" if value else None


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
    default_tool_mode: MCPToolMode
    default_enabled: bool
    deepspace_overrides: dict[str, bool]
    conversation_overrides: dict[str, bool]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MCPConnectionPolicyUpdate(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list, max_length=1000)
    denied_tools: list[str] = Field(default_factory=list, max_length=1000)
    read_only: bool = True
    risk_ceiling: MCPRiskCeiling = "read"
    approval_rules: dict[str, MCPToolMode] = Field(default_factory=dict)
    tool_modes: dict[str, MCPToolMode] = Field(default_factory=dict)
    default_tool_mode: MCPToolMode = "needs_approval"
    default_enabled: bool = False
    deepspace_overrides: dict[str, bool] = Field(default_factory=dict)
    conversation_overrides: dict[str, bool] = Field(default_factory=dict)


class MCPHealthRead(BaseModel):
    status: str
    last_checked_at: datetime | None = None
    detail: str | None = None


class MCPMarketplaceToolPreviewRead(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    risk_labels: list[str] = Field(default_factory=list)


class MCPMarketplaceConnectionOptionRead(BaseModel):
    transport: str
    url: str | None = None
    security_schemes: dict[str, Any] = Field(default_factory=dict)


class MCPMarketplaceEntryRead(BaseModel):
    id: uuid.UUID
    name: str
    version: str | None = None
    server_name: str
    publisher: str | None = None
    description: str | None = None
    transport: str | None = None
    remote_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    official: bool
    verified: bool
    source: str
    oauth_requirements: dict[str, Any] = Field(default_factory=dict)
    package_metadata: dict[str, Any] = Field(default_factory=dict)
    action: Literal["connect", "install"]
    logo_url: str | None = None
    tool_count: int = 0
    last_catalog_sync_at: datetime | None = None
    verification_reason: str | None = None
    last_seen_at: datetime
    docs_url: str | None = None
    connection_options: list[MCPMarketplaceConnectionOptionRead] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    tool_preview: list[MCPMarketplaceToolPreviewRead] = Field(default_factory=list)
    tools: list[MCPMarketplaceToolPreviewRead] = Field(default_factory=list)
    catalog_status: str
    auth_type: str
    trust_status: str
    verification_source: str | None = None
    popularity_rank: int | None = None
    provider_slug: str | None = None
    publisher_type: Literal["official", "community"] | None = None
    author_name: str | None = None
    author_website_url: str | None = None
    support_url: str | None = None
    privacy_policy_url: str | None = None
    badges: dict[str, bool] = Field(default_factory=dict)
    availability: str | None = None
    trusted_logo_key: str | None = None
    supported_products: list[str] = Field(default_factory=list)
    tool_categories: list[str] = Field(default_factory=list)
    risk_policy: dict[str, Any] = Field(default_factory=dict)
    health: MCPHealthRead
    reviewed_at: datetime | None = None
    review_due_at: datetime | None = None
    requested_scopes: list[str] = Field(default_factory=list)
    scope_mode: str | None = None
    scope_note: str | None = None
    connectable: bool
    connectability_reason: str | None = None


class MCPMarketplacePageRead(BaseModel):
    items: list[MCPMarketplaceEntryRead]
    page: int
    page_size: int
    total: int
    pages: int


class MCPMarketplaceFacetsRead(BaseModel):
    categories: list[str]
    transports: list[str]
    auth_types: list[str]
    trust_statuses: list[str]


class MCPConnectionCreateResponse(BaseModel):
    server: MCPServerRead
    authorization_url: str | None = None
    setup_required: bool = False


class MCPActionResponse(BaseModel):
    status: Literal["scheduled", "connected"]
    server_id: uuid.UUID


class MCPOAuthStartResponse(BaseModel):
    authorization_url: str


class MCPConnectionRead(MCPServerRead):
    policy: MCPConnectionPolicyRead | None = None


class MCPToolPolicyUpdate(BaseModel):
    mode: MCPToolMode


class MCPToolRead(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    risk_labels: list[str] = Field(default_factory=list)
    mode: MCPToolMode


class MCPToolCatalogRead(BaseModel):
    server_id: uuid.UUID
    catalog_revision: int
    tools: list[MCPToolRead]


class MCPConnectionOverrideUpdate(BaseModel):
    enabled: bool = False


class MCPConnectionOverrideRead(BaseModel):
    scope: Literal["deepspace", "conversation"]
    scope_id: uuid.UUID
    server_id: uuid.UUID
    enabled: bool


class MCPScopedConnectionRead(BaseModel):
    server: MCPConnectionRead
    enabled: bool


class MCPScopedConnectionListRead(BaseModel):
    scope: Literal["deepspace", "conversation"]
    scope_id: uuid.UUID
    connections: list[MCPScopedConnectionRead]


class MCPCatalogReviewRead(BaseModel):
    id: uuid.UUID
    trust_status: str
    verification_source: str | None = None


class MCPInspectorEventRead(BaseModel):
    event_type: str
    sequence: int
    created_at: datetime
    tool: str | None = None
    argument_keys: list[str] | None = None
    error_code: str | None = None
    content_item_count: int | None = None
    content_types: list[str] | None = None
    has_structured_content: bool | None = None
    rendered_length: int | None = None
    is_error: bool | None = None
    has_refresh_token: bool | None = None
    expires_in: int | None = None
    provider: str | None = None


class MCPInspectorActiveToolRead(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None


class MCPInspectorDiagnosticsRead(BaseModel):
    credential_configured: bool
    oauth_configured: bool
    catalog_counts: dict[str, int]
    event_counts: dict[str, int]
    latest_event: MCPInspectorEventRead | None = None
    reconnect_attempts: int
    last_error: str | None = None
    last_catalog_sync_at: str | None = None
    active_tools: list[MCPInspectorActiveToolRead]


class MCPInspectorRead(BaseModel):
    server: MCPServerRead
    diagnostics: MCPInspectorDiagnosticsRead
    events: list[MCPInspectorEventRead]
