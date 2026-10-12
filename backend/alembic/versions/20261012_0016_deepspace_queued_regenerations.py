"""Persist the assistant message targeted by a queued regeneration."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0016"
down_revision = "20261012_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deepspace_queued_turns",
        sa.Column("regenerate_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_deepspace_queued_turn_regenerate_message",
        "deepspace_queued_turns",
        "messages",
        ["regenerate_message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_deepspace_queued_turns_regenerate_message_id",
        "deepspace_queued_turns",
        ["regenerate_message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deepspace_queued_turns_regenerate_message_id",
        table_name="deepspace_queued_turns",
    )
    op.drop_constraint(
        "fk_deepspace_queued_turn_regenerate_message",
        "deepspace_queued_turns",
        type_="foreignkey",
    )
    op.drop_column("deepspace_queued_turns", "regenerate_message_id")
