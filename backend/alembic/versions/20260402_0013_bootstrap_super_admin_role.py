"""add bootstrap super admin role and normalize default user roles

Revision ID: 20260402_0013
Revises: b7c8d9e0f1a2
Create Date: 2026-04-02 00:00:00
"""

from __future__ import annotations

import json
import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260402_0013"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def _load_bootstrap_super_admin_emails() -> list[str]:
    raw = os.getenv("AKS_BOOTSTRAP_SUPER_ADMIN_EMAILS", "").strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw.split(",")]

    if isinstance(parsed, str):
        parsed = [parsed]

    if not isinstance(parsed, list):
        return []

    normalized: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        cleaned = item.strip().lower()
        if "@" not in cleaned or cleaned in normalized:
            continue
        normalized.append(cleaned)
    return normalized


def upgrade() -> None:
    op.execute("""
        INSERT INTO roles (name, description)
        VALUES ('super_admin', 'Bootstrap platform owner with full control.')
        ON CONFLICT (name) DO NOTHING
        """)

    bootstrap_super_admin_emails = _load_bootstrap_super_admin_emails()
    if not bootstrap_super_admin_emails:
        return

    connection = op.get_bind()
    user_roles = sa.table(
        "user_roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
    )
    users = sa.table(
        "users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("email", sa.String()),
    )
    roles = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
    )

    role_rows = connection.execute(
        sa.select(roles.c.id, roles.c.name).where(
            roles.c.name.in_(["super_admin", "editor"])
        )
    ).all()
    role_ids = {row.name: row.id for row in role_rows}
    super_admin_role_id = role_ids.get("super_admin")
    editor_role_id = role_ids.get("editor")
    if super_admin_role_id is None or editor_role_id is None:
        return

    target_users = connection.execute(
        sa.select(users.c.id, users.c.tenant_id, users.c.email)
    ).all()
    for user in target_users:
        normalized_email = str(user.email).strip().lower()
        desired_role_id = (
            super_admin_role_id
            if normalized_email in bootstrap_super_admin_emails
            else editor_role_id
        )
        connection.execute(
            sa.delete(user_roles).where(
                user_roles.c.tenant_id == user.tenant_id,
                user_roles.c.user_id == user.id,
            )
        )
        connection.execute(
            sa.insert(user_roles).values(
                tenant_id=user.tenant_id,
                user_id=user.id,
                role_id=desired_role_id,
            )
        )


def downgrade() -> None:
    op.execute("""
        DELETE FROM user_roles
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'super_admin')
        """)
    op.execute("DELETE FROM roles WHERE name = 'super_admin'")
