"""add provider reranking support

Revision ID: 20260329_0011
Revises: 20260319_0010
Create Date: 2026-03-29 19:20:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260329_0011"
down_revision = "20260319_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column(
            "supports_reranking",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "provider_configs",
        sa.Column("default_reranker_model", sa.String(length=255), nullable=True),
    )
    op.execute("""
        UPDATE provider_configs
        SET
            supports_reranking = true,
            default_reranker_model = COALESCE(
                default_reranker_model,
                'BAAI/bge-reranker-v2-m3'
            )
        WHERE provider_type = 'sentence-transformers'
        """)
    op.execute("""
        UPDATE provider_configs
        SET supports_reranking = true
        WHERE provider_type = 'cohere'
        """)
    op.alter_column("provider_configs", "supports_reranking", server_default=None)


def downgrade() -> None:
    op.drop_column("provider_configs", "default_reranker_model")
    op.drop_column("provider_configs", "supports_reranking")
