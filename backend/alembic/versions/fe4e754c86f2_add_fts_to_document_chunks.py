"""add_fts_to_document_chunks

Revision ID: fe4e754c86f2
Revises: 3e548a995610
Create Date: 2026-03-02 14:28:22.673091
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

# revision identifiers, used by Alembic.
revision = "fe4e754c86f2"
down_revision = "3e548a995610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add tsvector column
    op.add_column("document_chunks", sa.Column("search_vector", TSVECTOR(), nullable=True))

    # 2. Add GIN index
    op.create_index(
        "ix_document_chunks_fts",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )

    # 3. Create function and trigger for automatic updates
    op.execute("""
        CREATE FUNCTION document_chunks_fts_trigger() RETURNS trigger AS $$
        begin
          new.search_vector := to_tsvector('english', coalesce(new.content, ''));
          return new;
        end
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
        ON document_chunks FOR EACH ROW EXECUTE FUNCTION document_chunks_fts_trigger();
        """)

    # 4. Populate existing rows
    op.execute(
        "UPDATE document_chunks SET search_vector = to_tsvector('english', coalesce(content, ''))"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tsvectorupdate ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS document_chunks_fts_trigger()")
    op.drop_index("ix_document_chunks_fts", table_name="document_chunks")
    op.drop_column("document_chunks", "search_vector")
