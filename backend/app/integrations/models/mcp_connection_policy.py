"""Tenant/user-owned MCP tool and connection policy records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.base import Base


class MCPConnectionPolicy(Base):
    """Durable policy for one tenant/user-owned MCP server.

    Connected MCP accounts are available across the owner's DeepSpace
    conversations by default. Tool-level allow/deny, risk, read-only, and
    approval policy remains enforced by the runtime evaluator.
    """

    __tablename__ = "mcp_connection_policies"
    __table_args__ = (
        UniqueConstraint("server_id", name="uq_mcp_connection_policies_server_id"),
        CheckConstraint(
            "risk_ceiling IN ('read', 'write', 'delete', 'external_message')",
            name="ck_mcp_connection_policies_risk_ceiling",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    denied_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    read_only: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    risk_ceiling: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'read'"))
    approval_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{\"write\":\"needs_approval\",\"delete\":\"needs_approval\",\"external_message\":\"needs_approval\"}'::jsonb"),
    )
    tool_modes: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    default_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    deepspace_overrides: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    conversation_overrides: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
