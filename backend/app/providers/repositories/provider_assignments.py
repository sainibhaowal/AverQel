from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select, update

from app.providers.models.provider_assignment import ProviderAssignment
from app.system.repositories.base import BaseRepository


class ProviderAssignmentsRepository(BaseRepository):
    def create(self, assignment: ProviderAssignment) -> ProviderAssignment:
        self.apply_tenant_scope(assignment.tenant_id)
        if not assignment.visibility_scope:
            assignment.visibility_scope = "user"
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def list_assignments(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> Sequence[ProviderAssignment]:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderAssignment).where(ProviderAssignment.tenant_id == tenant_id)
        stmt = stmt.where(ProviderAssignment.workspace_id.is_(None))
        if owner_user_id is not None:
            stmt = stmt.where(
                or_(
                    ProviderAssignment.owner_user_id == owner_user_id,
                    ProviderAssignment.visibility_scope == "system",
                )
            )
        else:
            stmt = stmt.where(ProviderAssignment.visibility_scope.in_(("tenant", "system")))
        stmt = stmt.order_by(
            ProviderAssignment.feature_scope.asc(), ProviderAssignment.priority.asc()
        )
        return self.db.execute(stmt).scalars().all()

    def get_active_assignment(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        feature_scope: str,
        owner_user_id: uuid.UUID | None = None,
    ) -> ProviderAssignment | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderAssignment).where(
            ProviderAssignment.tenant_id == tenant_id,
            ProviderAssignment.feature_scope == feature_scope,
            ProviderAssignment.enabled.is_(True),
        )
        stmt = stmt.where(ProviderAssignment.workspace_id.is_(None))
        if owner_user_id is not None:
            stmt = stmt.where(
                or_(
                    ProviderAssignment.owner_user_id == owner_user_id,
                    ProviderAssignment.visibility_scope == "system",
                )
            )
        else:
            stmt = stmt.where(ProviderAssignment.visibility_scope.in_(("tenant", "system")))
        stmt = stmt.order_by(ProviderAssignment.priority.asc(), ProviderAssignment.created_at.asc())
        return self.db.execute(stmt).scalars().first()

    def get_by_scope_and_priority(
        self,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID | None,
        feature_scope: str,
        priority: int,
        owner_user_id: uuid.UUID | None = None,
    ) -> ProviderAssignment | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderAssignment).where(
            ProviderAssignment.tenant_id == tenant_id,
            ProviderAssignment.feature_scope == feature_scope,
            ProviderAssignment.priority == priority,
        )
        stmt = stmt.where(ProviderAssignment.workspace_id.is_(None))
        if owner_user_id is not None:
            stmt = stmt.where(ProviderAssignment.owner_user_id == owner_user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert_assignment(self, assignment: ProviderAssignment) -> ProviderAssignment:
        self.apply_tenant_scope(assignment.tenant_id)
        if not assignment.visibility_scope:
            assignment.visibility_scope = "user"
        existing = self.get_by_scope_and_priority(
            tenant_id=assignment.tenant_id,
            workspace_id=assignment.workspace_id,
            feature_scope=assignment.feature_scope,
            priority=assignment.priority,
            owner_user_id=assignment.owner_user_id,
        )
        if existing is None:
            self.db.add(assignment)
            self.db.flush()
            return assignment
        existing.provider_config_id = assignment.provider_config_id
        existing.model_name = assignment.model_name
        existing.enabled = assignment.enabled
        self.db.flush()
        return existing

    def get_by_id(
        self,
        *,
        tenant_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> ProviderAssignment | None:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderAssignment).where(
            ProviderAssignment.tenant_id == tenant_id,
            ProviderAssignment.id == assignment_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_fields(
        self,
        *,
        tenant_id: uuid.UUID,
        assignment_id: uuid.UUID,
        values: dict[str, object],
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = (
            update(ProviderAssignment)
            .where(
                ProviderAssignment.tenant_id == tenant_id,
                ProviderAssignment.id == assignment_id,
            )
            .values(**values)
        )
        result = self.db.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]

    def count_active_for_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> int:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderAssignment).where(
            ProviderAssignment.tenant_id == tenant_id,
            ProviderAssignment.provider_config_id == provider_config_id,
            ProviderAssignment.enabled.is_(True),
        )
        return len(self.db.execute(stmt).scalars().all())

    def list_for_provider(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        enabled_only: bool = False,
    ) -> Sequence[ProviderAssignment]:
        self.apply_tenant_scope(tenant_id)
        stmt = select(ProviderAssignment).where(
            ProviderAssignment.tenant_id == tenant_id,
            ProviderAssignment.provider_config_id == provider_config_id,
        )
        if enabled_only:
            stmt = stmt.where(ProviderAssignment.enabled.is_(True))
        stmt = stmt.order_by(ProviderAssignment.priority.asc(), ProviderAssignment.created_at.asc())
        return self.db.execute(stmt).scalars().all()

    def delete(
        self,
        *,
        tenant_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> bool:
        self.apply_tenant_scope(tenant_id)
        stmt = delete(ProviderAssignment).where(
            ProviderAssignment.tenant_id == tenant_id,
            ProviderAssignment.id == assignment_id,
        )
        result = self.db.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)  # type: ignore[attr-defined]
