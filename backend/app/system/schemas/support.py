from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SupportCategory = Literal[
    "complaint",
    "feedback",
    "query",
    "technical_issue",
    "account_access",
    "billing_plan",
    "documents_storage",
    "query_results",
    "deepspace_agent",
    "provider_integrations",
    "security_privacy",
    "feature_request",
    "other",
]
SupportStatus = Literal["open", "in_progress", "waiting_user", "resolved", "closed"]


class SupportTicketBase(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=20_000)
    category: SupportCategory = "query"
    encrypted_payload: str | None = Field(default=None, max_length=150_000)


class SupportTicketCreate(BaseModel):
    encrypted_payload: str = Field(..., min_length=100, max_length=150_000)
    category: SupportCategory = "query"

    model_config = ConfigDict(extra="forbid")


class SupportTicketUpdate(BaseModel):
    status: SupportStatus | None = None
    category: SupportCategory | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assigned_admin_id: uuid.UUID | None = None


class SupportTicketResponse(SupportTicketBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    priority: str = "normal"
    assigned_admin_id: uuid.UUID | None = None
    first_response_due_at: datetime | None = None
    resolution_due_at: datetime | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
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


class SupportTicketMessageCreate(BaseModel):
    encrypted_payload: str = Field(..., min_length=100, max_length=150_000)

    model_config = ConfigDict(extra="forbid")


class AdminSupportMessageCreate(SupportTicketMessageCreate):
    visibility: Literal["public", "internal"] = "public"


class SupportTicketMessageResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID | None
    author_role: str
    kind: str
    body: str
    encrypted_payload: str | None = None
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupportTicketAttachmentResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    download_url: str
    is_encrypted: bool = False
    encrypted_metadata: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SupportTicketDetailResponse(SupportTicketResponse):
    user_email: str | None = None
    messages: list[SupportTicketMessageResponse]
    attachments: list[SupportTicketAttachmentResponse] = Field(default_factory=list)


class AdminSupportQueueItem(SupportTicketResponse):
    user_email: str


class AdminSupportQueueResponse(BaseModel):
    items: list[AdminSupportQueueItem]
    total: int
    open_count: int
    overdue_count: int
