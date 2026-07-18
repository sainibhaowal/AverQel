from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.roles import is_platform_admin_email
from app.db.session import set_db_tenant_context
from app.models.auth.refresh_token import RefreshToken
from app.models.auth.user import User
from app.models.documents.collection import DocumentCollection
from app.models.documents.document import Document
from app.models.providers.provider_config import ProviderConfig
from app.models.query.comment import Comment
from app.models.query.conversation import Conversation
from app.models.query.pinned_finding import PinnedFinding
from app.models.query.query import Query
from app.repositories.auth.refresh_tokens import RefreshTokensRepository
from app.repositories.auth.roles import RolesRepository
from app.repositories.auth.tenants import TenantsRepository
from app.repositories.auth.users import UsersRepository
from app.services.system.audit_service import AuditService
from app.services.system.storage_service import StorageService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AdminUserStats:
    documents_count: int
    queries_count: int
    conversations_count: int
    comments_count: int
    pinned_findings_count: int
    providers_count: int
    storage_bytes: int


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
    updated_at: datetime
    last_login_at: datetime | None
    stats: AdminUserStats


@dataclass(slots=True)
class AdminUserDeleteResult:
    deleted_user_id: uuid.UUID
    deleted_email: str
    counts: dict[str, int]


@dataclass(slots=True)
class AdminTenantStats:
    users_count: int
    active_users_count: int
    documents_count: int
    queries_count: int
    collections_count: int


@dataclass(slots=True)
class AdminTenantSummary:
    tenant_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    stats: AdminTenantStats


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
        user_ids = [user.id for user in users]
        role_map = {
            user.id: sorted(self.roles.get_role_names_for_user(tenant_id, user.id))
            for user in users
        }
        stats = self._stats_map(tenant_id=tenant_id, user_ids=user_ids)

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
                updated_at=user.updated_at,
                last_login_at=user.last_login_at,
                stats=stats[user.id],
            )
            for user in users
        ]

    def list_users_global(self) -> list[AdminUserSummary]:
        users = self.users.list_all()
        if not users:
            return []

        user_ids = [user.id for user in users]
        tenant_map = {tenant.id: tenant for tenant in self.tenants.list_all()}
        role_map = {
            user.id: sorted(self.roles.get_role_names_for_user_global(user_id=user.id))
            for user in users
        }
        stats = self._stats_map_global(user_ids=user_ids)

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
                    updated_at=user.updated_at,
                    last_login_at=user.last_login_at,
                    stats=stats[user.id],
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
        stats = self._stats_map(tenant_id=tenant_id, user_ids=[user.id])[user.id]
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
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
            stats=stats,
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
        stats = self._stats_map_global(user_ids=[user.id])[user.id]
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
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
            stats=stats,
        )

    def list_recent_activity(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int = 20
    ) -> list[Any]:
        return self.audit.repo.list_for_actor(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            limit=max(1, min(limit, 100)),
        )

    def list_recent_activity_global(
        self, *, user_id: uuid.UUID, limit: int = 20
    ) -> list[Any]:
        return self.audit.repo.list_for_actor_global(
            actor_user_id=user_id,
            limit=max(1, min(limit, 100)),
        )

    def list_tenants_global(self) -> list[AdminTenantSummary]:
        tenants = [
            tenant
            for tenant in self.tenants.list_all()
            if self.users.count_by_tenant(tenant.id) > 0
        ]
        if not tenants:
            return []
        tenant_ids = [tenant.id for tenant in tenants]
        stats = self._tenant_stats_map(tenant_ids=tenant_ids)
        return [
            AdminTenantSummary(
                tenant_id=tenant.id,
                name=tenant.name,
                created_at=tenant.created_at,
                updated_at=tenant.updated_at,
                stats=stats[tenant.id],
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
            details={"target_email": user.email},
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
            details={"target_email": user.email},
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
            details={"target_email": user.email},
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

        counts = asdict(
            self._stats_map(tenant_id=tenant_id, user_ids=[user.id])[user.id]
        )
        counts["refresh_tokens"] = self._count_for_query(
            select(func.count())
            .select_from(self.refresh_tokens_model)
            .where(
                self.refresh_tokens_model.tenant_id == tenant_id,
                self.refresh_tokens_model.user_id == user.id,
            )
        )

        objects = list(
            self.db.execute(
                select(Document.storage_bucket, Document.storage_object_key).where(
                    Document.tenant_id == tenant_id,
                    Document.uploaded_by_user_id == user.id,
                )
            ).all()
        )
        for bucket, object_key in objects:
            try:
                self.storage.delete_object(
                    bucket=str(bucket), object_key=str(object_key)
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to delete user-owned object from storage.",
                    extra={
                        "tenant_id": str(tenant_id),
                        "user_id": str(user.id),
                        "bucket": str(bucket),
                        "object_key": str(object_key),
                    },
                    exc_info=True,
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
            details={
                "target_email": user.email,
                **{k: str(v) for k, v in counts.items()},
            },
        )
        self.db.commit()

        return AdminUserDeleteResult(
            deleted_user_id=user.id,
            deleted_email=user.email,
            counts=counts,
        )

    @property
    def refresh_tokens_model(self) -> type[RefreshToken]:
        return RefreshToken

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
        return is_platform_admin_email(
            email, self.settings.bootstrap_super_admin_emails
        )

    def _count_for_query(self, statement: Any) -> int:
        return int(self.db.execute(statement).scalar_one() or 0)

    def _stats_map(
        self, *, tenant_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AdminUserStats]:
        def grouped(model: Any, field: Any) -> dict[uuid.UUID, int]:
            rows = self.db.execute(
                select(field, func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id, field.in_(user_ids))
                .group_by(field)
            ).all()
            return {row[0]: int(row[1]) for row in rows}

        documents = grouped(Document, Document.uploaded_by_user_id)
        queries = grouped(Query, Query.user_id)
        conversations = grouped(Conversation, Conversation.user_id)
        comments = grouped(Comment, Comment.user_id)
        pinned = grouped(PinnedFinding, PinnedFinding.user_id)
        providers_count = self._count_for_query(
            select(func.count())
            .select_from(ProviderConfig)
            .where(ProviderConfig.tenant_id == tenant_id)
        )

        storage_rows = self.db.execute(
            select(
                Document.uploaded_by_user_id,
                func.coalesce(func.sum(Document.size_bytes), 0),
            )
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.uploaded_by_user_id.in_(user_ids),
                Document.is_deleted.is_(False),
            )
            .group_by(Document.uploaded_by_user_id)
        ).all()
        storage = {row[0]: int(row[1] or 0) for row in storage_rows}

        return {
            user_id: AdminUserStats(
                documents_count=documents.get(user_id, 0),
                queries_count=queries.get(user_id, 0),
                conversations_count=conversations.get(user_id, 0),
                comments_count=comments.get(user_id, 0),
                pinned_findings_count=pinned.get(user_id, 0),
                providers_count=providers_count,
                storage_bytes=storage.get(user_id, 0),
            )
            for user_id in user_ids
        }

    def _stats_map_global(
        self, *, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AdminUserStats]:
        def grouped(model: Any, field: Any) -> dict[uuid.UUID, int]:
            set_db_tenant_context(self.db, "bypass")
            rows = self.db.execute(
                select(field, func.count())
                .select_from(model)
                .where(field.in_(user_ids))
                .group_by(field)
            ).all()
            return {row[0]: int(row[1]) for row in rows}

        documents = grouped(Document, Document.uploaded_by_user_id)
        queries = grouped(Query, Query.user_id)
        conversations = grouped(Conversation, Conversation.user_id)
        comments = grouped(Comment, Comment.user_id)
        pinned = grouped(PinnedFinding, PinnedFinding.user_id)
        provider_rows = self.db.execute(
            select(ProviderConfig.tenant_id, func.count())
            .select_from(ProviderConfig)
            .group_by(ProviderConfig.tenant_id)
        ).all()
        provider_counts_by_tenant = {row[0]: int(row[1]) for row in provider_rows}

        user_tenants = {
            user.id: user.tenant_id
            for user in self.db.execute(
                select(User).where(User.id.in_(user_ids))
            ).scalars()
        }
        storage_rows = self.db.execute(
            select(
                Document.uploaded_by_user_id,
                func.coalesce(func.sum(Document.size_bytes), 0),
            )
            .select_from(Document)
            .where(
                Document.uploaded_by_user_id.in_(user_ids),
                Document.is_deleted.is_(False),
            )
            .group_by(Document.uploaded_by_user_id)
        ).all()
        storage = {row[0]: int(row[1] or 0) for row in storage_rows}

        return {
            user_id: AdminUserStats(
                documents_count=documents.get(user_id, 0),
                queries_count=queries.get(user_id, 0),
                conversations_count=conversations.get(user_id, 0),
                comments_count=comments.get(user_id, 0),
                pinned_findings_count=pinned.get(user_id, 0),
                providers_count=provider_counts_by_tenant.get(
                    user_tenants.get(user_id), 0
                ),
                storage_bytes=storage.get(user_id, 0),
            )
            for user_id in user_ids
        }

    def _tenant_stats_map(
        self,
        *,
        tenant_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, AdminTenantStats]:
        def grouped(
            model: Any,
            field: Any,
            extra_where: tuple[Any, ...] = (),
        ) -> dict[uuid.UUID, int]:
            set_db_tenant_context(self.db, "bypass")
            rows = self.db.execute(
                select(field, func.count())
                .select_from(model)
                .where(field.in_(tenant_ids), *extra_where)
                .group_by(field)
            ).all()
            return {row[0]: int(row[1]) for row in rows}

        user_counts = grouped(self.users_model, self.users_model.tenant_id)
        active_user_counts = grouped(
            self.users_model,
            self.users_model.tenant_id,
            extra_where=(self.users_model.is_active.is_(True),),
        )
        document_counts = grouped(Document, Document.tenant_id)
        query_counts = grouped(Query, Query.tenant_id)
        collection_counts = grouped(DocumentCollection, DocumentCollection.tenant_id)

        return {
            tenant_id: AdminTenantStats(
                users_count=user_counts.get(tenant_id, 0),
                active_users_count=active_user_counts.get(tenant_id, 0),
                documents_count=document_counts.get(tenant_id, 0),
                queries_count=query_counts.get(tenant_id, 0),
                collections_count=collection_counts.get(tenant_id, 0),
            )
            for tenant_id in tenant_ids
        }

    @property
    def users_model(self) -> type[User]:
        return User
