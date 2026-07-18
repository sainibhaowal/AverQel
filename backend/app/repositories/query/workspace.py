from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.query.comment import Comment
from app.models.query.pinned_finding import PinnedFinding
from app.models.query.query import Query
from app.repositories.system.base import BaseRepository
from app.services.system.metrics_service import observe_db_query


class WorkspaceRepository(BaseRepository):
    def share_query(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        query_id: uuid.UUID,
        user_ids: list[uuid.UUID],
    ) -> None:
        self.apply_tenant_scope(tenant_id)
        query = select(Query).where(
            Query.tenant_id == tenant_id,
            Query.id == query_id,
            Query.user_id == actor_user_id,
        )
        with observe_db_query("workspace.share_query"):
            q_obj = self.db.execute(query).scalar_one_or_none()
            if q_obj is None:
                raise ValueError("Query is not owned by this user")
            current = set(q_obj.shared_with or [])
            current.update(user_ids)
            q_obj.shared_with = sorted(current, key=str)

    def can_access_query(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_id: uuid.UUID,
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = select(Query).where(
            Query.tenant_id == tenant_id,
            Query.id == query_id,
        )
        with observe_db_query("workspace.can_access_query"):
            row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            return False
        return row.user_id == user_id or user_id in set(row.shared_with or [])

    def pin_finding(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        query_id: uuid.UUID,
        chunk_id: uuid.UUID,
        notes: str,
    ) -> PinnedFinding:
        self.apply_tenant_scope(tenant_id)
        if not self.can_access_query(
            tenant_id=tenant_id,
            user_id=user_id,
            query_id=query_id,
        ):
            raise ValueError("Query is not accessible to this user")
        finding = PinnedFinding(
            tenant_id=tenant_id,
            user_id=user_id,
            query_id=query_id,
            chunk_id=chunk_id,
            notes=notes,
        )
        with observe_db_query("workspace.pin_finding"):
            self.db.add(finding)
            self.db.flush()
        return finding

    def get_pinned_findings(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[PinnedFinding]:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            select(PinnedFinding)
            .where(
                PinnedFinding.tenant_id == tenant_id,
                PinnedFinding.user_id == user_id,
            )
            .order_by(PinnedFinding.created_at.desc())
        )
        with observe_db_query("workspace.get_pinned_findings"):
            return list(self.db.execute(stmt).scalars().all())

    def add_comment(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        parent_id: uuid.UUID | None,
        content: str,
    ) -> Comment:
        self.apply_tenant_scope(tenant_id)
        if target_type == "query" and not self.can_access_query(
            tenant_id=tenant_id,
            user_id=user_id,
            query_id=target_id,
        ):
            raise ValueError("Query is not accessible to this user")
        c = Comment(
            tenant_id=tenant_id,
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            parent_id=parent_id,
            content=content,
        )
        with observe_db_query("workspace.add_comment"):
            self.db.add(c)
            self.db.flush()
        return c

    def get_comments(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
    ) -> list[Comment]:
        self.apply_tenant_scope(tenant_id)
        if target_type == "query" and not self.can_access_query(
            tenant_id=tenant_id,
            user_id=user_id,
            query_id=target_id,
        ):
            return []
        stmt = (
            select(Comment)
            .where(
                Comment.tenant_id == tenant_id,
                Comment.target_type == target_type,
                Comment.target_id == target_id,
            )
            .order_by(Comment.created_at.asc(), Comment.id.asc())
        )
        with observe_db_query("workspace.get_comments"):
            return list(self.db.execute(stmt).scalars().all())
