"""Add folders, binary storage metadata, and immutable Library revisions."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260805_0001"
down_revision = "20260804_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_workspace_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_folder_id"], ["deepspace_workspace_folders.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "parent_folder_id",
            "name",
            name="uq_deepspace_workspace_folders_parent_name",
        ),
    )
    for column in ("tenant_id", "user_id", "conversation_id", "parent_folder_id"):
        op.create_index(
            f"ix_deepspace_workspace_folders_{column}",
            "deepspace_workspace_folders",
            [column],
        )

    op.add_column(
        "deepspace_workspace_files",
        sa.Column("parent_folder_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "deepspace_workspace_files",
        sa.Column("storage_bucket", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "deepspace_workspace_files",
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "deepspace_workspace_files",
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "deepspace_workspace_files",
        sa.Column("extracted_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "deepspace_workspace_files",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "deepspace_workspace_files",
        sa.Column("is_binary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_deepspace_workspace_files_parent_folder",
        "deepspace_workspace_files",
        "deepspace_workspace_folders",
        ["parent_folder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_deepspace_workspace_files_parent_folder_id",
        "deepspace_workspace_files",
        ["parent_folder_id"],
    )
    op.create_index(
        "ix_deepspace_workspace_files_checksum_sha256",
        "deepspace_workspace_files",
        ["checksum_sha256"],
    )
    op.drop_constraint(
        "uq_deepspace_workspace_files_conversation_name",
        "deepspace_workspace_files",
        type_="unique",
    )
    op.create_index(
        "uq_deepspace_workspace_files_root_name",
        "deepspace_workspace_files",
        ["conversation_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_folder_id IS NULL"),
    )
    op.create_index(
        "uq_deepspace_workspace_files_folder_name",
        "deepspace_workspace_files",
        ["conversation_id", "parent_folder_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_folder_id IS NOT NULL"),
    )

    op.create_table(
        "deepspace_workspace_file_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=127), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("storage_bucket", sa.String(length=255), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["file_id"], ["deepspace_workspace_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "file_id", "version", name="uq_deepspace_workspace_file_versions_number"
        ),
    )
    for column in ("file_id", "tenant_id", "user_id", "conversation_id"):
        op.create_index(
            f"ix_deepspace_workspace_file_versions_{column}",
            "deepspace_workspace_file_versions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("deepspace_workspace_file_versions")
    op.drop_index(
        "ix_deepspace_workspace_files_checksum_sha256",
        table_name="deepspace_workspace_files",
    )
    op.drop_index(
        "ix_deepspace_workspace_files_parent_folder_id",
        table_name="deepspace_workspace_files",
    )
    op.drop_constraint(
        "fk_deepspace_workspace_files_parent_folder",
        "deepspace_workspace_files",
        type_="foreignkey",
    )
    op.drop_index(
        "uq_deepspace_workspace_files_folder_name",
        table_name="deepspace_workspace_files",
    )
    op.drop_index("uq_deepspace_workspace_files_root_name", table_name="deepspace_workspace_files")
    for column in (
        "is_binary",
        "version",
        "extracted_text",
        "checksum_sha256",
        "storage_key",
        "storage_bucket",
        "parent_folder_id",
    ):
        op.drop_column("deepspace_workspace_files", column)
    op.create_unique_constraint(
        "uq_deepspace_workspace_files_conversation_name",
        "deepspace_workspace_files",
        ["conversation_id", "name"],
    )
    for column in ("parent_folder_id", "conversation_id", "user_id", "tenant_id"):
        op.drop_index(
            f"ix_deepspace_workspace_folders_{column}",
            table_name="deepspace_workspace_folders",
        )
    op.drop_table("deepspace_workspace_folders")
