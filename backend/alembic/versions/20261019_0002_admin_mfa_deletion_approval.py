"""Record MFA completion and delayed single-owner deletion approvals."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261019_0002"
down_revision = "20261019_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True)))
    op.add_column(
        "data_deletions",
        sa.Column(
            "approval_mode",
            sa.String(length=32),
            nullable=False,
            server_default="two_admin",
        ),
    )
    op.add_column(
        "data_deletions",
        sa.Column("self_approval_not_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("""UPDATE data_deletions
           SET self_approval_not_before = requested_at + INTERVAL '24 hours'
           WHERE status = 'awaiting_approval'""")


def downgrade() -> None:
    op.drop_column("data_deletions", "self_approval_not_before")
    op.drop_column("data_deletions", "approval_mode")
    op.drop_column("auth_sessions", "mfa_verified_at")
