from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "20260402_0016"
down_revision = "20260402_0015"
branch_labels = None
depends_on = None


def _code_for_id(value: uuid.UUID) -> str:
    return str(value).replace("-", "").upper()[-16:]


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("collection_code", sa.String(length=16), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM users")).fetchall()
    for row in rows:
        user_id = row[0]
        bind.execute(
            sa.text("UPDATE users SET collection_code = :code WHERE id = :id"),
            {"id": user_id, "code": _code_for_id(user_id)},
        )

    op.alter_column("users", "collection_code", nullable=False)
    op.create_index(
        "ix_users_collection_code", "users", ["collection_code"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_users_collection_code", table_name="users")
    op.drop_column("users", "collection_code")
