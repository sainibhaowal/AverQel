"""simplify human roles to user, editor, admin

Revision ID: 20260407_0019
Revises: 20260402_0018
Create Date: 2026-04-07 00:00:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260407_0019"
down_revision = "20260402_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO roles (name, description)
        VALUES ('user', 'Standard user who can read documents and run queries.')
        ON CONFLICT (name) DO UPDATE
        SET description = EXCLUDED.description
        """)
    op.execute("""
        UPDATE roles
        SET description = CASE
            WHEN name = 'admin' THEN 'Platform admin with full administrative permissions.'
            WHEN name = 'editor' THEN 'Can upload documents, manage collections, and configure providers.'
            WHEN name = 'service' THEN 'Machine identity for scoped service operations.'
            ELSE description
        END
        WHERE name IN ('admin', 'editor', 'service')
        """)
    op.execute("""
        WITH role_ids AS (
            SELECT id, name
            FROM roles
            WHERE name IN ('user', 'reader', 'admin', 'super_admin')
        ),
        mapped_assignments AS (
            SELECT DISTINCT
                ur.tenant_id,
                ur.user_id,
                CASE
                    WHEN r.name = 'reader' THEN user_role.id
                    WHEN r.name = 'super_admin' THEN admin_role.id
                    ELSE ur.role_id
                END AS mapped_role_id
            FROM user_roles ur
            JOIN role_ids r ON r.id = ur.role_id
            LEFT JOIN role_ids user_role ON user_role.name = 'user'
            LEFT JOIN role_ids admin_role ON admin_role.name = 'admin'
            WHERE r.name IN ('reader', 'super_admin')
        )
        INSERT INTO user_roles (tenant_id, user_id, role_id)
        SELECT tenant_id, user_id, mapped_role_id
        FROM mapped_assignments
        WHERE mapped_role_id IS NOT NULL
        ON CONFLICT (tenant_id, user_id, role_id) DO NOTHING
        """)
    op.execute("""
        DELETE FROM user_roles
        WHERE role_id IN (
            SELECT id
            FROM roles
            WHERE name IN ('reader', 'super_admin')
        )
        """)
    op.execute("DELETE FROM roles WHERE name IN ('reader', 'super_admin')")


def downgrade() -> None:
    op.execute("""
        INSERT INTO roles (name, description)
        VALUES
            ('reader', 'Can run read-only knowledge queries.'),
            ('super_admin', 'Bootstrap platform owner with full control.')
        ON CONFLICT (name) DO NOTHING
        """)
    op.execute("""
        WITH role_ids AS (
            SELECT id, name
            FROM roles
            WHERE name IN ('user', 'reader', 'admin', 'super_admin')
        ),
        mapped_assignments AS (
            SELECT DISTINCT
                ur.tenant_id,
                ur.user_id,
                CASE
                    WHEN r.name = 'user' THEN reader_role.id
                    WHEN r.name = 'admin' THEN super_admin_role.id
                    ELSE ur.role_id
                END AS mapped_role_id
            FROM user_roles ur
            JOIN role_ids r ON r.id = ur.role_id
            LEFT JOIN role_ids reader_role ON reader_role.name = 'reader'
            LEFT JOIN role_ids super_admin_role ON super_admin_role.name = 'super_admin'
            WHERE r.name IN ('user', 'admin')
        )
        INSERT INTO user_roles (tenant_id, user_id, role_id)
        SELECT tenant_id, user_id, mapped_role_id
        FROM mapped_assignments
        WHERE mapped_role_id IS NOT NULL
        ON CONFLICT (tenant_id, user_id, role_id) DO NOTHING
        """)
    op.execute("""
        DELETE FROM user_roles
        WHERE role_id IN (
            SELECT id
            FROM roles
            WHERE name IN ('user')
        )
        """)
    op.execute("DELETE FROM roles WHERE name = 'user'")
    op.execute("""
        UPDATE roles
        SET description = CASE
            WHEN name = 'admin' THEN 'Tenant administrator with full permissions.'
            WHEN name = 'editor' THEN 'Can upload documents and run queries.'
            WHEN name = 'service' THEN 'Machine identity for scoped service operations.'
            ELSE description
        END
        WHERE name IN ('admin', 'editor', 'service')
        """)
