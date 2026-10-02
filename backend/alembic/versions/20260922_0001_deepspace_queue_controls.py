"""Add durable pause state for DeepSpace conversation queues."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260922_0001"
down_revision = "20260920_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_queue_controls",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("failed_request_id", sa.String(255), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_deepspace_queue_controls_tenant_id", "deepspace_queue_controls", ["tenant_id"]
    )
    op.create_index("ix_deepspace_queue_controls_user_id", "deepspace_queue_controls", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_deepspace_queue_controls_user_id", table_name="deepspace_queue_controls")
    op.drop_index("ix_deepspace_queue_controls_tenant_id", table_name="deepspace_queue_controls")
    op.drop_table("deepspace_queue_controls")
