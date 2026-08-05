"""auth_security_hardening

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-01 21:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("access_token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "revoked_access_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "token_id",
            name="uq_revoked_access_tokens_tenant_token_id",
        ),
    )
    op.create_index(
        "ix_revoked_access_tokens_tenant_id",
        "revoked_access_tokens",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_revoked_access_tokens_user_id",
        "revoked_access_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_revoked_access_tokens_token_id",
        "revoked_access_tokens",
        ["token_id"],
        unique=False,
    )
    op.create_index(
        "ix_revoked_access_tokens_expires_at",
        "revoked_access_tokens",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_revoked_access_tokens_expires_at", table_name="revoked_access_tokens")
    op.drop_index("ix_revoked_access_tokens_token_id", table_name="revoked_access_tokens")
    op.drop_index("ix_revoked_access_tokens_user_id", table_name="revoked_access_tokens")
    op.drop_index("ix_revoked_access_tokens_tenant_id", table_name="revoked_access_tokens")
    op.drop_table("revoked_access_tokens")
    op.drop_column("users", "access_token_version")
