from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "20260402_0015"
down_revision = "20260402_0014"
branch_labels = None
depends_on = None


def _code_for_id(value: uuid.UUID) -> str:
    return str(value).replace("-", "").upper()[:10]


def upgrade() -> None:
    op.add_column(
        "document_collections",
        sa.Column("connection_code", sa.String(length=16), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM document_collections")).fetchall()
    for row in rows:
        collection_id = row[0]
        bind.execute(
            sa.text("UPDATE document_collections SET connection_code = :code WHERE id = :id"),
            {"id": collection_id, "code": _code_for_id(collection_id)},
        )

    op.alter_column("document_collections", "connection_code", nullable=False)
    op.create_index(
        "ix_document_collections_connection_code",
        "document_collections",
        ["connection_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_document_collections_connection_code", table_name="document_collections")
    op.drop_column("document_collections", "connection_code")
