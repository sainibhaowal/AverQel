"""Add connector_id to documents

Revision ID: bb1ef0954cca
Revises: 078c055efcaa
Create Date: 2026-05-03 09:12:10.306257
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "bb1ef0954cca"
down_revision = "078c055efcaa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("connector_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_documents_connector_id",
        "documents",
        "connectors",
        ["connector_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_documents_connector_id", "documents", ["connector_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_connector_id", table_name="documents")
    op.drop_constraint("fk_documents_connector_id", "documents", type_="foreignkey")
    op.drop_column("documents", "connector_id")
