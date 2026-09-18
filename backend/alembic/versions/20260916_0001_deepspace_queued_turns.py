"""Add durable FIFO queue records for DeepSpace turns."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260916_0001"
down_revision = "20260913_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_queued_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_request_id", sa.String(255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "roles_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "permissions_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "conversation_id",
            "client_request_id",
            name="uq_deepspace_queued_turn_request",
        ),
    )
    for column in ("tenant_id", "user_id", "conversation_id", "client_request_id", "status"):
        op.create_index(f"ix_deepspace_queued_turns_{column}", "deepspace_queued_turns", [column])
    op.create_index(
        "ix_deepspace_queued_turns_dispatch",
        "deepspace_queued_turns",
        ["tenant_id", "user_id", "conversation_id", "status", "priority", "sequence"],
    )


def downgrade() -> None:
    op.drop_table("deepspace_queued_turns")
