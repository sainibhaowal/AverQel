"""add_collection_expiry_days

Revision ID: 1a2b3c4d5e6f
Revises: 8b3a7c6e4d2a
Create Date: 2026-07-06 20:15:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "8b3a7c6e4d2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_collections",
        sa.Column("expiry_days", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("document_collections", "expiry_days")
