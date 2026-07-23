"""Add explicit MCP provider, server, and encrypted-token identity metadata."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260722_0003"
down_revision = "20260722_0002"
branch_labels = None
depends_on = None


def _jsonb_default(value: str) -> sa.TextClause:
    return sa.text(f"'{value}'::jsonb")


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    # Registry metadata is global public catalog data. New columns are added
    # with safe defaults so existing registry rows remain readable during a
    # rolling deployment.
    registry_columns = (
        sa.Column("provider_slug", sa.String(240), nullable=True),
        sa.Column("publisher_type", sa.String(24), nullable=True),
        sa.Column("version", sa.String(128), nullable=True),
        sa.Column("documentation_url", sa.String(1000), nullable=True),
        sa.Column("health_status", sa.String(32), nullable=False, server_default=sa.text("'not_checked'")),
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_scopes", jsonb, nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("supported_products", jsonb, nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("risk_policy", jsonb, nullable=False, server_default=_jsonb_default("{}")),
        sa.Column("oauth_profile", jsonb, nullable=False, server_default=_jsonb_default("{}")),
        sa.Column("author_website_url", sa.String(1000), nullable=True),
        sa.Column("support_url", sa.String(1000), nullable=True),
        sa.Column("privacy_policy_url", sa.String(1000), nullable=True),
        sa.Column("catalog_badges", jsonb, nullable=False, server_default=_jsonb_default("{}")),
        sa.Column("trusted_logo_key", sa.String(128), nullable=True),
        sa.Column("tool_categories", jsonb, nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("tool_risk_summary", jsonb, nullable=False, server_default=_jsonb_default("{}")),
    )
    for column in registry_columns:
        op.add_column("mcp_registry_entries", column)

    # Backfill only from already persisted public catalog metadata. No OAuth
    # payload is copied into the new public columns.
    op.execute(
        """
        UPDATE mcp_registry_entries
        SET provider_slug = COALESCE(
                NULLIF(raw_metadata -> 'catalog' ->> 'provider_slug', ''),
                server_name
            ),
            publisher_type = CASE
                WHEN raw_metadata -> 'catalog' ->> 'publisher_type' IN ('official', 'community')
                    THEN raw_metadata -> 'catalog' ->> 'publisher_type'
                WHEN official THEN 'official'
                ELSE 'community'
            END,
            documentation_url = COALESCE(
                NULLIF(raw_metadata -> 'catalog' ->> 'documentation_url', ''),
                NULLIF(raw_metadata -> 'server' ->> 'documentationUrl', '')
            ),
            requested_scopes = CASE
                WHEN jsonb_typeof(oauth_requirements -> 'requested_scopes') = 'array'
                    THEN oauth_requirements -> 'requested_scopes'
                ELSE '[]'::jsonb
            END,
            supported_products = CASE
                WHEN jsonb_typeof(raw_metadata -> 'catalog' -> 'supported_products') = 'array'
                    THEN raw_metadata -> 'catalog' -> 'supported_products'
                WHEN jsonb_typeof(package_metadata -> 'supported_products') = 'array'
                    THEN package_metadata -> 'supported_products'
                ELSE '[]'::jsonb
            END,
            risk_policy = CASE
                WHEN jsonb_typeof(raw_metadata -> 'catalog' -> 'risk_policy') = 'object'
                    THEN raw_metadata -> 'catalog' -> 'risk_policy'
                WHEN jsonb_typeof(package_metadata -> 'risk_policy') = 'object'
                    THEN package_metadata -> 'risk_policy'
                ELSE '{}'::jsonb
            END,
            author_website_url = NULLIF(raw_metadata -> 'catalog' ->> 'author_website_url', ''),
            support_url = NULLIF(raw_metadata -> 'catalog' ->> 'support_url', ''),
            privacy_policy_url = NULLIF(raw_metadata -> 'catalog' ->> 'privacy_policy_url', ''),
            catalog_badges = CASE
                WHEN jsonb_typeof(raw_metadata -> 'catalog' -> 'badges') = 'object'
                    THEN raw_metadata -> 'catalog' -> 'badges'
                ELSE '{}'::jsonb
            END,
            trusted_logo_key = NULLIF(raw_metadata -> 'catalog' ->> 'trusted_logo_key', ''),
            tool_categories = CASE
                WHEN jsonb_typeof(raw_metadata -> 'catalog' -> 'tool_categories') = 'array'
                    THEN raw_metadata -> 'catalog' -> 'tool_categories'
                WHEN jsonb_typeof(package_metadata -> 'tool_categories') = 'array'
                    THEN package_metadata -> 'tool_categories'
                ELSE '[]'::jsonb
            END,
            tool_risk_summary = CASE
                WHEN jsonb_typeof(raw_metadata -> 'catalog' -> 'risk_policy') = 'object'
                    THEN jsonb_build_object('policy', raw_metadata -> 'catalog' -> 'risk_policy')
                ELSE '{}'::jsonb
            END
        WHERE provider_slug IS NULL
           OR publisher_type IS NULL
        """
    )
    op.alter_column("mcp_registry_entries", "provider_slug", nullable=False)
    op.alter_column("mcp_registry_entries", "publisher_type", nullable=False)
    op.create_check_constraint(
        "ck_mcp_registry_entries_publisher_type",
        "mcp_registry_entries",
        "publisher_type IN ('official', 'community')",
    )
    for column in ("provider_slug", "publisher_type", "health_status"):
        op.create_index(f"ix_mcp_registry_entries_{column}", "mcp_registry_entries", [column])

    # Native server identity remains nullable for manually-created legacy
    # records. Curated connections are populated with the actual registry FK.
    op.add_column(
        "mcp_servers",
        sa.Column("registry_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mcp_servers_registry_entry_id",
        "mcp_servers",
        "mcp_registry_entries",
        ["registry_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("mcp_servers", sa.Column("provider_slug", sa.String(240), nullable=True))
    op.add_column(
        "mcp_servers",
        sa.Column("account_identity", jsonb, nullable=False, server_default=_jsonb_default("{}")),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("catalog_revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_mcp_servers_registry_entry_id", "mcp_servers", ["registry_entry_id"])
    op.create_index("ix_mcp_servers_provider_slug", "mcp_servers", ["provider_slug"])
    op.execute(
        """
        UPDATE mcp_servers AS server
        SET registry_entry_id = CASE
                WHEN server.config ->> 'registry_entry_id' ~
                    '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
                    THEN (server.config ->> 'registry_entry_id')::uuid
                ELSE NULL
            END,
            provider_slug = COALESCE(
                NULLIF(server.config ->> 'vendor_slug', ''),
                NULLIF(server.config ->> 'provider_slug', '')
            ),
            catalog_revision = CASE
                WHEN server.config ->> 'catalog_revision' ~ '^[0-9]+$'
                    THEN (server.config ->> 'catalog_revision')::integer
                ELSE 0
            END
        """
    )
    op.execute(
        """
        UPDATE mcp_servers AS server
        SET provider_slug = COALESCE(server.provider_slug, entry.provider_slug)
        FROM mcp_registry_entries AS entry
        WHERE server.registry_entry_id = entry.id
        """
    )

    # Token ciphertext/nonces/key IDs are intentionally untouched. Identity
    # columns are backfilled from the tenant-owned server row and then user_id
    # is made mandatory for every future encrypted MCP token.
    op.add_column("mcp_oauth_tokens", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "mcp_oauth_tokens",
        sa.Column("registry_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("mcp_oauth_tokens", sa.Column("provider_slug", sa.String(240), nullable=True))
    op.execute(
        """
        UPDATE mcp_oauth_tokens AS token
        SET user_id = server.user_id,
            registry_entry_id = server.registry_entry_id,
            provider_slug = server.provider_slug
        FROM mcp_servers AS server
        WHERE token.server_id = server.id
        """
    )
    op.alter_column("mcp_oauth_tokens", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_mcp_oauth_tokens_user_id",
        "mcp_oauth_tokens",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_mcp_oauth_tokens_registry_entry_id",
        "mcp_oauth_tokens",
        "mcp_registry_entries",
        ["registry_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mcp_oauth_tokens_user_id", "mcp_oauth_tokens", ["user_id"])
    op.create_index("ix_mcp_oauth_tokens_registry_entry_id", "mcp_oauth_tokens", ["registry_entry_id"])
    op.create_index("ix_mcp_oauth_tokens_provider_slug", "mcp_oauth_tokens", ["provider_slug"])


def downgrade() -> None:
    op.drop_index("ix_mcp_oauth_tokens_provider_slug", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_registry_entry_id", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_tokens_user_id", table_name="mcp_oauth_tokens")
    op.drop_constraint("fk_mcp_oauth_tokens_registry_entry_id", "mcp_oauth_tokens", type_="foreignkey")
    op.drop_constraint("fk_mcp_oauth_tokens_user_id", "mcp_oauth_tokens", type_="foreignkey")
    op.drop_column("mcp_oauth_tokens", "provider_slug")
    op.drop_column("mcp_oauth_tokens", "registry_entry_id")
    op.drop_column("mcp_oauth_tokens", "user_id")

    op.drop_index("ix_mcp_servers_provider_slug", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_registry_entry_id", table_name="mcp_servers")
    op.drop_column("mcp_servers", "catalog_revision")
    op.drop_column("mcp_servers", "account_identity")
    op.drop_column("mcp_servers", "provider_slug")
    op.drop_constraint("fk_mcp_servers_registry_entry_id", "mcp_servers", type_="foreignkey")
    op.drop_column("mcp_servers", "registry_entry_id")

    for column in ("provider_slug", "publisher_type", "health_status"):
        op.drop_index(f"ix_mcp_registry_entries_{column}", table_name="mcp_registry_entries")
    op.drop_constraint("ck_mcp_registry_entries_publisher_type", "mcp_registry_entries", type_="check")
    for column in (
        "tool_risk_summary",
        "tool_categories",
        "trusted_logo_key",
        "catalog_badges",
        "privacy_policy_url",
        "support_url",
        "author_website_url",
        "oauth_profile",
        "risk_policy",
        "supported_products",
        "requested_scopes",
        "health_checked_at",
        "health_status",
        "documentation_url",
        "version",
        "publisher_type",
        "provider_slug",
    ):
        op.drop_column("mcp_registry_entries", column)
