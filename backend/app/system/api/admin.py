from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions, resolve_permissions
from app.auth.repositories.users import UsersRepository
from app.auth.roles import is_admin_role, is_platform_admin_email
from app.auth.schemas.admin import (
    AdminDocumentSummaryListResponse,
    AdminDocumentTenantSummaryResponse,
    AdminTenantListResponse,
    AdminTenantSummaryResponse,
    AdminUserActionResponse,
    AdminUserDeleteRequest,
    AdminUserDeleteResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
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
    StorageCleanupJobResponse,
    StorageCleanupListResponse,
    StorageCleanupRetryResponse,
)
from app.auth.services.admin_user_service import (
    AdminTenantSummary,
    AdminUserService,
    AdminUserSummary,
)
from app.auth.tenancy import TenantContext, get_tenant_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.documents.models.data_deletion import DataDeletion
from app.documents.repositories.documents import DocumentsRepository
from app.documents.services.deletion_service import DeletionService
from app.ingestion.models.ingestion_job import IngestionJob
from app.platform.database.session import get_db, set_db_tenant_context
from app.system.models.break_glass_grant import BreakGlassGrant
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.audit_service import AuditService
from app.system.workers.tasks_maintenance import process_data_deletion

logger = logging.getLogger(__name__)

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


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
        last_login_at=summary.last_login_at,
    )


def _to_admin_tenant_response(
    summary: AdminTenantSummary,
) -> AdminTenantSummaryResponse:
    return AdminTenantSummaryResponse(
        tenant_id=summary.tenant_id,
        name=summary.name,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        status=summary.status,
        seats_used=summary.seats_used,
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
    if settings.platform_admin_mfa_required:
        if not user.totp_enabled:
            raise ApiError(
                code="ADMIN_MFA_SETUP_REQUIRED",
                message="Set up an authenticator app in account security before using platform administration.",
                status_code=403,
            )
        if auth.auth_type != "jwt" or auth.session_id is None or auth.mfa_verified_at is None:
            raise ApiError(
                code="ADMIN_MFA_REQUIRED",
                message="Sign in again and complete the authenticator challenge to use platform administration.",
                status_code=403,
            )


def _require_recent_mfa_authentication(auth: AuthContext, settings: Settings) -> None:
    """Require a recently completed, session-bound MFA sign-in for destructive actions."""
    if not settings.platform_admin_mfa_required:
        return
    authenticated_at = auth.session_created_at
    mfa_verified_at = auth.mfa_verified_at
    if authenticated_at is None or mfa_verified_at is None or auth.session_id is None:
        raise ApiError(
            code="RECENT_MFA_AUTH_REQUIRED",
            message="Sign in again with your authenticator app before requesting or approving deletion.",
            status_code=403,
        )

    now = datetime.now(tz=UTC)
    if authenticated_at.tzinfo is None:
        authenticated_at = authenticated_at.replace(tzinfo=UTC)
    if mfa_verified_at.tzinfo is None:
        mfa_verified_at = mfa_verified_at.replace(tzinfo=UTC)
    deadline = now - timedelta(minutes=settings.platform_admin_reauth_window_minutes)
    if authenticated_at < deadline or mfa_verified_at < deadline:
        raise ApiError(
            code="RECENT_MFA_AUTH_REQUIRED",
            message="Your administrator sign-in is no longer recent. Sign in again with your authenticator app before requesting or approving deletion.",
            status_code=403,
        )


def _resolve_deletion_tenant_id(
    *,
    target_tenant_id: uuid.UUID | None,
    tenant_context: TenantContext,
    auth: AuthContext,
    db: Session,
    settings: Settings,
) -> uuid.UUID:
    effective_tenant_id = target_tenant_id or tenant_context.tenant_id
    if effective_tenant_id != tenant_context.tenant_id:
        _require_platform_admin(auth, db=db, settings=settings)
    return effective_tenant_id


def _can_approve_deletion(row: DataDeletion, auth: AuthContext) -> bool:
    return bool(
        row.status == "awaiting_approval"
        and row.requested_by_user_id != auth.user_id
        and "admin:data_deletions:approve"
        in resolve_permissions(roles=auth.roles, direct_permissions=auth.permissions)
    )


def _can_self_approve_deletion(row: DataDeletion, auth: AuthContext) -> bool:
    not_before = row.self_approval_not_before
    if not_before is None:
        return False
    if not_before.tzinfo is None:
        not_before = not_before.replace(tzinfo=UTC)
    return bool(
        row.status == "awaiting_approval"
        and row.requested_by_user_id == auth.user_id
        and datetime.now(tz=UTC) >= not_before
        and "admin:data_deletions:approve"
        in resolve_permissions(roles=auth.roles, direct_permissions=auth.permissions)
    )


def _can_cancel_deletion(row: DataDeletion, auth: AuthContext) -> bool:
    return bool(
        row.status == "awaiting_approval"
        and row.requested_by_user_id == auth.user_id
        and "admin:data_deletions:write"
        in resolve_permissions(roles=auth.roles, direct_permissions=auth.permissions)
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
    tenant_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    account_user_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    security_only: bool = Query(default=False),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    service = AuditService(db)

    page = service.list_global_events(
        limit=limit,
        cursor=cursor,
        action=action,
        tenant_id=tenant_id,
        account_user_id=account_user_id,
        security_only=security_only,
    )

    service.write_admin_read_event(
        tenant_id=tenant_context.tenant_id,
        actor_user_id=tenant_context.user_id,
        action="admin.audit_logs.read",
        resource_type="admin_audit_logs",
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
                details={
                    key: str(value)
                    for key, value in (item.details or {}).items()
                    if key
                    in {
                        "auth_method",
                        "email_verified",
                        "failure_reason",
                        "mfa_verified",
                        "provider",
                        "registration_method",
                        "second_factor",
                        "storage_cleanup_jobs_pending",
                        "target_tenant_removed",
                        "target_user_id",
                        "verification_method",
                    }
                },
            )
            for item in page.items
        ],
        page=CursorPage(next_cursor=page.next_cursor, has_more=page.has_more),
    )


@router.get(
    "/storage-cleanup",
    response_model=StorageCleanupListResponse,
    dependencies=[Depends(require_permissions("admin:users:read"))],
)
def list_storage_cleanup(
    limit: int = Query(default=200, ge=1, le=500),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> StorageCleanupListResponse:
    set_db_tenant_context(db, "bypass")
    jobs = (
        db.query(StorageCleanupJob)
        .filter(StorageCleanupJob.status.in_(("pending", "failed")))
        .order_by(StorageCleanupJob.created_at.desc())
        .limit(limit)
        .all()
    )
    AuditService(db).write_admin_read_event(
        tenant_id=tenant_context.tenant_id,
        actor_user_id=tenant_context.user_id,
        action="admin.storage_cleanup.list.read",
        resource_type="storage_cleanup_jobs",
    )
    return StorageCleanupListResponse(
        items=[
            StorageCleanupJobResponse(
                id=job.id,
                tenant_id=job.tenant_id,
                status=job.status,
                attempts=job.attempts,
                next_attempt_at=job.next_attempt_at,
                created_at=job.created_at,
            )
            for job in jobs
        ]
    )


@router.post(
    "/storage-cleanup/{job_id}/retry",
    response_model=StorageCleanupRetryResponse,
    dependencies=[Depends(require_permissions("admin:users:delete"))],
)
def retry_storage_cleanup(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageCleanupRetryResponse:
    set_db_tenant_context(db, "bypass")
    job = (
        db.query(StorageCleanupJob).filter(StorageCleanupJob.id == job_id).with_for_update().first()
    )
    if job is None:
        raise ApiError(
            code="STORAGE_CLEANUP_NOT_FOUND", message="Cleanup job not found.", status_code=404
        )
    if job.status != "failed":
        raise ApiError(
            code="STORAGE_CLEANUP_NOT_RETRYABLE",
            message="Only failed cleanup jobs can be manually retried.",
            status_code=409,
        )
    job.status = "pending"
    job.attempts = 0
    job.last_error = None
    job.next_attempt_at = datetime.now(tz=UTC)
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        action="admin.storage_cleanup.retry",
        resource_type="storage_cleanup_job",
        resource_id=str(job.id),
        actor_user_id=auth.user_id,
        details={"target_tenant_id": job.tenant_id},
    )
    db.commit()
    return StorageCleanupRetryResponse(job_id=job.id, status=job.status)


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
        # Keep the requesting administrator's tenant first while retaining the
        # complete global view. This makes the response stable when other
        # tenants are being created concurrently by parallel workers.
        all_tenant_ids = [tenant.tenant_id for tenant in service.list_tenants_global()]
        tenant_ids = [auth.tenant_id] + [
            tenant_id for tenant_id in all_tenant_ids if tenant_id != auth.tenant_id
        ]
    elif _has_admin_access(auth) and target_tenant_id is not None:
        tenant_ids = [target_tenant_id]
    else:
        tenant_ids = [tenant_context.tenant_id]
    items: list[AdminDocumentTenantSummaryResponse] = []
    for tenant_id in tenant_ids:
        items.append(
            AdminDocumentTenantSummaryResponse(
                tenant_id=tenant_id,
                quarantined_count=document_repo.count_quarantined_by_tenant(tenant_id=tenant_id),
                error_count=document_repo.count_error_by_tenant(tenant_id=tenant_id),
            )
        )

    AuditService(db).write_admin_read_event(
        tenant_id=tenant_context.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.documents.summary.read",
        resource_type="document_processing_health",
        resource_id=str(target_tenant_id) if target_tenant_id else "all_workspaces",
    )
    return AdminDocumentSummaryListResponse(items=items)


@router.get(
    "/documents/recovery-history",
    dependencies=[Depends(require_permissions("admin:users:read"))],
)
def list_document_recovery_history(
    limit: int = Query(default=100, ge=1, le=500),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    jobs = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.tenant_id == tenant_context.tenant_id,
            (IngestionJob.resume_count > 0) | (IngestionJob.checkpoint_updated_at.is_not(None)),
        )
        .order_by(IngestionJob.updated_at.desc())
        .limit(limit)
        .all()
    )
    AuditService(db).write_admin_read_event(
        tenant_id=tenant_context.tenant_id,
        actor_user_id=tenant_context.user_id,
        action="admin.documents.recovery_history.read",
        resource_type="document_recovery_history",
    )
    return {
        "items": [
            {
                "job_id": job.id,
                "status": job.status,
                "checkpoint_stage": job.checkpoint_stage,
                "checkpoint_updated_at": job.checkpoint_updated_at,
                "resume_count": job.resume_count,
                "last_error_code": job.last_error_code,
                "updated_at": job.updated_at,
            }
            for job in jobs
        ]
    }


@router.post(
    "/break-glass",
    response_model=BreakGlassGrantResponse,
    dependencies=[Depends(require_permissions("admin:break_glass:write"))],
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
    dependencies=[Depends(require_permissions("admin:break_glass:write"))],
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
        update(BreakGlassGrant).where(BreakGlassGrant.id == grant_id).values(status="revoked")
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
    _require_recent_mfa_authentication(auth, settings)
    service = DeletionService(db, settings)
    target_tenant_id = _resolve_deletion_tenant_id(
        target_tenant_id=payload.target_tenant_id,
        tenant_context=tenant_context,
        auth=auth,
        db=db,
        settings=settings,
    )
    expected_confirmation = f"DELETE {target_tenant_id}"
    if payload.target_confirmation.strip() != expected_confirmation:
        raise ApiError(
            code="INVALID_REQUEST",
            message="Type DELETE followed by the exact workspace ID to confirm this request.",
            status_code=400,
        )

    result = service.request_deletion(
        tenant_id=target_tenant_id,
        requested_by_user_id=auth.user_id,
        reason=payload.reason,
    )

    return DataDeletionRequestResponse(
        deletion_id=result.deletion_id,
        status=result.status,
        self_approval_not_before=result.self_approval_not_before,
    )


@router.post(
    "/data-deletions/{deletion_id}/approve",
    response_model=DataDeletionRequestResponse,
    dependencies=[Depends(require_permissions("admin:data_deletions:approve"))],
)
def approve_data_deletion(
    deletion_id: uuid.UUID,
    target_tenant_id: uuid.UUID | None = None,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataDeletionRequestResponse:
    _require_recent_mfa_authentication(auth, settings)
    target_tenant_id = _resolve_deletion_tenant_id(
        target_tenant_id=target_tenant_id,
        tenant_context=tenant_context,
        auth=auth,
        db=db,
        settings=settings,
    )
    service = DeletionService(db, settings)
    result = service.approve_deletion(
        tenant_id=target_tenant_id,
        deletion_id=deletion_id,
        approved_by_user_id=auth.user_id,
    )

    try:
        process_data_deletion.delay(str(result.deletion_id), str(target_tenant_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Failed to enqueue approved data deletion task.",
            extra={
                "tenant_id": str(target_tenant_id),
                "user_id": str(auth.user_id),
                "deletion_id": str(result.deletion_id),
            },
        )
        service.mark_enqueue_failed(
            tenant_id=target_tenant_id,
            deletion_id=result.deletion_id,
            actor_user_id=auth.user_id,
        )
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="The approved deletion could not be queued. It is marked failed; create a new request when the service is available.",
            status_code=503,
        ) from exc

    return DataDeletionRequestResponse(deletion_id=result.deletion_id, status=result.status)


@router.post(
    "/data-deletions/{deletion_id}/self-approve",
    response_model=DataDeletionRequestResponse,
    dependencies=[Depends(require_permissions("admin:data_deletions:approve"))],
)
def self_approve_data_deletion(
    deletion_id: uuid.UUID,
    target_tenant_id: uuid.UUID | None = None,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataDeletionRequestResponse:
    _require_recent_mfa_authentication(auth, settings)
    target_tenant_id = _resolve_deletion_tenant_id(
        target_tenant_id=target_tenant_id,
        tenant_context=tenant_context,
        auth=auth,
        db=db,
        settings=settings,
    )
    service = DeletionService(db, settings)
    result = service.self_approve_deletion(
        tenant_id=target_tenant_id,
        deletion_id=deletion_id,
        approved_by_user_id=auth.user_id,
    )
    try:
        process_data_deletion.delay(str(result.deletion_id), str(target_tenant_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Failed to enqueue self-approved data deletion task.",
            extra={
                "tenant_id": str(target_tenant_id),
                "user_id": str(auth.user_id),
                "deletion_id": str(result.deletion_id),
            },
        )
        service.mark_enqueue_failed(
            tenant_id=target_tenant_id,
            deletion_id=result.deletion_id,
            actor_user_id=auth.user_id,
        )
        raise ApiError(
            code="INTERNAL_SERVER_ERROR",
            message="The approved deletion could not be queued. It is marked failed; create a new request when the service is available.",
            status_code=503,
        ) from exc
    return DataDeletionRequestResponse(deletion_id=result.deletion_id, status=result.status)


@router.post(
    "/data-deletions/{deletion_id}/cancel",
    response_model=DataDeletionRequestResponse,
    dependencies=[Depends(require_permissions("admin:data_deletions:write"))],
)
def cancel_data_deletion(
    deletion_id: uuid.UUID,
    target_tenant_id: uuid.UUID | None = None,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataDeletionRequestResponse:
    _require_recent_mfa_authentication(auth, settings)
    target_tenant_id = _resolve_deletion_tenant_id(
        target_tenant_id=target_tenant_id,
        tenant_context=tenant_context,
        auth=auth,
        db=db,
        settings=settings,
    )
    result = DeletionService(db, settings).cancel_deletion(
        tenant_id=target_tenant_id,
        deletion_id=deletion_id,
        actor_user_id=auth.user_id,
    )
    return DataDeletionRequestResponse(deletion_id=result.deletion_id, status=result.status)


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
    effective_tenant_id = _resolve_deletion_tenant_id(
        target_tenant_id=target_tenant_id,
        tenant_context=tenant_context,
        auth=auth,
        db=db,
        settings=settings,
    )
    rows = service.list_statuses(tenant_id=effective_tenant_id, limit=limit)
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.data_deletions.list.read",
        resource_type="data_deletion_requests",
        resource_id=str(effective_tenant_id),
    )
    return DataDeletionListResponse(
        items=[
            DataDeletionStatusResponse(
                deletion_id=row.id,
                tenant_id=row.tenant_id,
                status=row.status,
                scope=row.scope,
                reason=row.reason,
                can_approve=_can_approve_deletion(row, auth),
                can_self_approve=_can_self_approve_deletion(row, auth),
                can_cancel=_can_cancel_deletion(row, auth),
                self_approval_not_before=row.self_approval_not_before,
                error_code=row.error_code,
                error_message=(
                    "Deletion could not be completed. Contact support with the request ID."
                    if row.status == "failed"
                    else None
                ),
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
    effective_tenant_id = _resolve_deletion_tenant_id(
        target_tenant_id=target_tenant_id,
        tenant_context=tenant_context,
        auth=auth,
        db=db,
        settings=settings,
    )
    row = service.get_status(
        tenant_id=effective_tenant_id,
        deletion_id=deletion_id,
    )
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.data_deletion.read",
        resource_type="data_deletion_request",
        resource_id=str(deletion_id),
    )

    return DataDeletionStatusResponse(
        deletion_id=row.id,
        tenant_id=row.tenant_id,
        status=row.status,
        scope=row.scope,
        reason=row.reason,
        can_approve=_can_approve_deletion(row, auth),
        can_self_approve=_can_self_approve_deletion(row, auth),
        can_cancel=_can_cancel_deletion(row, auth),
        self_approval_not_before=row.self_approval_not_before,
        error_code=row.error_code,
        error_message=(
            "Deletion could not be completed. Contact support with the request ID."
            if row.status == "failed"
            else None
        ),
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
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.users.list.read",
        resource_type="admin_users",
    )
    return AdminUserListResponse(items=[_to_admin_user_response(item) for item in items])


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
    else:
        summary = service.get_user(tenant_id=tenant_context.tenant_id, user_id=user_id)
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.user.read",
        resource_type="user",
        resource_id=str(user_id),
    )
    return AdminUserDetailResponse(
        user=_to_admin_user_response(summary),
    )


@router.post(
    "/users/{user_id}/disable",
    response_model=AdminUserActionResponse,
    dependencies=[Depends(require_permissions("admin:users:disable"))],
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
    dependencies=[Depends(require_permissions("admin:users:reactivate"))],
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
    dependencies=[Depends(require_permissions("admin:users:logout"))],
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
    dependencies=[Depends(require_permissions("admin:users:delete"))],
)
def delete_admin_user(
    user_id: uuid.UUID,
    payload: AdminUserDeleteRequest,
    tenant_context: TenantContext = Depends(get_tenant_context),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminUserDeleteResponse:
    _require_recent_mfa_authentication(auth, settings)
    service = AdminUserService(db, settings)
    target_user = service.get_user_global(user_id=user_id)
    if payload.confirmation.strip() != f"DELETE {target_user.email}":
        raise ApiError(
            code="INVALID_REQUEST",
            message="Type DELETE followed by the account email exactly to confirm erasure.",
            status_code=400,
        )
    target_tenant_id = (
        target_user.tenant_id if _has_admin_access(auth) else tenant_context.tenant_id
    )
    result = service.delete_user(
        tenant_id=target_tenant_id,
        target_user_id=user_id,
        actor=auth,
    )
    return AdminUserDeleteResponse(
        success=True,
        deleted_user_id=result.deleted_user_id,
        pending_storage_cleanup_count=result.pending_storage_cleanup_count,
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
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.workspaces.list.read",
        resource_type="workspaces",
    )
    return AdminTenantListResponse(items=[_to_admin_tenant_response(item) for item in items])
