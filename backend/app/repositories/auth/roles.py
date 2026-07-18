from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.roles import canonicalize_role_name
from app.db.session import set_db_tenant_context
from app.models.auth.role import Role
from app.models.auth.user_role import UserRole
from app.repositories.system.base import BaseRepository


class RolesRepository(BaseRepository):
    def get_by_name(self, name: str) -> Role | None:
        query = select(Role).where(Role.name == canonicalize_role_name(name))
        return self.db.execute(query).scalar_one_or_none()

    def get_role_names_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> set[str]:
        self.apply_tenant_scope(tenant_id)
        query = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.tenant_id == tenant_id,
                UserRole.user_id == user_id,
            )
        )
        return {
            canonicalize_role_name(str(name))
            for name in self.db.execute(query).scalars().all()
        }

    def get_role_names_for_user_global(self, *, user_id: uuid.UUID) -> set[str]:
        set_db_tenant_context(self.db, "bypass")
        query = (
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return {
            canonicalize_role_name(str(name))
            for name in self.db.execute(query).scalars().all()
        }
