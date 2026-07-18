from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SupportTicketBase(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    category: Literal["complaint", "feedback", "query"] = "query"


class SupportTicketCreate(SupportTicketBase):
    pass


class SupportTicketUpdate(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None
    category: Literal["complaint", "feedback", "query"] | None = None


class SupportTicketResponse(SupportTicketBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSupportSummary(BaseModel):
    user_id: uuid.UUID
    email: str
    ticket_count: int
    last_ticket_at: datetime | None
    latest_tickets: list[SupportTicketResponse]

    model_config = ConfigDict(from_attributes=True)


class AdminSupportListResponse(BaseModel):
    items: list[UserSupportSummary]
