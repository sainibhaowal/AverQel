from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.base import Base


class MCPServer(Base):
    """Tenant-owned generic MCP server definition and lifecycle state."""

    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    registry_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_registry_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_slug: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    account_identity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    connection_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_connection_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    catalog_revision: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'disconnected'"), index=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reconnect_attempts: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class MCPRegistryEntry(Base):
    """Public marketplace metadata imported from the MCP Registry."""
    __tablename__ = "mcp_registry_entries"
    __table_args__ = (
        UniqueConstraint("source", "server_name", name="uq_mcp_registry_source_name"),
        CheckConstraint(
            "publisher_type IN ('official', 'community')",
            name="ck_mcp_registry_entries_publisher_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback)
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    server_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    provider_slug: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    publisher_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    transport: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    remote_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    package_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    oauth_requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    oauth_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    requested_scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    supported_products: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    risk_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    official: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"), index=True)
    verified: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    documentation_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    author_website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    support_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    privacy_policy_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    catalog_badges: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    trusted_logo_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    tool_risk_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tool_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    last_catalog_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trust_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'discovered'"), index=True)
    verification_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    popularity_rank: Mapped[int | None] = mapped_column(nullable=True, index=True)
    catalog_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"), index=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'not_checked'"), index=True)
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class MCPOAuthTransaction(Base):
    """Encrypted, single-use OAuth transaction state for a native MCP server."""

    __tablename__ = "mcp_oauth_transactions"
    __table_args__ = (UniqueConstraint("state_hash", name="uq_mcp_oauth_transactions_state_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_ciphertext: Mapped[bytes] = mapped_column(nullable=False)
    secret_nonce: Mapped[bytes] = mapped_column(nullable=False)
    secret_kid: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class MCPEvent(Base):
    """Durable lifecycle/catalog/tool event for replay and diagnostics."""

    __tablename__ = "mcp_events"
    __table_args__ = (UniqueConstraint("server_id", "sequence", name="uq_mcp_events_server_sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)


class MCPOAuthToken(Base):
    """Encrypted MCP credential material; plaintext never enters this table."""

    __tablename__ = "mcp_oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, unique=True)
    registry_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_registry_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_slug: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    granted_scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    secret_ciphertext: Mapped[bytes] = mapped_column(nullable=False)
    secret_nonce: Mapped[bytes] = mapped_column(nullable=False)
    secret_kid: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
