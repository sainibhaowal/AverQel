"""Add durable webhook attempt timelines.

Revision ID: 20261011_0001
Revises: 20261010_0001
"""

import sqlalchemy as sa

from alembic import op

revision = "20261011_0001"
down_revision = "20261010_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_webhook_deliveries",
        sa.Column("attempt_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("document_webhook_deliveries", "attempt_history")
