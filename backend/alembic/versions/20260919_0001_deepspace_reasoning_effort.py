"""Persist selectable DeepSpace reasoning effort."""

import sqlalchemy as sa

from alembic import op

revision = "20260919_0001"
down_revision = "20260918_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deepspace_queued_turns", sa.Column("reasoning_effort", sa.String(20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("deepspace_queued_turns", "reasoning_effort")
