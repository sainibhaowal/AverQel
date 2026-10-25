from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import case, desc, exists, func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.models.user import User
from app.auth.rbac import require_permissions
from app.auth.tenancy import TenantContext, get_tenant_context
from app.core.config import get_settings
from app.platform.database.session import get_db, set_db_tenant_context
from app.system.api.admin import require_platform_admin_access
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.models.support_encryption_key import SupportEncryptionKey
from app.system.models.support_ticket import SupportTicket
from app.system.models.support_ticket_attachment import SupportTicketAttachment
from app.system.models.support_ticket_message import SupportTicketMessage
from app.system.schemas.support import (
    AdminSupportListResponse,
    AdminSupportMessageCreate,
    AdminSupportQueueItem,
    AdminSupportQueueResponse,
    AdminSupportQueueUserProfile,
    SupportTicketAttachmentResponse,
    SupportTicketCreate,
    SupportTicketDetailResponse,
    SupportTicketMessageCreate,
    SupportTicketMessageResponse,
    SupportTicketResponse,
    SupportTicketUpdate,
    UserSupportSummary,
)
from app.system.schemas.support_encryption import (
    LegacySupportRecord,
    LegacySupportRecordPage,
    SupportRecordEncryptionMigration,
)
from app.system.services.audit_service import AuditService
from app.system.services.conversation_profiles import conversation_participants
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.storage_quota import StorageQuotaService
from app.system.services.storage_service import StorageService, StorageServiceError
from app.system.services.support_encryption import (
    EncryptedPayloadError,
    validate_attachment_metadata,
    validate_payload,
)
from app.system.services.user_notifications import add_user_notification, notify_platform_admins

router = APIRouter(prefix="/support", tags=["support"])
MAX_SUPPORT_ATTACHMENT_BYTES = 5 * 1024 * 1024
SUPPORT_ATTACHMENT_FILE = File(...)
QUEUE_LIMIT = Query(default=50, ge=1, le=100)
QUEUE_OFFSET = Query(default=0, ge=0, le=100_000)
QUEUE_SEARCH = Query(default=None, max_length=120)
QUEUE_ASSIGNEE = Query(default=None)
QUEUE_UNASSIGNED = Query(default=False)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"


def _attachment_response(row: SupportTicketAttachment) -> SupportTicketAttachmentResponse:
    return SupportTicketAttachmentResponse(
        id=row.id,
        ticket_id=row.ticket_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
        download_url=f"/api/v1/support/tickets/{row.ticket_id}/attachments/{row.id}",
        is_encrypted=row.is_encrypted,
        encrypted_metadata=row.encrypted_metadata,
    )


def _conversation_key_ids(
    db: Session, *, user_id: uuid.UUID, tenant_id_to_restore: uuid.UUID | None = None
) -> set[str]:
    set_db_tenant_context(db, "bypass")
    rows = (
        db.execute(
            select(SupportEncryptionKey).where(
                (SupportEncryptionKey.scope == "platform_admin")
                | (
                    (SupportEncryptionKey.scope == "user")
                    & (SupportEncryptionKey.user_id == user_id)
                )
            )
        )
        .scalars()
        .all()
    )
    admin_key = next((row for row in rows if row.scope == "platform_admin"), None)
    user_key = next((row for row in rows if row.scope == "user" and row.user_id == user_id), None)
    if tenant_id_to_restore is not None:
        set_db_tenant_context(db, tenant_id_to_restore)
    if admin_key is None or user_key is None:
        raise HTTPException(status_code=409, detail="Support encryption keys are not initialized")
    return {admin_key.key_id, user_key.key_id}


def _admin_key_id(db: Session, *, admin_user_id: uuid.UUID) -> str:
    set_db_tenant_context(db, "bypass")
    row = db.execute(
        select(SupportEncryptionKey).where(SupportEncryptionKey.scope == "platform_admin")
    ).scalar_one_or_none()
    if row is None or row.user_id != admin_user_id:
        raise HTTPException(status_code=409, detail="Admin support encryption key is unavailable")
    return row.key_id


def _validate_payload_or_422(payload: str, expected_key_ids: set[str]) -> None:
    try:
        validate_payload(payload, expected_key_ids)
    except EncryptedPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _ticket_for_user(
    db: Session, *, ticket_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> SupportTicket:
    ticket = db.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.tenant_id == tenant_id,
            SupportTicket.user_id == user_id,
        )
    ).scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def _ticket_messages(
    db: Session, *, ticket: SupportTicket, include_internal: bool
) -> list[SupportTicketMessage]:
    query = select(SupportTicketMessage).where(
        SupportTicketMessage.ticket_id == ticket.id,
        SupportTicketMessage.tenant_id == ticket.tenant_id,
    )
    if not include_internal:
        query = query.where(SupportTicketMessage.is_internal.is_(False))
    return list(
        db.execute(
            query.order_by(SupportTicketMessage.created_at, SupportTicketMessage.id)
        ).scalars()
    )


def _detail(
    db: Session,
    ticket: SupportTicket,
    *,
    include_internal: bool,
    user_email: str | None = None,
    tenant_id_to_restore: uuid.UUID | None = None,
) -> SupportTicketDetailResponse:
    message_rows = _ticket_messages(db, ticket=ticket, include_internal=include_internal)
    participants, author_refs = conversation_participants(
        db,
        message_rows,
        primary_author_ids=[ticket.user_id],
        include_display_names=include_internal,
        tenant_id_to_restore=tenant_id_to_restore,
    )
    attachment_rows = (
        db.execute(
            select(SupportTicketAttachment)
            .where(
                SupportTicketAttachment.ticket_id == ticket.id,
                SupportTicketAttachment.tenant_id == ticket.tenant_id,
            )
            .order_by(SupportTicketAttachment.created_at)
        )
        .scalars()
        .all()
    )
    attachments = []
    for row in attachment_rows:
        item = _attachment_response(row)
        if include_internal:
            item.download_url = f"/api/v1/support/admin/tickets/{ticket.id}/attachments/{row.id}"
        attachments.append(item)
    return SupportTicketDetailResponse(
        **SupportTicketResponse.model_validate(ticket).model_dump(),
        user_email=user_email,
        messages=[
            SupportTicketMessageResponse.model_validate(item).model_copy(
                update={
                    "author_ref": (
                        author_refs.get(item.author_user_id)
                        if item.author_user_id is not None
                        else None
                    )
                }
            )
            for item in message_rows
        ],
        participants=participants,
        attachments=attachments,
    )


@router.post("/tickets", response_model=SupportTicketResponse)
def create_ticket(
    payload: SupportTicketCreate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportTicketResponse:
    _validate_payload_or_422(
        payload.encrypted_payload,
        _conversation_key_ids(db, user_id=auth.user_id, tenant_id_to_restore=tenant.tenant_id),
    )
    RateLimitService(get_settings()).enforce_support_submission_limit(
        tenant_id=str(tenant.tenant_id), user_id=str(auth.user_id)
    )
    now = datetime.now(UTC)
    response_hours, resolution_hours = 8, 72
    ticket = SupportTicket(
        tenant_id=tenant.tenant_id,
        user_id=auth.user_id,
        subject="[Encrypted support request]",
        description="[Encrypted]",
        encrypted_payload=payload.encrypted_payload,
        category=payload.category,
        status="open",
        priority="normal",
        first_response_due_at=now + timedelta(hours=response_hours),
        resolution_due_at=now + timedelta(hours=resolution_hours),
    )
    db.add(ticket)
    db.flush()
    db.add(
        SupportTicketMessage(
            tenant_id=tenant.tenant_id,
            ticket_id=ticket.id,
            author_role="system",
            kind="acknowledgment",
            body="We received your request. Our support team will follow up in this conversation.",
        )
    )
    add_user_notification(
        db,
        tenant_id=tenant.tenant_id,
        recipient_user_id=auth.user_id,
        event_domain="support",
        event_type="ticket_received",
        title="Support request received",
        message="Your encrypted support request was received.",
        href=f"/dashboard/support?ticket={ticket.id}",
        resource_id=ticket.id,
        idempotency_key=f"support:received:{ticket.id}",
    )
    notify_platform_admins(
        db,
        event_domain="support",
        event_type="ticket_created",
        title="New support request",
        message="A user submitted a support request.",
        href=f"/dashboard/admin/support?ticket={ticket.id}",
        resource_id=ticket.id,
    )
    db.commit()
    return SupportTicketResponse.model_validate(ticket)


@router.get("/tickets", response_model=list[SupportTicketResponse])
def list_my_tickets(
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[SupportTicketResponse]:
    _no_store(response)
    tickets = (
        db.execute(
            select(SupportTicket)
            .where(
                SupportTicket.user_id == auth.user_id, SupportTicket.tenant_id == tenant.tenant_id
            )
            .order_by(desc(SupportTicket.updated_at), desc(SupportTicket.id))
            .limit(100)
        )
        .scalars()
        .all()
    )
    return [SupportTicketResponse.model_validate(ticket) for ticket in tickets]


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetailResponse)
def get_my_ticket(
    ticket_id: uuid.UUID,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportTicketDetailResponse:
    _no_store(response)
    ticket = _ticket_for_user(
        db, ticket_id=ticket_id, tenant_id=tenant.tenant_id, user_id=auth.user_id
    )
    return _detail(db, ticket, include_internal=False, tenant_id_to_restore=tenant.tenant_id)


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketDetailResponse)
def add_user_ticket_message(
    ticket_id: uuid.UUID,
    payload: SupportTicketMessageCreate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportTicketDetailResponse:
    ticket = _ticket_for_user(
        db, ticket_id=ticket_id, tenant_id=tenant.tenant_id, user_id=auth.user_id
    )
    _validate_payload_or_422(
        payload.encrypted_payload,
        _conversation_key_ids(db, user_id=auth.user_id, tenant_id_to_restore=tenant.tenant_id),
    )
    if ticket.status in {"resolved", "closed"}:
        old_status = ticket.status
        ticket.status = "open"
        db.add(
            SupportTicketMessage(
                tenant_id=tenant.tenant_id,
                ticket_id=ticket.id,
                author_user_id=auth.user_id,
                author_role="system",
                kind="status_changed",
                body=f"User reopened this request from {old_status.replace('_', ' ')}.",
            )
        )
    db.add(
        SupportTicketMessage(
            tenant_id=tenant.tenant_id,
            ticket_id=ticket.id,
            author_user_id=auth.user_id,
            author_role="user",
            body="[Encrypted message]",
            encrypted_payload=payload.encrypted_payload,
        )
    )
    ticket.updated_at = datetime.now(UTC)
    if ticket.status == "waiting_user":
        ticket.status = "in_progress"
    notify_platform_admins(
        db,
        event_domain="support",
        event_type="ticket_user_reply",
        title="User replied to a support request",
        message="A user added an encrypted reply to a support request.",
        href=f"/dashboard/admin/support?ticket={ticket.id}",
        resource_id=f"{ticket.id}:user-reply:{uuid.uuid4()}",
    )
    db.flush()
    detail = _detail(db, ticket, include_internal=False, tenant_id_to_restore=tenant.tenant_id)
    db.commit()
    return detail


@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=SupportTicketAttachmentResponse,
    status_code=201,
)
async def upload_ticket_attachment(
    ticket_id: uuid.UUID,
    file: UploadFile = SUPPORT_ATTACHMENT_FILE,
    encrypted_metadata: str = Form(..., max_length=12_000),
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportTicketAttachmentResponse:
    ticket = _ticket_for_user(
        db, ticket_id=ticket_id, tenant_id=tenant.tenant_id, user_id=auth.user_id
    )
    RateLimitService(get_settings()).enforce_support_submission_limit(
        tenant_id=str(tenant.tenant_id), user_id=str(auth.user_id)
    )
    payload = await file.read(MAX_SUPPORT_ATTACHMENT_BYTES + 17)
    if len(payload) > MAX_SUPPORT_ATTACHMENT_BYTES + 16:
        raise HTTPException(status_code=413, detail="Support attachments are limited to 5 MiB")
    if len(payload) < 16:
        raise HTTPException(status_code=422, detail="Encrypted attachment is incomplete")
    expected_key_ids = _conversation_key_ids(
        db, user_id=auth.user_id, tenant_id_to_restore=tenant.tenant_id
    )
    try:
        validate_attachment_metadata(encrypted_metadata, expected_key_ids)
    except EncryptedPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename, content_type = "Encrypted attachment.bin", "application/octet-stream"
    StorageQuotaService(db).ensure_capacity(
        tenant_id=tenant.tenant_id,
        roles=auth.roles,
        user_id=auth.user_id,
        additional_bytes=len(payload),
    )
    row = SupportTicketAttachment(
        tenant_id=tenant.tenant_id,
        ticket_id=ticket.id,
        uploaded_by_user_id=auth.user_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(payload),
        encrypted_metadata=encrypted_metadata,
        is_encrypted=True,
        storage_bucket=get_settings().minio_bucket,
        storage_key=f"{tenant.tenant_id}/pending/{uuid.uuid4()}",
    )
    db.add(row)
    db.flush()
    try:
        stored = StorageService(get_settings()).put_bytes(
            tenant_id=tenant.tenant_id,
            document_id=row.id,
            filename=f"support-{row.id}.bin",
            content_type=content_type,
            payload=payload,
        )
        row.storage_bucket = stored.bucket
        row.storage_key = stored.object_key
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            if "stored" in locals():
                StorageService(get_settings()).delete_tenant_object(
                    tenant_id=tenant.tenant_id, bucket=stored.bucket, object_key=stored.object_key
                )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Unable to store support attachment") from exc
    return _attachment_response(row)


def _read_ticket_attachment(
    db: Session, *, ticket_id: uuid.UUID, attachment_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[SupportTicketAttachment, bytes]:
    row = db.execute(
        select(SupportTicketAttachment).where(
            SupportTicketAttachment.id == attachment_id,
            SupportTicketAttachment.ticket_id == ticket_id,
            SupportTicketAttachment.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        data = StorageService(get_settings()).get_tenant_bytes(
            tenant_id=tenant_id, bucket=row.storage_bucket, object_key=row.storage_key
        )
    except StorageServiceError as exc:
        raise HTTPException(status_code=404, detail="Attachment payload is unavailable") from exc
    return row, data


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}")
def download_ticket_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Response:
    _ticket_for_user(db, ticket_id=ticket_id, tenant_id=tenant.tenant_id, user_id=auth.user_id)
    row, data = _read_ticket_attachment(
        db, ticket_id=ticket_id, attachment_id=attachment_id, tenant_id=tenant.tenant_id
    )
    from urllib.parse import quote

    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/admin/tickets/{ticket_id}/attachments/{attachment_id}",
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def download_ticket_attachment_admin(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> Response:
    set_db_tenant_context(db, "bypass")
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row, data = _read_ticket_attachment(
        db, ticket_id=ticket_id, attachment_id=attachment_id, tenant_id=ticket.tenant_id
    )
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.attachment.read",
        resource_type="support_attachment",
        resource_id=str(attachment_id),
    )
    from urllib.parse import quote

    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/admin/tickets",
    response_model=AdminSupportListResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def list_all_tickets_admin(
    response: Response,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AdminSupportListResponse:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    results = db.execute(
        select(SupportTicket, User.email)
        .join(User, User.id == SupportTicket.user_id)
        .order_by(desc(SupportTicket.updated_at), desc(SupportTicket.id))
    ).all()
    grouped: dict[uuid.UUID, list[tuple[SupportTicket, str]]] = {}
    for ticket, email in results:
        grouped.setdefault(ticket.user_id, []).append((ticket, email))
    items = [
        UserSupportSummary(
            user_id=user_id,
            email=tickets[0][1],
            ticket_count=len(tickets),
            last_ticket_at=tickets[0][0].updated_at,
            latest_tickets=[
                SupportTicketResponse.model_validate(ticket) for ticket, _ in tickets[:5]
            ],
        )
        for user_id, tickets in grouped.items()
    ]
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.history.list.read",
        resource_type="support_history",
    )
    return AdminSupportListResponse(items=items)


@router.get(
    "/admin/queue",
    response_model=AdminSupportQueueResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def list_support_queue_admin(
    response: Response,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    search: str | None = QUEUE_SEARCH,
    assigned_to: uuid.UUID | None = QUEUE_ASSIGNEE,
    unassigned_only: bool = QUEUE_UNASSIGNED,
    overdue_only: bool = Query(default=False),
    limit: int = QUEUE_LIMIT,
    offset: int = QUEUE_OFFSET,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AdminSupportQueueResponse:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    now = datetime.now(UTC)
    base = select(SupportTicket, User.email, User.display_name, User.avatar).join(
        User, User.id == SupportTicket.user_id
    )
    if status:
        base = base.where(SupportTicket.status == status)
    if priority:
        base = base.where(SupportTicket.priority == priority)
    if search:
        # Content is encrypted in the browser; only account metadata can be searched server-side.
        base = base.where(User.email.ilike(f"%{search.strip()}%"))
    if assigned_to:
        base = base.where(SupportTicket.assigned_admin_id == assigned_to)
    elif unassigned_only:
        base = base.where(SupportTicket.assigned_admin_id.is_(None))
    if overdue_only:
        base = base.where(
            SupportTicket.status.notin_(["resolved", "closed"]),
            or_(
                SupportTicket.resolution_due_at < now,
                (SupportTicket.first_response_at.is_(None))
                & (SupportTicket.first_response_due_at < now),
            ),
        )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    priority_rank = case(
        (SupportTicket.priority == "urgent", 0),
        (SupportTicket.priority == "high", 1),
        (SupportTicket.priority == "normal", 2),
        else_=3,
    )
    rows = db.execute(
        base.order_by(priority_rank, SupportTicket.updated_at.asc()).limit(limit).offset(offset)
    ).all()
    user_profiles: dict[uuid.UUID, AdminSupportQueueUserProfile] = {}
    for ticket, _, display_name, avatar in rows:
        user_profiles.setdefault(
            ticket.user_id,
            AdminSupportQueueUserProfile(
                user_id=ticket.user_id,
                display_name=display_name,
                avatar=avatar,
            ),
        )
    tickets = [
        AdminSupportQueueItem(
            **SupportTicketResponse.model_validate(ticket).model_dump(),
            user_email=email,
        )
        for ticket, email, display_name, avatar in rows
    ]
    open_count = (
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status.notin_(["resolved", "closed"]))
        )
        or 0
    )
    overdue_count = (
        db.scalar(
            select(func.count())
            .select_from(SupportTicket)
            .where(
                SupportTicket.status.notin_(["resolved", "closed"]),
                or_(
                    SupportTicket.resolution_due_at < now,
                    (SupportTicket.first_response_at.is_(None))
                    & (SupportTicket.first_response_due_at < now),
                ),
            )
        )
        or 0
    )
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.queue.read",
        resource_type="support_queue",
    )
    return AdminSupportQueueResponse(
        items=tickets,
        users=list(user_profiles.values()),
        total=int(total),
        open_count=int(open_count),
        overdue_count=int(overdue_count),
    )


@router.get(
    "/admin/encryption/legacy",
    response_model=LegacySupportRecordPage,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def list_legacy_support_records(
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> LegacySupportRecordPage:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    has_legacy_messages = exists(
        select(1).where(
            SupportTicketMessage.ticket_id == SupportTicket.id,
            SupportTicketMessage.encrypted_payload.is_(None),
            SupportTicketMessage.author_role != "system",
        )
    )
    has_legacy_attachments = exists(
        select(1).where(
            SupportTicketAttachment.ticket_id == SupportTicket.id,
            SupportTicketAttachment.is_encrypted.is_(False),
        )
    )
    legacy_filter = or_(
        SupportTicket.encrypted_payload.is_(None), has_legacy_messages, has_legacy_attachments
    )
    total = db.scalar(select(func.count()).select_from(SupportTicket).where(legacy_filter)) or 0
    user_key_initialized = exists(
        select(1).where(
            SupportEncryptionKey.user_id == SupportTicket.user_id,
            SupportEncryptionKey.tenant_id == SupportTicket.tenant_id,
            SupportEncryptionKey.scope == "user",
        )
    )
    rows = db.execute(
        select(
            SupportTicket.id,
            SupportTicket.user_id,
            user_key_initialized.label("user_key_initialized"),
        )
        .where(legacy_filter)
        .order_by(SupportTicket.created_at, SupportTicket.id)
        .limit(limit)
        .offset(offset)
    ).all()
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.encryption.legacy.list.read",
        resource_type="support_encryption_migration",
    )
    return LegacySupportRecordPage(
        items=[
            LegacySupportRecord(
                id=row.id,
                user_id=row.user_id,
                user_key_initialized=row.user_key_initialized,
            )
            for row in rows
        ],
        total=int(total),
    )


@router.get(
    "/admin/tickets/{ticket_id}",
    response_model=SupportTicketDetailResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def get_ticket_admin(
    ticket_id: uuid.UUID,
    response: Response,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportTicketDetailResponse:
    _no_store(response)
    set_db_tenant_context(db, "bypass")
    result = db.execute(
        select(SupportTicket, User.email)
        .join(User, User.id == SupportTicket.user_id)
        .where(SupportTicket.id == ticket_id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    detail = _detail(db, result[0], include_internal=True, user_email=result[1])
    AuditService(db).write_admin_read_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.ticket.read",
        resource_type="support_ticket",
        resource_id=str(ticket_id),
    )
    return detail


@router.put(
    "/admin/tickets/{ticket_id}/encryption",
    response_model=SupportTicketDetailResponse,
    dependencies=[Depends(require_permissions("admin:support:write"))],
)
def encrypt_legacy_support_record(
    ticket_id: uuid.UUID,
    payload: SupportRecordEncryptionMigration,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportTicketDetailResponse:
    set_db_tenant_context(db, "bypass")
    result = db.execute(
        select(SupportTicket, User.email)
        .join(User, User.id == SupportTicket.user_id)
        .where(SupportTicket.id == ticket_id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket, user_email = result
    if ticket.encrypted_payload is None:
        if payload.encrypted_payload is None:
            raise HTTPException(status_code=422, detail="Encrypted ticket content is required")
        conversation_key_ids = _conversation_key_ids(db, user_id=ticket.user_id)
        _validate_payload_or_422(payload.encrypted_payload, conversation_key_ids)
        ticket.encrypted_payload = payload.encrypted_payload
        ticket.subject = "[Encrypted support request]"
        ticket.description = "[Encrypted]"
    elif payload.encrypted_payload is not None:
        raise HTTPException(status_code=409, detail="Ticket content is already encrypted")

    legacy_messages = (
        db.execute(
            select(SupportTicketMessage).where(
                SupportTicketMessage.ticket_id == ticket.id,
                SupportTicketMessage.encrypted_payload.is_(None),
                SupportTicketMessage.author_role != "system",
            )
        )
        .scalars()
        .all()
    )
    expected_message_ids = {message.id for message in legacy_messages}
    supplied_messages = {message.id: message.encrypted_payload for message in payload.messages}
    if (
        len(supplied_messages) != len(payload.messages)
        or set(supplied_messages) != expected_message_ids
    ):
        raise HTTPException(
            status_code=422, detail="Migration must include each legacy message once"
        )
    conversation_key_ids = _conversation_key_ids(db, user_id=ticket.user_id)
    admin_key_id = _admin_key_id(db, admin_user_id=auth.user_id)
    for message in legacy_messages:
        ciphertext = supplied_messages[message.id]
        recipients = {admin_key_id} if message.is_internal else conversation_key_ids
        _validate_payload_or_422(ciphertext, recipients)
        message.encrypted_payload = ciphertext
        message.body = "[Encrypted message]"

    db.flush()
    detail = _detail(db, ticket, include_internal=True, user_email=user_email)
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.encryption.legacy.migrated",
        resource_type="support_ticket",
        resource_id=str(ticket.id),
    )
    db.commit()
    return detail


@router.post(
    "/admin/tickets/{ticket_id}/attachments/{attachment_id}/encryption",
    response_model=SupportTicketAttachmentResponse,
    dependencies=[Depends(require_permissions("admin:support:write"))],
)
async def encrypt_legacy_support_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    file: UploadFile = SUPPORT_ATTACHMENT_FILE,
    encrypted_metadata: str = Form(..., max_length=12_000),
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportTicketAttachmentResponse:
    set_db_tenant_context(db, "bypass")
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row = db.execute(
        select(SupportTicketAttachment).where(
            SupportTicketAttachment.id == attachment_id,
            SupportTicketAttachment.ticket_id == ticket.id,
            SupportTicketAttachment.tenant_id == ticket.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if row.is_encrypted:
        raise HTTPException(status_code=409, detail="Attachment is already encrypted")
    payload = await file.read(MAX_SUPPORT_ATTACHMENT_BYTES + 17)
    if len(payload) > MAX_SUPPORT_ATTACHMENT_BYTES + 16:
        raise HTTPException(status_code=413, detail="Support attachments are limited to 5 MiB")
    if len(payload) < 16:
        raise HTTPException(status_code=422, detail="Encrypted attachment is incomplete")
    expected_key_ids = _conversation_key_ids(db, user_id=ticket.user_id)
    try:
        validate_attachment_metadata(encrypted_metadata, expected_key_ids)
    except EncryptedPayloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    old_bucket, old_key = row.storage_bucket, row.storage_key
    settings = get_settings()
    stored = None
    try:
        stored = StorageService(settings).put_bytes(
            tenant_id=ticket.tenant_id,
            document_id=row.id,
            filename=f"support-{row.id}-{uuid.uuid4()}.bin",
            content_type="application/octet-stream",
            payload=payload,
        )
        row.storage_bucket = stored.bucket
        row.storage_key = stored.object_key
        row.filename = "Encrypted attachment.bin"
        row.content_type = "application/octet-stream"
        row.size_bytes = len(payload)
        row.encrypted_metadata = encrypted_metadata
        row.is_encrypted = True
        db.add(
            StorageCleanupJob(
                tenant_id=ticket.tenant_id,
                owner_user_id=row.uploaded_by_user_id,
                bucket=old_bucket,
                object_key=old_key,
            )
        )
        AuditService(db).write_event(
            tenant_id=auth.tenant_id,
            actor_user_id=auth.user_id,
            action="admin.support.encryption.attachment.migrated",
            resource_type="support_attachment",
            resource_id=str(row.id),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if stored is not None:
            try:
                StorageService(settings).delete_tenant_object(
                    tenant_id=ticket.tenant_id,
                    bucket=stored.bucket,
                    object_key=stored.object_key,
                    raise_on_error=True,
                )
            except Exception:
                pass
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=503, detail="Unable to encrypt support attachment") from exc
    return _attachment_response(row)


@router.post(
    "/admin/tickets/{ticket_id}/messages",
    response_model=SupportTicketDetailResponse,
    dependencies=[Depends(require_permissions("admin:support:write"))],
)
def add_admin_ticket_message(
    ticket_id: uuid.UUID,
    payload: AdminSupportMessageCreate,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportTicketDetailResponse:
    set_db_tenant_context(db, "bypass")
    result = db.execute(
        select(SupportTicket, User.email)
        .join(User, User.id == SupportTicket.user_id)
        .where(SupportTicket.id == ticket_id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket, user_email = result
    is_internal = payload.visibility == "internal"
    admin_key_id = _admin_key_id(db, admin_user_id=auth.user_id)
    expected_key_ids = (
        {admin_key_id} if is_internal else _conversation_key_ids(db, user_id=ticket.user_id)
    )
    _validate_payload_or_422(payload.encrypted_payload, expected_key_ids)
    db.add(
        SupportTicketMessage(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            author_user_id=auth.user_id,
            author_role="admin",
            body="[Encrypted message]",
            encrypted_payload=payload.encrypted_payload,
            is_internal=is_internal,
        )
    )
    ticket.updated_at = datetime.now(UTC)
    if not is_internal:
        if ticket.first_response_at is None:
            ticket.first_response_at = datetime.now(UTC)
        ticket.status = "waiting_user"
        add_user_notification(
            db,
            tenant_id=ticket.tenant_id,
            recipient_user_id=ticket.user_id,
            event_domain="support",
            event_type="ticket_reply",
            title="Support replied to your request",
            message="There is a new encrypted reply to your support request.",
            href=f"/dashboard/support?ticket={ticket.id}",
            resource_id=ticket.id,
            idempotency_key=f"support:reply:{uuid.uuid4()}",
        )
    db.flush()
    detail = _detail(db, ticket, include_internal=True, user_email=user_email)
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.ticket.message.created",
        resource_type="support_ticket",
        resource_id=str(ticket.id),
    )
    db.commit()
    return detail


@router.patch(
    "/admin/tickets/{ticket_id}",
    response_model=SupportTicketResponse,
    dependencies=[Depends(require_permissions("admin:support:write"))],
)
def update_ticket_admin(
    ticket_id: uuid.UUID,
    payload: SupportTicketUpdate,
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> SupportTicketResponse:
    set_db_tenant_context(db, "bypass")
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    old_status = ticket.status
    if payload.status is not None:
        ticket.status = payload.status
    if payload.category is not None:
        ticket.category = payload.category
    if payload.priority is not None:
        ticket.priority = payload.priority
        first_hours, resolution_hours = {
            "low": (24, 168),
            "normal": (8, 72),
            "high": (2, 24),
            "urgent": (1, 8),
        }[payload.priority]
        if ticket.first_response_at is None:
            ticket.first_response_due_at = ticket.created_at + timedelta(hours=first_hours)
        if ticket.status not in {"resolved", "closed"}:
            ticket.resolution_due_at = ticket.created_at + timedelta(hours=resolution_hours)
    if "assigned_admin_id" in payload.model_fields_set:
        prior_assignee_id = ticket.assigned_admin_id
        if payload.assigned_admin_id is None:
            ticket.assigned_admin_id = None
        else:
            allowlisted_emails = {
                email.strip().lower()
                for email in get_settings().bootstrap_super_admin_emails
                if email.strip()
            }
            assignee = db.execute(
                select(User).where(User.id == payload.assigned_admin_id, User.is_active.is_(True))
            ).scalar_one_or_none()
            if assignee is None or assignee.email.lower() not in allowlisted_emails:
                raise HTTPException(
                    status_code=422, detail="Assignee must be an active platform administrator"
                )
            ticket.assigned_admin_id = assignee.id
        if ticket.assigned_admin_id and ticket.assigned_admin_id != prior_assignee_id:
            assigned_user = db.get(User, ticket.assigned_admin_id)
            if assigned_user:
                add_user_notification(
                    db,
                    tenant_id=assigned_user.tenant_id,
                    recipient_user_id=assigned_user.id,
                    event_domain="support",
                    event_type="ticket_assigned",
                    title="Support ticket assigned to you",
                    message=f"A support ticket priority changed to {ticket.priority}.",
                    href=f"/dashboard/admin/support?ticket={ticket.id}",
                    resource_id=ticket.id,
                    idempotency_key=f"support:assigned:{ticket.id}:{assigned_user.id}:{uuid.uuid4()}",
                )
    ticket.updated_at = datetime.now(UTC)
    if ticket.status != old_status:
        ticket.resolved_at = datetime.now(UTC) if ticket.status in {"resolved", "closed"} else None
        db.add(
            SupportTicketMessage(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                author_user_id=auth.user_id,
                author_role="system",
                kind="status_changed",
                body=f"Status changed from {old_status.replace('_', ' ')} to {ticket.status.replace('_', ' ')}.",
            )
        )
        add_user_notification(
            db,
            tenant_id=ticket.tenant_id,
            recipient_user_id=ticket.user_id,
            event_domain="support",
            event_type="ticket_status_changed",
            title="Support request updated",
            message=f"Your support ticket status changed to {ticket.status.replace('_', ' ')}.",
            href=f"/dashboard/support?ticket={ticket.id}",
            resource_id=ticket.id,
            idempotency_key=f"support:status:{ticket.id}:{uuid.uuid4()}",
        )
    AuditService(db).write_event(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="admin.support.ticket.updated",
        resource_type="support_ticket",
        resource_id=str(ticket.id),
    )
    db.commit()
    return SupportTicketResponse.model_validate(ticket)
