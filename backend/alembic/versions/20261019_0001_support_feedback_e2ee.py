"""Add encrypted support and feedback payload storage."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261019_0001"
down_revision = "20261018_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_tickets", sa.Column("encrypted_payload", sa.Text(), nullable=True))
    op.add_column(
        "support_ticket_messages", sa.Column("encrypted_payload", sa.Text(), nullable=True)
    )
    op.add_column(
        "support_ticket_attachments", sa.Column("encrypted_metadata", sa.Text(), nullable=True)
    )
    op.add_column(
        "support_ticket_attachments",
        sa.Column("is_encrypted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("app_feedback", sa.Column("encrypted_payload", sa.Text(), nullable=True))
    op.add_column("app_feedback_messages", sa.Column("encrypted_payload", sa.Text(), nullable=True))

    op.create_table(
        "support_encryption_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("private_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("salt", sa.String(length=64), nullable=False),
        sa.Column("iv", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scope", name="uq_support_encryption_keys_user_scope"),
    )
    op.create_index(
        "ix_support_encryption_keys_scope_tenant",
        "support_encryption_keys",
        ["scope", "tenant_id"],
    )
    op.create_index(
        "uq_support_encryption_keys_platform_scope",
        "support_encryption_keys",
        ["scope"],
        unique=True,
        postgresql_where=sa.text("scope = 'platform_admin'"),
    )
    op.execute("ALTER TABLE support_encryption_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_encryption_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation_support_encryption_keys
        ON support_encryption_keys
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_support_encryption_keys ON support_encryption_keys"
    )
    op.execute("ALTER TABLE support_encryption_keys NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_encryption_keys DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_support_encryption_keys_scope_tenant", table_name="support_encryption_keys")
    op.drop_index("uq_support_encryption_keys_platform_scope", table_name="support_encryption_keys")
    op.drop_table("support_encryption_keys")
    op.drop_column("app_feedback_messages", "encrypted_payload")
    op.drop_column("app_feedback", "encrypted_payload")
    op.drop_column("support_ticket_attachments", "is_encrypted")
    op.drop_column("support_ticket_attachments", "encrypted_metadata")
    op.drop_column("support_ticket_messages", "encrypted_payload")
    op.drop_column("support_tickets", "encrypted_payload")
