"""mcp registry marketplace catalog"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260717_0003"
down_revision = "20260716_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_registry_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("server_name", sa.String(240), nullable=False),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("publisher", sa.String(240)),
        sa.Column("description", sa.String(2000)),
        sa.Column("transport", sa.String(32)),
        sa.Column("remote_url", sa.String(1000)),
        sa.Column(
            "package_metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "oauth_requirements",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "categories",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("official", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("logo_url", sa.String(1000)),
        sa.Column("tool_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_catalog_sync_at", sa.DateTime(timezone=True)),
        sa.Column("verification_reason", sa.String(500)),
        sa.UniqueConstraint("source", "server_name", name="uq_mcp_registry_source_name"),
    )
    for col in (
        "source",
        "server_name",
        "publisher",
        "transport",
        "official",
        "verified",
        "last_seen_at",
    ):
        op.create_index("ix_mcp_registry_entries_" + col, "mcp_registry_entries", [col])


def downgrade() -> None:
    op.drop_table("mcp_registry_entries")
