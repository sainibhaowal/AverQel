"""Persist private Library references on durable DeepSpace queue turns."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260930_0001"
down_revision = "20260929_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deepspace_queued_turns",
        sa.Column(
            "attachment_file_ids_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("deepspace_queued_turns", "attachment_file_ids_json")
