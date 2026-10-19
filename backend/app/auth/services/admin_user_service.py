from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.auth.models.user import User
from app.auth.repositories.refresh_tokens import RefreshTokensRepository
from app.auth.repositories.roles import RolesRepository
from app.auth.repositories.tenants import TenantsRepository
from app.auth.repositories.users import UsersRepository
from app.auth.roles import is_platform_admin_email
from app.core.config import Settings
from app.core.errors import ApiError
from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.documents.models.collection import CollectionChatMedia
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.data_deletion import DataDeletion
from app.documents.models.document import Document
from app.documents.models.organization import (
    DocumentAutomationSchedule,
    DocumentAutomationScheduleRun,
    DocumentClassificationRule,
    DocumentClassificationRun,
    DocumentShare,
    DocumentShareLink,
    DocumentSmartCollection,
    DocumentSmartCollectionEvaluation,
    DocumentWebhookSubscription,
)
from app.integrations.models.mcp_server import MCPEvent
from app.platform.database.session import set_db_tenant_context
from app.query.models.dataset_index import QueryDatasetIndex
from app.query.models.query import Query
from app.system.models.app_feedback_message import AppFeedbackMessage
from app.system.models.audit_log import AuditLog
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.models.storage_lifecycle import StorageLifecycleItem, StorageQuotaReservation
from app.system.models.support_ticket_attachment import SupportTicketAttachment
from app.system.models.support_ticket_message import SupportTicketMessage
from app.system.models.usage_record import UsageRecord
from app.system.services.audit_service import AuditService


@dataclass(slots=True)
class AdminUserSummary:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str | None
    email: str
    is_active: bool
    totp_enabled: bool
    roles: list[str]
    created_at: datetime
    last_login_at: datetime | None


@dataclass(slots=True)
class AdminUserDeleteResult:
    deleted_user_id: uuid.UUID
    pending_storage_cleanup_count: int


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
                created_at=user.created_at,
                last_login_at=user.last_login_at,
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
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
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
            created_at=user.created_at,
            last_login_at=user.last_login_at,
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
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )

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
        set_db_tenant_context(self.db, tenant_id)
        user = self._guard_target_user(
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            actor=actor,
            allow_self=False,
        )

        pending_deletions = list(
            self.db.execute(
                select(DataDeletion.status)
                .where(
                    DataDeletion.tenant_id == tenant_id,
                    DataDeletion.requested_by_user_id == user.id,
                )
                .with_for_update()
            ).scalars()
        )
        if any(status in {"processing", "in_progress"} for status in pending_deletions):
            raise ApiError(
                code="ACCOUNT_DELETION_IN_PROGRESS",
                message="A workspace deletion requested by this account is already processing. Retry account deletion when it finishes.",
                status_code=409,
            )

        storage_objects: set[tuple[str, str]] = set()
        storage_queries = (
            select(Document.storage_bucket, Document.storage_object_key).where(
                Document.tenant_id == tenant_id,
                Document.uploaded_by_user_id == user.id,
            ),
            select(QueryDatasetIndex.derivative_bucket, QueryDatasetIndex.derivative_object_key)
            .join(Document, QueryDatasetIndex.document_id == Document.id)
            .where(Document.tenant_id == tenant_id, Document.uploaded_by_user_id == user.id),
            select(
                SupportTicketAttachment.storage_bucket,
                SupportTicketAttachment.storage_key,
            ).where(
                SupportTicketAttachment.tenant_id == tenant_id,
                SupportTicketAttachment.uploaded_by_user_id == user.id,
            ),
            select(CollectionChatMedia.bucket, CollectionChatMedia.object_key).where(
                CollectionChatMedia.tenant_id == tenant_id,
                CollectionChatMedia.uploaded_by_user_id == user.id,
            ),
            select(DeepSpaceMediaArtifact.storage_bucket, DeepSpaceMediaArtifact.storage_key).where(
                DeepSpaceMediaArtifact.tenant_id == tenant_id,
                DeepSpaceMediaArtifact.user_id == user.id,
            ),
            select(DeepSpaceWorkspaceFile.storage_bucket, DeepSpaceWorkspaceFile.storage_key).where(
                DeepSpaceWorkspaceFile.tenant_id == tenant_id,
                DeepSpaceWorkspaceFile.user_id == user.id,
            ),
            select(
                DeepSpaceWorkspaceFileVersion.storage_bucket,
                DeepSpaceWorkspaceFileVersion.storage_key,
            ).where(
                DeepSpaceWorkspaceFileVersion.tenant_id == tenant_id,
                DeepSpaceWorkspaceFileVersion.user_id == user.id,
            ),
        )
        for query in storage_queries:
            for bucket, object_key in self.db.execute(query).all():
                if bucket and object_key:
                    storage_objects.add((str(bucket), str(object_key)))

        if self.settings.minio_bucket:
            uploads = self.db.execute(
                select(DeepSpaceLibraryUpload.id, DeepSpaceLibraryUpload.total_chunks).where(
                    DeepSpaceLibraryUpload.tenant_id == tenant_id,
                    DeepSpaceLibraryUpload.user_id == user.id,
                )
            ).all()
            for upload_id, total_chunks in uploads:
                for chunk_index in range(max(0, int(total_chunks))):
                    storage_objects.add(
                        (
                            self.settings.minio_bucket,
                            f"{tenant_id}/library-uploads/{upload_id}/chunk-{chunk_index:08d}",
                        )
                    )

        for bucket, object_key in sorted(storage_objects):
            self.db.add(
                StorageCleanupJob(
                    tenant_id=tenant_id,
                    owner_user_id=None,
                    bucket=bucket,
                    object_key=object_key,
                )
            )

        self.refresh_tokens.revoke_all_for_user(
            tenant_id=tenant_id,
            user_id=user.id,
            reason="deleted_by_admin",
        )
        self.db.execute(
            delete(DataDeletion).where(
                DataDeletion.tenant_id == tenant_id,
                DataDeletion.requested_by_user_id == user.id,
            )
        )
        self.db.execute(
            delete(UsageRecord).where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.user_id == user.id,
            )
        )
        self.db.execute(
            delete(AgentTodo).where(
                AgentTodo.tenant_id == str(tenant_id),
                AgentTodo.user_id == str(user.id),
            )
        )
        self.db.execute(
            delete(DeepSpaceMissionSnapshot).where(
                DeepSpaceMissionSnapshot.tenant_id == tenant_id,
                DeepSpaceMissionSnapshot.user_id == user.id,
            )
        )
        for model in (
            DocumentSmartCollection,
            DocumentShare,
            DocumentWebhookSubscription,
            DocumentShareLink,
            DocumentClassificationRule,
            DocumentAutomationSchedule,
        ):
            self.db.execute(
                delete(model).where(
                    model.tenant_id == tenant_id,
                    model.created_by_user_id == user.id,
                )
            )
        self.db.execute(
            delete(SupportTicketMessage).where(
                SupportTicketMessage.tenant_id == tenant_id,
                SupportTicketMessage.author_user_id == user.id,
            )
        )
        self.db.execute(
            delete(AppFeedbackMessage).where(
                AppFeedbackMessage.tenant_id == tenant_id,
                AppFeedbackMessage.author_user_id == user.id,
            )
        )
        for run_model in (
            DocumentSmartCollectionEvaluation,
            DocumentClassificationRun,
            DocumentAutomationScheduleRun,
        ):
            self.db.execute(
                delete(run_model).where(
                    run_model.tenant_id == tenant_id,
                    run_model.actor_user_id == user.id,
                )
            )
        self.db.execute(
            delete(StorageLifecycleItem).where(
                StorageLifecycleItem.tenant_id == tenant_id,
                StorageLifecycleItem.owner_user_id == user.id,
            )
        )
        self.db.execute(
            delete(StorageQuotaReservation).where(
                StorageQuotaReservation.tenant_id == tenant_id,
                StorageQuotaReservation.owner_user_id == user.id,
            )
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

        # Clean up pseudonymous references in retry jobs and audit history before removing the
        # account. Audit action/time/status remain as a minimal security record; identity and
        # resource details are removed.
        set_db_tenant_context(self.db, "bypass")
        self.db.execute(
            delete(MCPEvent).where(
                MCPEvent.tenant_id == tenant_id,
                MCPEvent.user_id == user.id,
            )
        )
        self.db.execute(
            update(CollectionNotification)
            .where(CollectionNotification.actor_user_id == user.id)
            .values(
                actor_user_id=None,
                message="A workspace member updated a shared item.",
            )
        )
        self.db.execute(
            delete(StorageCleanupJob).where(
                StorageCleanupJob.owner_user_id == user.id,
                StorageCleanupJob.status == "completed",
            )
        )
        self.db.execute(
            update(StorageCleanupJob)
            .where(StorageCleanupJob.owner_user_id == user.id)
            .values(owner_user_id=None)
        )
        self.db.execute(
            update(AuditLog)
            .where(AuditLog.actor_user_id == user.id)
            .values(actor_user_id=None, resource_id=None, ip_address=None, details={})
        )
        self.db.execute(
            update(AuditLog)
            .where(AuditLog.resource_id == str(user.id))
            .values(resource_id=None, details={})
        )
        self.db.execute(
            update(AuditLog)
            .where(
                or_(
                    AuditLog.details["target_user_id"].astext == str(user.id),
                    AuditLog.details["user_id"].astext == str(user.id),
                )
            )
            .values(details={})
        )
        set_db_tenant_context(self.db, tenant_id)

        self.users.delete(tenant_id=tenant_id, user=user)
        # Flush while the target tenant is active. The platform-wide admin audit
        # event below switches RLS context to the acting admin's tenant, which
        # would otherwise make this cross-tenant DELETE match zero rows.
        self.db.flush()
        tenant_removed = False
        if self.users.count_by_tenant(tenant_id) == 0:
            tenant = self.tenants.get_by_id(tenant_id)
            if tenant is not None:
                self.tenants.delete(tenant=tenant)
                # The tenant row has the same RLS requirement; remove it before
                # the audit service switches the session to the actor's tenant.
                self.db.flush()
                tenant_removed = True
        self.audit.write_event(
            tenant_id=actor.tenant_id,
            action="admin.user.account_erased",
            resource_type="account",
            resource_id=str(user.id),
            actor_user_id=actor.user_id,
            details={
                "target_user_id": str(user.id),
                "storage_cleanup_jobs_pending": len(storage_objects),
                "target_tenant_removed": tenant_removed,
            },
        )
        self.db.commit()

        return AdminUserDeleteResult(
            deleted_user_id=user.id,
            pending_storage_cleanup_count=len(storage_objects),
        )

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
