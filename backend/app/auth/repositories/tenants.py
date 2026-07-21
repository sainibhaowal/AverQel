from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import set_db_tenant_context
from app.auth.models.tenant import Tenant
from app.system.repositories.base import BaseRepository


class TenantsRepository(BaseRepository):
    def create(self, tenant: Tenant) -> Tenant:
        self.db.add(tenant)
        return tenant

    def delete(self, *, tenant: Tenant) -> None:
        self.db.delete(tenant)

    def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        query = select(Tenant).where(Tenant.id == tenant_id)
        return self.db.execute(query).scalar_one_or_none()

    def list_all(self) -> list[Tenant]:
        set_db_tenant_context(self.db, "bypass")
        query = select(Tenant).order_by(Tenant.created_at.asc())
        return list(self.db.execute(query).scalars().all())
