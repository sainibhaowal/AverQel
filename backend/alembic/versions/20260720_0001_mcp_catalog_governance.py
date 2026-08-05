"""add database-backed MCP catalog trust and enrichment state"""

from alembic import op

revision = "20260720_0001"
down_revision = "20260717_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The trusted marketplace is remote-only; remove legacy package-only rows.
    op.execute("DELETE FROM mcp_registry_entries WHERE remote_url IS NULL")
    op.execute(
        "ALTER TABLE mcp_registry_entries ADD COLUMN IF NOT EXISTS trust_status VARCHAR(24) NOT NULL DEFAULT 'discovered'"
    )
    op.execute(
        "ALTER TABLE mcp_registry_entries ADD COLUMN IF NOT EXISTS verification_source VARCHAR(500)"
    )
    op.execute("ALTER TABLE mcp_registry_entries ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ")
    op.execute("ALTER TABLE mcp_registry_entries ADD COLUMN IF NOT EXISTS popularity_rank INTEGER")
    op.execute(
        "ALTER TABLE mcp_registry_entries ADD COLUMN IF NOT EXISTS catalog_status VARCHAR(32) NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE mcp_registry_entries ADD COLUMN IF NOT EXISTS enrichment_error VARCHAR(1000)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_registry_entries_trust_status ON mcp_registry_entries (trust_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_registry_entries_catalog_status ON mcp_registry_entries (catalog_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_registry_entries_popularity_rank ON mcp_registry_entries (popularity_rank)"
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_registry_entries_popularity_rank", table_name="mcp_registry_entries")
    op.drop_index("ix_mcp_registry_entries_catalog_status", table_name="mcp_registry_entries")
    op.drop_index("ix_mcp_registry_entries_trust_status", table_name="mcp_registry_entries")
    for column in (
        "enrichment_error",
        "catalog_status",
        "popularity_rank",
        "verified_at",
        "verification_source",
        "trust_status",
    ):
        op.drop_column("mcp_registry_entries", column)
