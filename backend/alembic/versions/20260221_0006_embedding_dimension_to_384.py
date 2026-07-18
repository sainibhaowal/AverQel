"""align embedding vector dimension to 384 for open-source model providers

Revision ID: 20260221_0006
Revises: 20260221_0005
Create Date: 2026-02-21 21:05:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260221_0006"
down_revision = "20260221_0005"
branch_labels = None
depends_on = None

TARGET_DIMENSION = 384
PREVIOUS_DIMENSION = 8


def upgrade() -> None:
    # Existing embeddings from previous dimension cannot be cast directly.
    # Re-indexing is required after this migration.
    op.execute("TRUNCATE TABLE chunk_embeddings RESTART IDENTITY CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_chunk_embeddings_embedding_hnsw")
    op.execute(f"""
        ALTER TABLE chunk_embeddings
        ALTER COLUMN embedding TYPE vector({TARGET_DIMENSION})
        """)
    op.create_index(
        "ix_chunk_embeddings_embedding_hnsw",
        "chunk_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_l2_ops"},
    )


def downgrade() -> None:
    op.execute("TRUNCATE TABLE chunk_embeddings RESTART IDENTITY CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_chunk_embeddings_embedding_hnsw")
    op.execute(f"""
        ALTER TABLE chunk_embeddings
        ALTER COLUMN embedding TYPE vector({PREVIOUS_DIMENSION})
        """)
    op.create_index(
        "ix_chunk_embeddings_embedding_hnsw",
        "chunk_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_l2_ops"},
    )
