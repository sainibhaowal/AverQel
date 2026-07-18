"""harden_deepspace_memory

Revision ID: 20260605_0001
Revises: 20260527_0001
Create Date: 2026-06-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260605_0001"
down_revision = "20260527_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_memory", sa.Column("embedding_provider", sa.String(), nullable=True)
    )
    op.add_column(
        "agent_memory", sa.Column("embedding_model", sa.String(), nullable=True)
    )
    op.add_column(
        "agent_memory", sa.Column("embedding_version", sa.String(), nullable=True)
    )
    op.add_column("agent_memory", sa.Column("content_hash", sa.String(), nullable=True))
    op.add_column(
        "agent_memory",
        sa.Column("importance_score", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.add_column(
        "agent_memory",
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_memory", sa.Column("last_accessed_at", sa.DateTime(), nullable=True)
    )
    op.add_column("agent_memory", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.create_index(
        op.f("ix_agent_memory_content_hash"),
        "agent_memory",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_memory_content_hash"), table_name="agent_memory")
    op.drop_column("agent_memory", "metadata_json")
    op.drop_column("agent_memory", "last_accessed_at")
    op.drop_column("agent_memory", "access_count")
    op.drop_column("agent_memory", "importance_score")
    op.drop_column("agent_memory", "content_hash")
    op.drop_column("agent_memory", "embedding_version")
    op.drop_column("agent_memory", "embedding_model")
    op.drop_column("agent_memory", "embedding_provider")
