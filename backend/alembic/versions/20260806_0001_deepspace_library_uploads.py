"""Add durable resumable DeepSpace Library uploads.

Revision ID: 20260806_0001
Revises: 20260805_0002
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260806_0001"
down_revision = "20260805_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_library_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=127), nullable=False),
        sa.Column("expected_size", sa.Integer(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column(
            "received_chunks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("bytes_received", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["deepspace_workspace_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["parent_folder_id"],
            ["deepspace_workspace_folders.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deepspace_library_uploads_owner_status",
        "deepspace_library_uploads",
        ["tenant_id", "user_id", "status"],
    )
    op.create_index(
        "ix_deepspace_library_uploads_conversation_status",
        "deepspace_library_uploads",
        ["conversation_id", "status"],
    )
    op.create_index(
        "ix_deepspace_library_uploads_tenant_id",
        "deepspace_library_uploads",
        ["tenant_id"],
    )
    op.create_index(
        "ix_deepspace_library_uploads_user_id", "deepspace_library_uploads", ["user_id"]
    )
    op.create_index(
        "ix_deepspace_library_uploads_conversation_id",
        "deepspace_library_uploads",
        ["conversation_id"],
    )
    op.create_index(
        "ix_deepspace_library_uploads_parent_folder_id",
        "deepspace_library_uploads",
        ["parent_folder_id"],
    )
    op.create_index("ix_deepspace_library_uploads_status", "deepspace_library_uploads", ["status"])


def downgrade() -> None:
    op.drop_table("deepspace_library_uploads")
