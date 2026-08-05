"""Use partial unique indexes for root and nested Library folders.

Revision ID: 20260805_0002
Revises: 20260805_0001
"""

from alembic import op

revision = "20260805_0002"
down_revision = "20260805_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_deepspace_workspace_folders_parent_name",
        "deepspace_workspace_folders",
        type_="unique",
    )
    op.create_index(
        "uq_deepspace_workspace_folders_root_name",
        "deepspace_workspace_folders",
        ["conversation_id", "name"],
        unique=True,
        postgresql_where="parent_folder_id IS NULL",
    )
    op.create_index(
        "uq_deepspace_workspace_folders_parent_name",
        "deepspace_workspace_folders",
        ["conversation_id", "parent_folder_id", "name"],
        unique=True,
        postgresql_where="parent_folder_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_deepspace_workspace_folders_parent_name",
        table_name="deepspace_workspace_folders",
    )
    op.drop_index(
        "uq_deepspace_workspace_folders_root_name",
        table_name="deepspace_workspace_folders",
    )
    op.create_unique_constraint(
        "uq_deepspace_workspace_folders_parent_name",
        "deepspace_workspace_folders",
        ["conversation_id", "parent_folder_id", "name"],
    )
