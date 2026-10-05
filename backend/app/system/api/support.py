from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.models.user import User
from app.auth.rbac import require_permissions
from app.auth.tenancy import TenantContext, get_tenant_context
from app.core.config import get_settings
from app.ingestion.services.security.malware_scan_service import MalwareScanService
from app.platform.database.session import get_db, set_db_tenant_context
from app.system.api.admin import require_platform_admin_access
from app.system.models.support_ticket import SupportTicket
from app.system.models.support_ticket_attachment import SupportTicketAttachment
from app.system.models.support_ticket_message import SupportTicketMessage
from app.system.schemas.support import (
    AdminSupportListResponse,
    AdminSupportMessageCreate,
    AdminSupportQueueItem,
    AdminSupportQueueResponse,
    SupportTicketAttachmentResponse,
    SupportTicketCreate,
    SupportTicketDetailResponse,
    SupportTicketMessageCreate,
    SupportTicketMessageResponse,
    SupportTicketResponse,
    SupportTicketUpdate,
    UserSupportSummary,
)
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.storage_quota import StorageQuotaService
from app.system.services.storage_service import StorageService, StorageServiceError
from app.system.services.user_notifications import add_user_notification, notify_platform_admins

router = APIRouter(prefix="/support", tags=["support"])
MAX_SUPPORT_ATTACHMENT_BYTES = 5 * 1024 * 1024
SUPPORT_ATTACHMENT_FILE = File(...)
QUEUE_LIMIT = Query(default=50, ge=1, le=100)
QUEUE_OFFSET = Query(default=0, ge=0, le=100_000)
QUEUE_SEARCH = Query(default=None, max_length=120)
QUEUE_ASSIGNEE = Query(default=None)
QUEUE_UNASSIGNED = Query(default=False)
_SUPPORT_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
}


def _checked_attachment(filename: str, payload: bytes) -> tuple[str, str]:
    from pathlib import PurePath

    safe_name = PurePath(filename.replace("\\", "/")).name.strip()[:255]
    extension = PurePath(safe_name).suffix.lower()
    content_type = _SUPPORT_MIME_BY_EXTENSION.get(extension)
    valid = bool(payload)
    if extension == ".pdf":
        valid = valid and payload.startswith(b"%PDF-")
    elif extension == ".png":
        valid = valid and payload.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg", ".jpeg"}:
        valid = valid and payload.startswith(b"\xff\xd8\xff")
    elif extension == ".txt":
        try:
            payload.decode("utf-8", errors="strict")
            valid = valid and b"\x00" not in payload
        except UnicodeDecodeError:
            valid = False
    else:
        valid = False
    if not valid or not content_type:
        raise HTTPException(
            status_code=415, detail="Attachment must be a valid PDF, PNG, JPEG, or UTF-8 text file"
        )
    return safe_name, content_type


def _attachment_response(row: SupportTicketAttachment) -> SupportTicketAttachmentResponse:
    return SupportTicketAttachmentResponse(
        id=row.id,
        ticket_id=row.ticket_id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
        download_url=f"/api/v1/support/tickets/{row.ticket_id}/attachments/{row.id}",
    )


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
) -> SupportTicketDetailResponse:
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
            SupportTicketMessageResponse.model_validate(item)
            for item in _ticket_messages(db, ticket=ticket, include_internal=include_internal)
        ],
        attachments=attachments,
    )


@router.post("/tickets", response_model=SupportTicketResponse)
def create_ticket(
    payload: SupportTicketCreate,
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportTicketResponse:
    RateLimitService(get_settings()).enforce_support_submission_limit(
        tenant_id=str(tenant.tenant_id), user_id=str(auth.user_id)
    )
    now = datetime.now(UTC)
    response_hours, resolution_hours = 8, 72
    ticket = SupportTicket(
        tenant_id=tenant.tenant_id,
        user_id=auth.user_id,
        subject=payload.subject.strip(),
        description=payload.description.strip(),
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
        message=f"We received your request: {ticket.subject}",
        href=f"/dashboard/support?ticket={ticket.id}",
        resource_id=ticket.id,
        idempotency_key=f"support:received:{ticket.id}",
    )
    notify_platform_admins(
        db,
        event_domain="support",
        event_type="ticket_created",
        title="New support request",
        message=f"{ticket.category.replace('_', ' ').title()}: {ticket.subject}",
        href=f"/dashboard/admin/support?ticket={ticket.id}",
        resource_id=ticket.id,
    )
    db.commit()
    return SupportTicketResponse.model_validate(ticket)


@router.get("/tickets", response_model=list[SupportTicketResponse])
def list_my_tickets(
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[SupportTicketResponse]:
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
    auth: AuthContext = Depends(get_auth_context),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> SupportTicketDetailResponse:
    ticket = _ticket_for_user(
        db, ticket_id=ticket_id, tenant_id=tenant.tenant_id, user_id=auth.user_id
    )
    return _detail(db, ticket, include_internal=False)


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
    if ticket.status in {"resolved", "closed"}:
        old_status = ticket.status
        ticket.status = "open"
        db.add(
            SupportTicketMessage(
                tenant_id=tenant.tenant_id,
                ticket_id=ticket.id,
                author_user_id=auth.user_id,
                author_role="user",
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
            body=payload.body.strip(),
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
        message=f"New reply: {ticket.subject}",
        href=f"/dashboard/admin/support?ticket={ticket.id}",
        resource_id=f"{ticket.id}:user-reply:{uuid.uuid4()}",
    )
    db.flush()
    detail = _detail(db, ticket, include_internal=False)
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
    payload = await file.read(MAX_SUPPORT_ATTACHMENT_BYTES + 1)
    if len(payload) > MAX_SUPPORT_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="Support attachments are limited to 5 MiB")
    filename, content_type = _checked_attachment(file.filename or "attachment", payload)
    scan = MalwareScanService().scan_bytes(
        filename=filename, content_type=content_type, payload=payload
    )
    if not scan.is_clean:
        raise HTTPException(
            status_code=422, detail="Attachment could not pass the configured security scan"
        )
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
        storage_bucket=get_settings().minio_bucket,
        storage_key=f"{tenant.tenant_id}/pending/{uuid.uuid4()}",
    )
    db.add(row)
    db.flush()
    try:
        from pathlib import PurePath

        stored = StorageService(get_settings()).put_bytes(
            tenant_id=tenant.tenant_id,
            document_id=row.id,
            filename=f"support-{row.id}{PurePath(filename).suffix.lower()}",
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
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AdminSupportListResponse:
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
    return AdminSupportListResponse(items=items)


@router.get(
    "/admin/queue",
    response_model=AdminSupportQueueResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def list_support_queue_admin(
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
    set_db_tenant_context(db, "bypass")
    now = datetime.now(UTC)
    base = select(SupportTicket, User.email).join(User, User.id == SupportTicket.user_id)
    if status:
        base = base.where(SupportTicket.status == status)
    if priority:
        base = base.where(SupportTicket.priority == priority)
    if search:
        like = f"%{search.strip()}%"
        base = base.where(
            SupportTicket.subject.ilike(like)
            | SupportTicket.description.ilike(like)
            | User.email.ilike(like)
        )
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
    tickets = [
        AdminSupportQueueItem(
            **SupportTicketResponse.model_validate(ticket).model_dump(), user_email=email
        )
        for ticket, email in rows
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
    return AdminSupportQueueResponse(
        items=tickets,
        total=int(total),
        open_count=int(open_count),
        overdue_count=int(overdue_count),
    )


@router.get(
    "/admin/tickets/{ticket_id}",
    response_model=SupportTicketDetailResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def get_ticket_admin(
    ticket_id: uuid.UUID,
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
    return _detail(db, result[0], include_internal=True, user_email=result[1])


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
    db.add(
        SupportTicketMessage(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            author_user_id=auth.user_id,
            author_role="admin",
            body=payload.body.strip(),
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
            message=f"There is a new reply to: {ticket.subject}",
            href=f"/dashboard/support?ticket={ticket.id}",
            resource_id=ticket.id,
            idempotency_key=f"support:reply:{uuid.uuid4()}",
        )
    db.flush()
    detail = _detail(db, ticket, include_internal=True, user_email=user_email)
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
                    message=f"{ticket.subject} ({ticket.priority} priority)",
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
                author_role="admin",
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
            message=f"Your request is now {ticket.status.replace('_', ' ')}: {ticket.subject}",
            href=f"/dashboard/support?ticket={ticket.id}",
            resource_id=ticket.id,
            idempotency_key=f"support:status:{ticket.id}:{uuid.uuid4()}",
        )
    db.commit()
    return SupportTicketResponse.model_validate(ticket)
