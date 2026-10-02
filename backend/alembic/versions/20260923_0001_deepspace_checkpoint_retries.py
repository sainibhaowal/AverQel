"""Add durable source links for DeepSpace checkpoint retries."""

import sqlalchemy as sa

from alembic import op

revision = "20260923_0001"
down_revision = "20260922_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deepspace_queued_turns",
        sa.Column("resume_from_request_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_deepspace_queued_turns_resume_from_request_id",
        "deepspace_queued_turns",
        ["resume_from_request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deepspace_queued_turns_resume_from_request_id",
        table_name="deepspace_queued_turns",
    )
    op.drop_column("deepspace_queued_turns", "resume_from_request_id")
