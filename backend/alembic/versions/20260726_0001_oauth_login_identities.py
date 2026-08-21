"""add separate Google and GitHub application login identities"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260726_0001"
down_revision = "20260723_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_identities_provider_subject"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "user_id",
            name="uq_oauth_identities_tenant_provider_user",
        ),
    )
    op.create_index(
        "ix_oauth_identities_tenant_id", "oauth_identities", ["tenant_id"], unique=False
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"], unique=False)
    op.create_index("ix_oauth_identities_provider", "oauth_identities", ["provider"], unique=False)
    op.execute("ALTER TABLE oauth_identities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE oauth_identities FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_oauth_identities ON oauth_identities
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_oauth_identities ON oauth_identities")
    op.execute("ALTER TABLE oauth_identities NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE oauth_identities DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_oauth_identities_provider", table_name="oauth_identities")
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_index("ix_oauth_identities_tenant_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")
