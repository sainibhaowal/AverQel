"""add tenant isolation to connector tables

Revision ID: 20260527_0001
Revises: 30c4039401e5
Create Date: 2026-05-27 00:00:01.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260527_0001"
down_revision = "30c4039401e5"
branch_labels = None
depends_on = None


def _create_rls_policy(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation_{table_name}
        ON {table_name}
        USING (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        """)


def _drop_rls_policy(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    _create_rls_policy("connectors")
    _create_rls_policy("connector_secrets")


def downgrade() -> None:
    _drop_rls_policy("connector_secrets")
    _drop_rls_policy("connectors")
