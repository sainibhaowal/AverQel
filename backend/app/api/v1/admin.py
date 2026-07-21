from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.auth.roles import is_admin_role, is_platform_admin_email
from app.auth.tenancy import TenantContext, get_tenant_context
from app.db.session import get_db
from app.models.system.break_glass_grant import BreakGlassGrant
from app.auth.repositories.users import UsersRepository
from app.documents.repositories.documents import DocumentsRepository
from app.auth.schemas.admin import (
    AdminDocumentStatusCountResponse,
    AdminDocumentSummaryListResponse,
    AdminDocumentTenantSummaryResponse,
    AdminTenantListResponse,
    AdminTenantStatsResponse,
    AdminTenantSummaryResponse,
    AdminUserActionResponse,
    AdminUserDeleteResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserStatsResponse,
    AdminUserSummaryResponse,
    AuditLogItem,
    AuditLogListResponse,
    BreakGlassGrantRequest,
    BreakGlassGrantResponse,
    BreakGlassRevokeResponse,
    CursorPage,
    DataDeletionListResponse,
    DataDeletionRequest,
    DataDeletionRequestResponse,
    DataDeletionStatusResponse,
)
from app.auth.services.admin_user_service import (
    AdminTenantSummary,
    AdminUserService,
    AdminUserSummary,
)
from app.documents.services.deletion_service import DeletionService
from app.services.system.audit_service import AuditService
from app.worker.tasks_maintenance import process_data_deletion

logger = logging.getLogger(__name__)

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _safe_details_map(details: Any) -> dict[str, str]:
    if not isinstance(details, dict):
        return {}
    return {str(k): str(v) for k, v in details.items()}


def _to_admin_user_response(summary: AdminUserSummary) -> AdminUserSummaryResponse:
    return AdminUserSummaryResponse(
        user_id=summary.user_id,
        tenant_id=summary.tenant_id,
        tenant_name=summary.tenant_name,
        email=summary.email,
        is_active=summary.is_active,
        totp_enabled=summary.totp_enabled,
        roles=summary.roles,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        last_login_at=summary.last_login_at,
        stats=AdminUserStatsResponse(
            documents_count=summary.stats.documents_count,
            queries_count=summary.stats.queries_count,
            conversations_count=summary.stats.conversations_count,
            comments_count=summary.stats.comments_count,
            pinned_findings_count=summary.stats.pinned_findings_count,
            providers_count=summary.stats.providers_count,
            storage_bytes=summary.stats.storage_bytes,
        ),
    )


def _to_admin_tenant_response(
    summary: AdminTenantSummary,
) -> AdminTenantSummaryResponse:
    return AdminTenantSummaryResponse(
        tenant_id=summary.tenant_id,
        name=summary.name,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        stats=AdminTenantStatsResponse(
            users_count=summary.stats.users_count,
            active_users_count=summary.stats.active_users_count,
            documents_count=summary.stats.documents_count,
            queries_count=summary.stats.queries_count,
            collections_count=summary.stats.collections_count,
        ),
    )


def _has_admin_access(auth: AuthContext) -> bool:
    return is_admin_role(auth.roles)


def _require_platform_admin(
    auth: AuthContext,
    *,
    db: Session,
    settings: Settings,
) -> None:
    if not _has_admin_access(auth):
        raise ApiError(
            code="FORBIDDEN",
            message="Only platform admins can perform this operation.",
            status_code=403,
        )
    user = UsersRepository(db).get_by_id(auth.tenant_id, auth.user_id)
    if user is None or not is_platform_admin_email(
        user.email,
        settings.bootstrap_super_admin_emails,
    ):
        raise ApiError(
            code="FORBIDDEN",
            message="Only platform admins can perform this operation.",
            status_code=403,
        )


def require_platform_admin_access(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    _require_platform_admin(auth, db=db, settings=settings)
    return auth


def _require_break_glass_enabled(settings: Settings) -> None:
    if not settings.admin_break_glass_enabled:
        raise ApiError(
            code="FORBIDDEN",
            message="Break-glass access is disabled for this deployment.",
            status_code=403,
        )


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_platform_admin_access)],
)


@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    dependencies=[Depends(require_permissions("admin:audit_logs:read"))],
)
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    service = AuditService(db)

    page = service.list_events(
        tenant_id=tenant_context.tenant_id,
        limit=limit,
        cursor=cursor,
        action=action,
    )

    try:
        service.write_event(
            tenant_id=tenant_context.tenant_id,
            action="admin.audit_logs.read",
            resource_type="admin",
            actor_user_id=tenant_context.user_id,
            details={"limit": str(limit), "action": str(action) if action else ""},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning(
            "Failed to write admin audit-log read event.",
            extra={
                "tenant_id": str(tenant_context.tenant_id),
                "user_id": str(tenant_context.user_id),
            },
            exc_info=True,
        )

    return AuditLogListResponse(
        items=[
            AuditLogItem(
                id=item.id,
                tenant_id=item.tenant_id,
                actor_user_id=item.actor_user_id,
                action=item.action,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                status=item.status,
                trace_id=item.trace_id,
                created_at=item.created_at,
                details=_safe_details_map(item.details),
            )
            for item in page.items
        ],
        page=CursorPage(next_cursor=page.next_cursor, has_more=page.has_more),
    )


@router.get(
    "/documents/summary",
    response_model=AdminDocumentSummaryListResponse,
    dependencies=[Depends(require_permissions("admin:users:read"))],
)
def list_admin_document_summary(
    target_tenant_id: Annotated[uuid.UUID | None, Query()] = None,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminDocumentSummaryListResponse:
    service = AdminUserService(db, settings)
    document_repo = DocumentsRepository(db)
    if _has_admin_access(auth) and target_tenant_id is None:
        tenant_ids = [tenant.tenant_id for tenant in service.list_tenants_global()]
    elif _has_admin_access(auth) and target_tenant_id is not None:
        tenant_ids = [target_tenant_id]
    else:
        tenant_ids = [tenant_context.tenant_id]
    items: list[AdminDocumentTenantSummaryResponse] = []
    for tenant_id in tenant_ids:
        status_counts = document_repo.status_counts_by_tenant(tenant_id=tenant_id)
        items.append(
            AdminDocumentTenantSummaryResponse(
                tenant_id=tenant_id,
                documents_count=document_repo.count_by_tenant(tenant_id=tenant_id),
                storage_bytes=document_repo.sum_storage_by_tenant(tenant_id=tenant_id),
                quarantined_count=document_repo.count_quarantined_by_tenant(
                    tenant_id=tenant_id
                ),
                status_counts=[
                    AdminDocumentStatusCountResponse(status=status, count=count)
                    for status, count in status_counts.items()
                ],
                error_count=document_repo.count_error_by_tenant(tenant_id=tenant_id),
            )
        )

    AuditService(db).write_event(
        tenant_id=tenant_context.tenant_id,
        action="admin.documents.summary.read",
        resource_type="admin_documents",
        actor_user_id=auth.user_id,
        details={"target_tenant_id": str(target_tenant_id or "")},
    )
    db.commit()
    return AdminDocumentSummaryListResponse(items=items)


@router.post(
    "/break-glass",
    response_model=BreakGlassGrantResponse,
    dependencies=[Depends(require_permissions("admin:users:write"))],
)
def create_break_glass_grant(
    payload: BreakGlassGrantRequest,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> BreakGlassGrantResponse:
    _require_break_glass_enabled(settings)
    expires_at = datetime.now(tz=UTC) + timedelta(minutes=payload.duration_minutes)
    grant = BreakGlassGrant(
        tenant_id=payload.target_tenant_id,
        actor_user_id=auth.user_id,
        target_user_id=payload.target_user_id,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        reason=payload.reason,
        status="active",
        expires_at=expires_at,
    )
    db.add(grant)
    db.flush()
    AuditService(db).write_event(
        tenant_id=payload.target_tenant_id,
        action="admin.break_glass.grant",
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        actor_user_id=auth.user_id,
        details={
            "target_user_id": str(payload.target_user_id),
            "reason": payload.reason,
            "duration_minutes": str(payload.duration_minutes),
            "grant_id": str(grant.id),
        },
    )
    db.commit()
    return BreakGlassGrantResponse(
        grant_id=grant.id,
        tenant_id=grant.tenant_id,
        actor_user_id=grant.actor_user_id,
        target_user_id=grant.target_user_id,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        status=grant.status,
        expires_at=grant.expires_at,
    )


@router.post(
    "/break-glass/{grant_id}/revoke",
    response_model=BreakGlassRevokeResponse,
    dependencies=[Depends(require_permissions("admin:users:write"))],
)
def revoke_break_glass_grant(
    grant_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> BreakGlassRevokeResponse:
    _require_break_glass_enabled(settings)
    grant = db.get(BreakGlassGrant, grant_id)
    if grant is None:
        raise ApiError(
            code="BREAK_GLASS_GRANT_NOT_FOUND",
            message="Break-glass grant not found.",
            status_code=404,
        )
    db.execute(
        update(BreakGlassGrant)
        .where(BreakGlassGrant.id == grant_id)
        .values(status="revoked")
    )
    AuditService(db).write_event(
        tenant_id=grant.tenant_id,
        action="admin.break_glass.revoke",
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        actor_user_id=auth.user_id,
        details={
            "grant_id": str(grant_id),
            "target_user_id": str(grant.target_user_id),
        },
    )
    db.commit()
    return BreakGlassRevokeResponse(grant_id=grant_id)


@router.post(
    "/data-deletions",
    response_model=DataDeletionRequestResponse,
    dependencies=[Depends(require_permissions("admin:data_deletions:write"))],
)
def request_data_deletion(
    payload: DataDeletionRequest,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataDeletionRequestResponse:
    service = DeletionService(db, settings)
    target_tenant_id = (
        payload.target_tenant_id
        if _has_admin_access(auth) and payload.target_tenant_id
        else tenant_context.tenant_id
    )

    result = service.request_deletion(
        tenant_id=target_tenant_id,
        requested_by_user_id=auth.user_id,
        reason=payload.reason,
    )

    try:
        process_data_deletion.delay(str(result.deletion_id), str(target_tenant_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Failed to enqueue data deletion task.",
            extra={
                "tenant_id": str(tenant_context.tenant_id),
                "user_id": str(auth.user_id),
                "deletion_id": str(result.deletion_id),
            },
        )
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="Failed to schedule data deletion job.",
            status_code=500,
        ) from exc

    return DataDeletionRequestResponse(
        deletion_id=result.deletion_id,
        status=result.status,
    )


@router.get(
    "/data-deletions",
    response_model=DataDeletionListResponse,
    dependencies=[Depends(require_permissions("admin:data_deletions:read"))],
)
def list_data_deletions(
    limit: int = Query(default=20, ge=1, le=100),
    target_tenant_id: uuid.UUID | None = None,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataDeletionListResponse:
    service = DeletionService(db, settings)
    effective_tenant_id = (
        target_tenant_id
        if _has_admin_access(auth) and target_tenant_id
        else tenant_context.tenant_id
    )
    rows = service.list_statuses(tenant_id=effective_tenant_id, limit=limit)
    return DataDeletionListResponse(
        items=[
            DataDeletionStatusResponse(
                deletion_id=row.id,
                tenant_id=row.tenant_id,
                requested_by_user_id=row.requested_by_user_id,
                status=row.status,
                scope=row.scope,
                reason=row.reason,
                result_counts={
                    str(k): int(v) for k, v in (row.result_counts or {}).items()
                },
                error_code=row.error_code,
                error_message=row.error_message,
                requested_at=row.requested_at,
                started_at=row.started_at,
                completed_at=row.completed_at,
                failed_at=row.failed_at,
            )
            for row in rows
        ]
    )


@router.get(
    "/data-deletions/{deletion_id}",
    response_model=DataDeletionStatusResponse,
    dependencies=[Depends(require_permissions("admin:data_deletions:read"))],
)
def get_data_deletion_status(
    deletion_id: uuid.UUID,
    target_tenant_id: uuid.UUID | None = None,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataDeletionStatusResponse:
    service = DeletionService(db, settings)
    effective_tenant_id = (
        target_tenant_id
        if _has_admin_access(auth) and target_tenant_id
        else tenant_context.tenant_id
    )
    row = service.get_status(
        tenant_id=effective_tenant_id,
        deletion_id=deletion_id,
    )

    return DataDeletionStatusResponse(
        deletion_id=row.id,
        tenant_id=row.tenant_id,
        requested_by_user_id=row.requested_by_user_id,
        status=row.status,
        scope=row.scope,
        reason=row.reason,
        result_counts={str(k): int(v) for k, v in (row.result_counts or {}).items()},
        error_code=row.error_code,
        error_message=row.error_message,
        requested_at=row.requested_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failed_at=row.failed_at,
    )


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    dependencies=[Depends(require_permissions("admin:users:read"))],
)
def list_admin_users(
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserListResponse:
    service = AdminUserService(db, settings)
    items = (
        service.list_users_global()
        if _has_admin_access(auth)
        else service.list_users(tenant_id=tenant_context.tenant_id)
    )
    return AdminUserListResponse(
        items=[_to_admin_user_response(item) for item in items]
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    dependencies=[Depends(require_permissions("admin:users:read"))],
)
def get_admin_user(
    user_id: uuid.UUID,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserDetailResponse:
    service = AdminUserService(db, settings)
    if _has_admin_access(auth):
        summary = service.get_user_global(user_id=user_id)
        activity = service.list_recent_activity_global(user_id=user_id, limit=20)
    else:
        summary = service.get_user(tenant_id=tenant_context.tenant_id, user_id=user_id)
        activity = service.list_recent_activity(
            tenant_id=tenant_context.tenant_id,
            user_id=user_id,
            limit=20,
        )
    return AdminUserDetailResponse(
        user=_to_admin_user_response(summary),
        recent_activity=[
            AuditLogItem(
                id=item.id,
                tenant_id=item.tenant_id,
                actor_user_id=item.actor_user_id,
                action=item.action,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                status=item.status,
                trace_id=item.trace_id,
                created_at=item.created_at,
                details=_safe_details_map(item.details),
            )
            for item in activity
        ],
    )


@router.post(
    "/users/{user_id}/disable",
    response_model=AdminUserActionResponse,
    dependencies=[Depends(require_permissions("admin:users:write"))],
)
def disable_admin_user(
    user_id: uuid.UUID,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserActionResponse:
    service = AdminUserService(db, settings)
    target_tenant_id = (
        service.get_user_global(user_id=user_id).tenant_id
        if _has_admin_access(auth)
        else tenant_context.tenant_id
    )
    service.disable_user(
        tenant_id=target_tenant_id,
        target_user_id=user_id,
        actor=auth,
    )
    return AdminUserActionResponse(success=True)


@router.post(
    "/users/{user_id}/reactivate",
    response_model=AdminUserActionResponse,
    dependencies=[Depends(require_permissions("admin:users:write"))],
)
def reactivate_admin_user(
    user_id: uuid.UUID,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserActionResponse:
    service = AdminUserService(db, settings)
    target_tenant_id = (
        service.get_user_global(user_id=user_id).tenant_id
        if _has_admin_access(auth)
        else tenant_context.tenant_id
    )
    service.reactivate_user(
        tenant_id=target_tenant_id,
        target_user_id=user_id,
        actor=auth,
    )
    return AdminUserActionResponse(success=True)


@router.post(
    "/users/{user_id}/force-logout",
    response_model=AdminUserActionResponse,
    dependencies=[Depends(require_permissions("admin:users:write"))],
)
def force_logout_admin_user(
    user_id: uuid.UUID,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserActionResponse:
    service = AdminUserService(db, settings)
    target_tenant_id = (
        service.get_user_global(user_id=user_id).tenant_id
        if _has_admin_access(auth)
        else tenant_context.tenant_id
    )
    service.force_logout_user(
        tenant_id=target_tenant_id,
        target_user_id=user_id,
        actor=auth,
    )
    return AdminUserActionResponse(success=True)


@router.delete(
    "/users/{user_id}",
    response_model=AdminUserDeleteResponse,
    dependencies=[Depends(require_permissions("admin:users:write"))],
)
def delete_admin_user(
    user_id: uuid.UUID,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserDeleteResponse:
    service = AdminUserService(db, settings)
    target_tenant_id = (
        service.get_user_global(user_id=user_id).tenant_id
        if _has_admin_access(auth)
        else tenant_context.tenant_id
    )
    result = service.delete_user(
        tenant_id=target_tenant_id,
        target_user_id=user_id,
        actor=auth,
    )
    return AdminUserDeleteResponse(
        success=True,
        deleted_user_id=result.deleted_user_id,
        deleted_email=result.deleted_email,
        deleted_counts=result.counts,
    )


@router.get(
    "/tenants",
    response_model=AdminTenantListResponse,
    dependencies=[Depends(require_permissions("admin:users:read"))],
)
def list_admin_tenants(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminTenantListResponse:
    if not _has_admin_access(auth):
        raise ApiError(
            code="FORBIDDEN",
            message="Only admins can list all workspaces.",
            status_code=403,
        )
    items = AdminUserService(db, settings).list_tenants_global()
    return AdminTenantListResponse(
        items=[_to_admin_tenant_response(item) for item in items]
    )
