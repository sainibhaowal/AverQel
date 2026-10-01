"""Add revocable linked account sessions and bind refresh tokens to them."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0005"
down_revision = "20261012_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("label", sa.String(128), server_default=sa.text("'Browser'"), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "token_family_id", name="uq_auth_session_family"),
    )
    for name, columns in {
        "ix_auth_sessions_tenant_id": ["tenant_id"],
        "ix_auth_sessions_user_id": ["user_id"],
        "ix_auth_sessions_token_family_id": ["token_family_id"],
        "ix_auth_sessions_revoked_at": ["revoked_at"],
    }.items():
        op.create_index(name, "auth_sessions", columns)
    op.add_column(
        "refresh_tokens",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_refresh_tokens_session_id", "refresh_tokens", "auth_sessions", ["session_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    op.drop_constraint("fk_refresh_tokens_session_id", "refresh_tokens", type_="foreignkey")
    op.drop_column("refresh_tokens", "session_id")
    for name in (
        "ix_auth_sessions_revoked_at",
        "ix_auth_sessions_token_family_id",
        "ix_auth_sessions_user_id",
        "ix_auth_sessions_tenant_id",
    ):
        op.drop_index(name, table_name="auth_sessions")
    op.drop_table("auth_sessions")
