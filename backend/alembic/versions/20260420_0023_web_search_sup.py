"""Compatibility migration for the database state currently stamped at
20260420_0023_web_search_sup.

The database has already been stamped to this revision, but this checkout does
not include the original migration file. Keeping the revision id available
prevents Alembic from failing during application startup.
"""

# revision identifiers, used by Alembic.
revision = "20260420_0023_web_search_sup"
down_revision = "20260402_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
