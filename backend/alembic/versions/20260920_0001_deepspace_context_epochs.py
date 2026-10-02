"""Persist DeepSpace context epochs and source snapshots."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260920_0001"
down_revision = "20260919_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_context_epochs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("baseline_digest", sa.String(64), nullable=False),
        sa.Column(
            "source_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_deepspace_context_epochs_tenant_id", ["tenant_id"]),
        ("ix_deepspace_context_epochs_user_id", ["user_id"]),
        ("ix_deepspace_context_epochs_conversation_id", ["conversation_id"]),
        ("ix_deepspace_context_epochs_created_at", ["created_at"]),
    ):
        op.create_index(name, "deepspace_context_epochs", columns)


def downgrade() -> None:
    for name in (
        "ix_deepspace_context_epochs_created_at",
        "ix_deepspace_context_epochs_conversation_id",
        "ix_deepspace_context_epochs_user_id",
        "ix_deepspace_context_epochs_tenant_id",
    ):
        op.drop_index(name, table_name="deepspace_context_epochs")
    op.drop_table("deepspace_context_epochs")
