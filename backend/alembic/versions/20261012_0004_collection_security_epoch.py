"""Track membership security epochs for collection security notifications."""

import sqlalchemy as sa

from alembic import op

revision = "20261012_0004"
down_revision = "20261012_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_collections",
        sa.Column("security_epoch", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("document_collections", "security_epoch")
