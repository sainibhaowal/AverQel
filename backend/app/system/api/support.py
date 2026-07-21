from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.system.api.admin import require_platform_admin_access
from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.db.session import get_db
from app.auth.models.user import User
from app.system.models.support_ticket import SupportTicket
from app.system.schemas.support import (
    AdminSupportListResponse,
    SupportTicketCreate,
    SupportTicketResponse,
    SupportTicketUpdate,
    UserSupportSummary,
)

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=SupportTicketResponse)
def create_ticket(
    payload: SupportTicketCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> SupportTicketResponse:
    ticket = SupportTicket(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        subject=payload.subject,
        description=payload.description,
        category=payload.category,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return SupportTicketResponse.model_validate(ticket)


@router.get("/tickets", response_model=list[SupportTicketResponse])
def list_my_tickets(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[SupportTicketResponse]:
    tickets = (
        db.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == auth.user_id)
            .order_by(desc(SupportTicket.created_at))
        )
        .scalars()
        .all()
    )
    return [SupportTicketResponse.model_validate(ticket) for ticket in tickets]


@router.get(
    "/admin/tickets",
    response_model=AdminSupportListResponse,
    dependencies=[Depends(require_permissions("admin:support:read"))],
)
def list_all_tickets_admin(
    auth: AuthContext = Depends(require_platform_admin_access),
    db: Session = Depends(get_db),
) -> AdminSupportListResponse:
    # Group by user
    user_ids = (
        db.execute(select(SupportTicket.user_id).group_by(SupportTicket.user_id))
        .scalars()
        .all()
    )

    items = []
    for user_id in user_ids:
        user = db.get(User, user_id)
        if not user:
            continue

        tickets = (
            db.execute(
                select(SupportTicket)
                .where(SupportTicket.user_id == user_id)
                .order_by(desc(SupportTicket.created_at))
            )
            .scalars()
            .all()
        )

        items.append(
            UserSupportSummary(
                user_id=user_id,
                email=user.email,
                ticket_count=len(tickets),
                last_ticket_at=tickets[0].created_at if tickets else None,
                latest_tickets=[
                    SupportTicketResponse.model_validate(t) for t in tickets[:5]
                ],
            )
        )

    return AdminSupportListResponse(items=items)


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
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if payload.status is not None:
        ticket.status = payload.status
    if payload.category is not None:
        ticket.category = payload.category

    db.commit()
    db.refresh(ticket)
    return SupportTicketResponse.model_validate(ticket)
