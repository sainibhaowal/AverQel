from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.platform.database.session import set_db_tenant_context


class BaseRepository:
    def __init__(self, db: Session):
        self.db = db

    def apply_tenant_scope(self, tenant_id: UUID) -> None:
        set_db_tenant_context(self.db, tenant_id)
