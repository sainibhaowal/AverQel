"""Create app feedback tables

Revision ID: 20260510_0001
Revises: fbe37b489616
Create Date: 2026-05-10 00:01:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260510_0001"
down_revision = "fbe37b489616"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_campaigns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "app_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "rating",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "category",
            sa.String(length=50),
            server_default=sa.text("'suggestion'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["feedback_campaigns.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_feedback_tenant_id"), "app_feedback", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_app_feedback_user_id"), "app_feedback", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_app_feedback_campaign_id"),
        "app_feedback",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_feedback_created_at"), "app_feedback", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_feedback_campaigns_is_active"),
        "feedback_campaigns",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_feedback_campaigns_is_active"), table_name="feedback_campaigns"
    )
    op.drop_index(op.f("ix_app_feedback_created_at"), table_name="app_feedback")
    op.drop_index(op.f("ix_app_feedback_campaign_id"), table_name="app_feedback")
    op.drop_index(op.f("ix_app_feedback_user_id"), table_name="app_feedback")
    op.drop_index(op.f("ix_app_feedback_tenant_id"), table_name="app_feedback")
    op.drop_table("app_feedback")
    op.drop_table("feedback_campaigns")
