"""Add redacted, tenant-owned DeepSpace request latency metrics."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260916_0002"
down_revision = "20260916_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_request_metrics",
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
        sa.Column(
            "provider_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider_configs.id", ondelete="SET NULL"),
        ),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("time_to_first_token_ms", sa.Integer()),
        sa.Column("tool_profile", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    for column in (
        "tenant_id",
        "user_id",
        "conversation_id",
        "provider_config_id",
        "outcome",
        "created_at",
    ):
        op.create_index(
            f"ix_deepspace_request_metrics_{column}", "deepspace_request_metrics", [column]
        )


def downgrade() -> None:
    op.drop_table("deepspace_request_metrics")
