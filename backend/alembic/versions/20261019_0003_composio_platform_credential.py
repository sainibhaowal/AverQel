"""Store one encrypted Composio project key for platform-managed access."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261019_0003"
down_revision = ("20261019_0002", "20260424_0025")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "composio_credentials",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("secret_kid", sa.String(length=128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("id = 1", name="ck_composio_credentials_singleton"),
    )
    op.execute("ALTER TABLE composio_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE composio_credentials FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY composio_credentials_platform_admin_only ON composio_credentials
        USING (current_setting('app.tenant_id', true) = 'bypass')
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass')
        """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS composio_credentials_platform_admin_only ON composio_credentials"
    )
    op.drop_table("composio_credentials")
