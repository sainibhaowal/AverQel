from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.repositories.refresh_tokens import RefreshTokensRepository
from app.auth.repositories.roles import RolesRepository
from app.auth.repositories.tenants import TenantsRepository
from app.auth.repositories.users import UsersRepository
from app.auth.roles import is_platform_admin_email
from app.core.config import Settings
from app.core.errors import ApiError
from app.documents.models.document import Document
from app.platform.database.session import set_db_tenant_context
from app.query.models.query import Query
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.models.support_ticket_attachment import SupportTicketAttachment
from app.system.services.audit_service import AuditService
from app.system.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AdminUserSummary:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str | None
    email: str
    is_active: bool
    totp_enabled: bool
    roles: list[str]


@dataclass(slots=True)
class AdminUserDeleteResult:
    deleted_user_id: uuid.UUID


@dataclass(slots=True)
class AdminTenantSummary:
    tenant_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    seats_used: int
    status: str


class AdminUserService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.users = UsersRepository(db)
        self.roles = RolesRepository(db)
        self.tenants = TenantsRepository(db)
        self.refresh_tokens = RefreshTokensRepository(db)
        self.audit = AuditService(db)
        self.storage = StorageService(settings)

    def list_users(self, *, tenant_id: uuid.UUID) -> list[AdminUserSummary]:
        users = self.users.list_by_tenant(tenant_id)
        if not users:
            return []

        tenant = self.tenants.get_by_id(tenant_id)
        role_map = {
            user.id: sorted(self.roles.get_role_names_for_user(tenant_id, user.id))
            for user in users
        }

        return [
            AdminUserSummary(
                user_id=user.id,
                tenant_id=user.tenant_id,
                tenant_name=tenant.name if tenant else None,
                email=user.email,
                is_active=user.is_active,
                totp_enabled=user.totp_enabled,
                roles=role_map.get(user.id, []),
            )
            for user in users
        ]

    def list_users_global(self) -> list[AdminUserSummary]:
        users = self.users.list_all()
        if not users:
            return []

        tenant_map = {tenant.id: tenant for tenant in self.tenants.list_all()}
        role_map = {
            user.id: sorted(self.roles.get_role_names_for_user_global(user_id=user.id))
            for user in users
        }
        summaries: list[AdminUserSummary] = []
        for user in users:
            tenant = tenant_map.get(user.tenant_id)
            summaries.append(
                AdminUserSummary(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    tenant_name=tenant.name if tenant is not None else None,
                    email=user.email,
                    is_active=user.is_active,
                    totp_enabled=user.totp_enabled,
                    roles=role_map.get(user.id, []),
                )
            )
        return summaries

    def get_user(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> AdminUserSummary:
        user = self.users.get_by_id(tenant_id, user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )
        roles = sorted(self.roles.get_role_names_for_user(tenant_id, user.id))
        tenant = self.tenants.get_by_id(tenant_id)
        return AdminUserSummary(
            user_id=user.id,
            tenant_id=user.tenant_id,
            tenant_name=tenant.name if tenant else None,
            email=user.email,
            is_active=user.is_active,
            totp_enabled=user.totp_enabled,
            roles=roles,
        )

    def get_user_global(self, *, user_id: uuid.UUID) -> AdminUserSummary:
        user = self.users.get_by_id_global(user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )
        roles = sorted(self.roles.get_role_names_for_user_global(user_id=user.id))
        tenant = self.tenants.get_by_id(user.tenant_id)
        return AdminUserSummary(
            user_id=user.id,
            tenant_id=user.tenant_id,
            tenant_name=tenant.name if tenant else None,
            email=user.email,
            is_active=user.is_active,
            totp_enabled=user.totp_enabled,
            roles=roles,
        )

    def update_staff_roles_global(
        self,
        *,
        user_id: uuid.UUID,
        role_names: Sequence[str],
        actor: AuthContext,
    ) -> AdminUserSummary:
        """Grant or revoke only explicitly assigned content-bearing staff roles."""
        permitted_staff_roles = {
            "feedback_manager",
            "collection_moderator",
            "support_manager",
        }
        desired_roles = set(role_names)
        if not desired_roles.issubset(permitted_staff_roles):
            raise ApiError(
                code="INVALID_STAFF_ROLE",
                message="Only designated support, feedback, and moderation roles can be changed here.",
                status_code=422,
            )

        set_db_tenant_context(self.db, "bypass")
        user = self.users.get_by_id_global(user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )

        assigned_roles = self.roles.get_role_names_for_user_global(user_id=user.id)
        current_staff_roles = assigned_roles & permitted_staff_roles
        if not assigned_roles - permitted_staff_roles:
            raise ApiError(
                code="BASE_ROLE_REQUIRED",
                message="A user must retain a normal account role in addition to staff roles.",
                status_code=409,
            )
        if current_staff_roles != desired_roles:
            for role_name in sorted(desired_roles - current_staff_roles):
                role = self.roles.get_by_name(role_name)
                if role is None:
                    raise ApiError(
                        code="STAFF_ROLE_NOT_CONFIGURED",
                        message="Run the latest database migration before assigning staff roles.",
                        status_code=503,
                    )
                self.db.add(
                    UserRole(
                        tenant_id=user.tenant_id,
                        user_id=user.id,
                        role_id=role.id,
                    )
                )

            for role_name in sorted(current_staff_roles - desired_roles):
                role = self.roles.get_by_name(role_name)
                if role is not None:
                    self.db.execute(
                        delete(UserRole).where(
                            UserRole.tenant_id == user.tenant_id,
                            UserRole.user_id == user.id,
                            UserRole.role_id == role.id,
                        )
                    )

            self.audit.write_event(
                tenant_id=actor.tenant_id,
                action="admin.user.staff_roles.updated",
                resource_type="user",
                resource_id=str(user.id),
                actor_user_id=actor.user_id,
                details={
                    "roles": ",".join(sorted(desired_roles)),
                    "target_tenant_id": user.tenant_id,
                },
            )
            self.db.commit()

        return self.get_user_global(user_id=user.id)

    def list_tenants_global(self) -> list[AdminTenantSummary]:
        # Include empty tenants so platform operators can see their full lifecycle.
        tenants = self.tenants.list_all()
        if not tenants:
            return []
        tenant_ids = [tenant.id for tenant in tenants]
        seats_used = self._tenant_seat_count_map(tenant_ids=tenant_ids)
        return [
            AdminTenantSummary(
                tenant_id=tenant.id,
                name=tenant.name,
                created_at=tenant.created_at,
                updated_at=tenant.updated_at,
                seats_used=seats_used.get(tenant.id, 0),
                status="active" if seats_used.get(tenant.id, 0) else "empty",
            )
            for tenant in tenants
        ]

    def disable_user(
        self,
        *,
        tenant_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor: AuthContext,
    ) -> None:
        user = self._guard_target_user(
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            actor=actor,
            allow_self=False,
        )
        user.is_active = False
        user.access_token_version += 1
        self.refresh_tokens.revoke_all_for_user(
            tenant_id=tenant_id,
            user_id=user.id,
            reason="disabled_by_admin",
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            action="admin.user.disabled",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=actor.user_id,
        )
        self.db.commit()

    def reactivate_user(
        self,
        *,
        tenant_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor: AuthContext,
    ) -> None:
        user = self._guard_target_user(
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            actor=actor,
            allow_self=True,
        )
        user.is_active = True
        user.failed_login_attempts = 0
        user.locked_until = None
        self.audit.write_event(
            tenant_id=tenant_id,
            action="admin.user.reactivated",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=actor.user_id,
        )
        self.db.commit()

    def force_logout_user(
        self,
        *,
        tenant_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor: AuthContext,
    ) -> None:
        user = self._guard_target_user(
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            actor=actor,
            allow_self=True,
        )
        user.access_token_version += 1
        self.refresh_tokens.revoke_all_for_user(
            tenant_id=tenant_id,
            user_id=user.id,
            reason="forced_logout_by_admin",
        )
        self.audit.write_event(
            tenant_id=tenant_id,
            action="admin.user.force_logout",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=actor.user_id,
        )
        self.db.commit()

    def delete_user(
        self,
        *,
        tenant_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor: AuthContext,
    ) -> AdminUserDeleteResult:
        user = self._guard_target_user(
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            actor=actor,
            allow_self=False,
        )

        objects = list(
            self.db.execute(
                select(Document.storage_bucket, Document.storage_object_key).where(
                    Document.tenant_id == tenant_id,
                    Document.uploaded_by_user_id == user.id,
                )
            ).all()
        )
        attachment_objects = list(
            self.db.execute(
                select(
                    SupportTicketAttachment.storage_bucket, SupportTicketAttachment.storage_key
                ).where(
                    SupportTicketAttachment.tenant_id == tenant_id,
                    SupportTicketAttachment.uploaded_by_user_id == user.id,
                )
            ).all()
        )
        for bucket, object_key in objects:
            try:
                self.storage.delete_object(
                    bucket=str(bucket), object_key=str(object_key), raise_on_error=True
                )
            except Exception:  # noqa: BLE001
                self.db.add(
                    StorageCleanupJob(
                        tenant_id=tenant_id,
                        owner_user_id=user.id,
                        bucket=str(bucket),
                        object_key=str(object_key),
                        last_error="storage_delete_failed",
                    )
                )
                logger.warning(
                    "User-owned file cleanup was queued after object deletion failed.",
                )

        for bucket, object_key in attachment_objects:
            try:
                self.storage.delete_tenant_object(
                    tenant_id=tenant_id,
                    bucket=str(bucket),
                    object_key=str(object_key),
                    raise_on_error=True,
                )
            except Exception:  # noqa: BLE001
                self.db.add(
                    StorageCleanupJob(
                        tenant_id=tenant_id,
                        owner_user_id=user.id,
                        bucket=str(bucket),
                        object_key=str(object_key),
                        last_error="support_attachment_storage_delete_failed",
                    )
                )
                logger.warning(
                    "User support attachment cleanup was queued after object deletion failed.",
                )

        self.refresh_tokens.revoke_all_for_user(
            tenant_id=tenant_id,
            user_id=user.id,
            reason="deleted_by_admin",
        )
        self.db.execute(
            delete(Query).where(
                Query.tenant_id == tenant_id,
                Query.user_id == user.id,
            )
        )
        self.db.execute(
            delete(Document).where(
                Document.tenant_id == tenant_id,
                Document.uploaded_by_user_id == user.id,
            )
        )
        self.users.delete(tenant_id=tenant_id, user=user)
        if self.users.count_by_tenant(tenant_id) == 0:
            tenant = self.tenants.get_by_id(tenant_id)
            if tenant is not None:
                self.tenants.delete(tenant=tenant)
        self.audit.write_event(
            tenant_id=tenant_id,
            action="admin.user.deleted",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=actor.user_id,
        )
        self.db.commit()

        return AdminUserDeleteResult(deleted_user_id=user.id)

    def _guard_target_user(
        self,
        *,
        tenant_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor: AuthContext,
        allow_self: bool,
    ) -> User:
        user = self.users.get_by_id(tenant_id, target_user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )
        if not allow_self and user.id == actor.user_id:
            raise ApiError(
                code="FORBIDDEN",
                message="This action is not allowed on your own account.",
                status_code=403,
            )
        if self._is_bootstrap_super_admin_email(user.email):
            raise ApiError(
                code="FORBIDDEN",
                message="Bootstrap admin account cannot be modified here.",
                status_code=403,
            )
        return user

    def _is_bootstrap_super_admin_email(self, email: str) -> bool:
        return is_platform_admin_email(email, self.settings.bootstrap_super_admin_emails)

    def _tenant_seat_count_map(self, *, tenant_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        set_db_tenant_context(self.db, "bypass")
        rows = self.db.execute(
            select(User.tenant_id, func.count())
            .where(User.tenant_id.in_(tenant_ids))
            .group_by(User.tenant_id)
        ).all()
        return {tenant_id: int(count) for tenant_id, count in rows}
