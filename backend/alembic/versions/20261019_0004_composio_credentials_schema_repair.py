"""Move the legacy platform Composio key aside and ensure user credentials exist."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261019_0004"
down_revision = "20261019_0003"
branch_labels = None
depends_on = None

_CREDENTIALS_TABLE = "composio_credentials"
_LEGACY_TABLE = "composio_legacy_platform_credentials"
_USER_COLUMNS = {
    "tenant_id",
    "user_id",
    "secret_ciphertext",
    "secret_nonce",
    "secret_kid",
    "updated_at",
}


def _create_user_credentials_table() -> None:
    op.create_table(
        _CREDENTIALS_TABLE,
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("secret_kid", sa.String(length=128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.execute(f"ALTER TABLE {_CREDENTIALS_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_CREDENTIALS_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY composio_credentials_owner_only ON {_CREDENTIALS_TABLE}
        USING (
            tenant_id::text = current_setting('app.tenant_id', true)
            AND user_id::text = current_setting('app.user_id', true)
        )
        WITH CHECK (
            tenant_id::text = current_setting('app.tenant_id', true)
            AND user_id::text = current_setting('app.user_id', true)
        )
        """)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(_CREDENTIALS_TABLE):
        columns = {column["name"] for column in inspector.get_columns(_CREDENTIALS_TABLE)}
        if _USER_COLUMNS.issubset(columns):
            # Fresh installs already receive the account-scoped shape in 0003.
            return

        if inspector.has_table(_LEGACY_TABLE):
            raise RuntimeError(
                f"Both {_CREDENTIALS_TABLE} and {_LEGACY_TABLE} exist; refusing to replace either."
            )
        # Earlier Composio setup used a single platform-admin credential. Keep
        # that table and its access policy intact; never assign its key to a user.
        op.rename_table(_CREDENTIALS_TABLE, _LEGACY_TABLE)

    if not sa.inspect(op.get_bind()).has_table(_CREDENTIALS_TABLE):
        _create_user_credentials_table()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_LEGACY_TABLE):
        # On fresh installs the per-user table was created by revision 0003.
        return

    if not inspector.has_table(_CREDENTIALS_TABLE):
        raise RuntimeError(
            "Cannot restore the legacy Composio table because the user table is missing."
        )

    # Refuse to discard keys created after upgrade. Disable RLS only inside this
    # migration transaction so the count includes every owner's row.
    op.execute(f"ALTER TABLE {_CREDENTIALS_TABLE} DISABLE ROW LEVEL SECURITY")
    credential_count = bind.execute(
        sa.text(f"SELECT count(*) FROM {_CREDENTIALS_TABLE}")
    ).scalar_one()
    op.execute(f"ALTER TABLE {_CREDENTIALS_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_CREDENTIALS_TABLE} FORCE ROW LEVEL SECURITY")
    if credential_count:
        raise RuntimeError(
            "Cannot downgrade while user-owned Composio credentials exist; no credentials were removed."
        )

    op.execute(f"DROP POLICY IF EXISTS composio_credentials_owner_only ON {_CREDENTIALS_TABLE}")
    op.drop_table(_CREDENTIALS_TABLE)
    op.rename_table(_LEGACY_TABLE, _CREDENTIALS_TABLE)
