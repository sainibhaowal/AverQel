"""Add durable DeepSpace research runs and evidence sources.

Revision ID: 20260912_0001
Revises: 20260818_0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260912_0001"
down_revision = "20260818_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_research_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("is_freshness_request", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "quality_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_deepspace_research_runs_tenant_id", "deepspace_research_runs", ["tenant_id"]
    )
    op.create_index(
        "ix_deepspace_research_runs_conversation_id", "deepspace_research_runs", ["conversation_id"]
    )
    op.create_table(
        "deepspace_research_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deepspace_research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text()),
        sa.Column("published_at", sa.String(128)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("retrieval_status", sa.String(32), nullable=False),
        sa.Column(
            "verification_status", sa.String(32), nullable=False, server_default="unverified"
        ),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("extracted_text", sa.Text()),
        sa.Column(
            "passages_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_deepspace_research_sources_run_id", "deepspace_research_sources", ["run_id"]
    )
    op.create_index(
        "ix_deepspace_research_sources_tenant_id", "deepspace_research_sources", ["tenant_id"]
    )
    op.create_index(
        "ix_deepspace_research_sources_domain", "deepspace_research_sources", ["domain"]
    )


def downgrade() -> None:
    op.drop_table("deepspace_research_sources")
    op.drop_table("deepspace_research_runs")
