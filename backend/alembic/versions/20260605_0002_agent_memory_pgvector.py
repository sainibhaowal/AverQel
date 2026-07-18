"""agent_memory_pgvector

Revision ID: 20260605_0002
Revises: 20260605_0001
Create Date: 2026-06-05 00:00:01.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

from alembic import op
from app.core.config import get_settings

revision = "20260605_0002"
down_revision = "20260605_0001"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSION = get_settings().embedding_dimension


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "agent_memory",
        sa.Column("embedding_vector", Vector(EMBEDDING_DIMENSION), nullable=True),
    )
    op.create_index(
        "ix_agent_memory_embedding_vector_hnsw",
        "agent_memory",
        ["embedding_vector"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_l2_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_agent_memory_embedding_vector_hnsw", table_name="agent_memory")
    op.drop_column("agent_memory", "embedding_vector")
