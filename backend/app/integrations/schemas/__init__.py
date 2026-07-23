"""API schemas for external integrations."""

from app.integrations.schemas.connectors import (
    ConnectorBase,
    ConnectorCreate,
    ConnectorFleetSummary,
    ConnectorOAuthStartResponse,
    ConnectorOAuthStatus,
    ConnectorRead,
    ConnectorSummary,
    ConnectorSyncAuditEntry,
    IntegrationRead,
    SyncResult,
)
from app.integrations.schemas.mcp import (
    MCPCatalogReviewRequest,
    MCPConnectionPolicyRead,
    MCPConnectionPolicyUpdate,
    MCPServerRead,
)

__all__ = [
    "ConnectorBase",
    "ConnectorCreate",
    "ConnectorFleetSummary",
    "ConnectorOAuthStartResponse",
    "ConnectorOAuthStatus",
    "ConnectorRead",
    "ConnectorSummary",
    "ConnectorSyncAuditEntry",
    "IntegrationRead",
    "MCPCatalogReviewRequest",
    "MCPServerRead",
    "MCPConnectionPolicyRead",
    "MCPConnectionPolicyUpdate",
    "SyncResult",
]
