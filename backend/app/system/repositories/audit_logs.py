from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select

from app.platform.database.session import set_db_tenant_context
from app.system.models.audit_log import AuditLog
from app.system.repositories.base import BaseRepository


class AuditLogsRepository(BaseRepository):
    def create(self, *, event: AuditLog) -> AuditLog:
        self.apply_tenant_scope(event.tenant_id)
        self.db.add(event)
        self.db.flush()
        return event

    def list_page(
        self,
        *,
        tenant_id: uuid.UUID,
        limit: int,
        cursor_created_at: datetime | None,
        cursor_id: uuid.UUID | None,
        action: str | None,
    ) -> list[AuditLog]:
        self.apply_tenant_scope(tenant_id)

        statement = (
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )

        if action:
            statement = statement.where(AuditLog.action == action)

        if cursor_created_at is not None and cursor_id is not None:
            statement = statement.where(
                or_(
                    AuditLog.created_at < cursor_created_at,
                    and_(
                        AuditLog.created_at == cursor_created_at,
                        AuditLog.id < cursor_id,
                    ),
                )
            )

        return list(self.db.execute(statement).scalars().all())

    def delete_older_than(self, *, tenant_id: uuid.UUID, cutoff: datetime) -> int:
        self.apply_tenant_scope(tenant_id)

        count_statement = (
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.created_at < cutoff,
            )
        )
        rows = self.db.execute(count_statement).scalar() or 0

        if rows == 0:
            return 0

        delete_statement = delete(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.created_at < cutoff,
        )
        self.db.execute(delete_statement)
        self.db.flush()
        return int(rows)

    def list_for_actor(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        limit: int,
    ) -> list[AuditLog]:
        self.apply_tenant_scope(tenant_id)
        statement = (
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.actor_user_id == actor_user_id,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(statement).scalars().all())

    def list_for_actor_global(
        self,
        *,
        actor_user_id: uuid.UUID,
        limit: int,
    ) -> list[AuditLog]:
        set_db_tenant_context(self.db, "bypass")
        statement = (
            select(AuditLog)
            .where(AuditLog.actor_user_id == actor_user_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(self.db.execute(statement).scalars().all())
