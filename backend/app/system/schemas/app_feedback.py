from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.system.schemas.support_encryption import SupportPublicKeyResponse


class FeedbackCampaignBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    is_active: bool = True


class FeedbackCampaignCreate(FeedbackCampaignBase):
    pass


class FeedbackCampaignResponse(FeedbackCampaignBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


FeedbackCategory = Literal[
    "suggestion",
    "bug",
    "achievement",
    "ux_improvement",
    "documents_collections",
    "query_quality",
    "deepspace_agent",
    "provider_integrations",
    "billing_plan",
    "performance",
    "reliability",
    "accessibility",
    "security_privacy",
    "positive_feedback",
    "other",
]
FeedbackStatus = Literal["new", "triaged", "planned", "in_progress", "completed", "declined"]


class AppFeedbackCreate(BaseModel):
    campaign_id: uuid.UUID | None = None
    encrypted_payload: str = Field(..., min_length=100, max_length=150_000)
    category: FeedbackCategory = "suggestion"

    model_config = ConfigDict(extra="forbid")


class AppFeedbackResponse(BaseModel):
    campaign_id: uuid.UUID | None = None
    subject: str = "[Encrypted feedback]"
    content: str = "[Encrypted]"
    encrypted_payload: str | None = None
    category: FeedbackCategory = "suggestion"
    id: uuid.UUID
    user_id: uuid.UUID
    email: str | None = None
    created_at: datetime
    status: FeedbackStatus = "new"
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AppFeedbackUpdate(BaseModel):
    status: FeedbackStatus


class AppFeedbackMessageCreate(BaseModel):
    encrypted_payload: str = Field(..., min_length=100, max_length=150_000)

    model_config = ConfigDict(extra="forbid")


class AdminFeedbackMessageCreate(AppFeedbackMessageCreate):
    visibility: Literal["public", "internal"] = "public"


class AppFeedbackMessageResponse(BaseModel):
    id: uuid.UUID
    feedback_id: uuid.UUID
    author_user_id: uuid.UUID | None
    author_role: str
    kind: str
    body: str
    encrypted_payload: str | None = None
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppFeedbackDetailResponse(AppFeedbackResponse):
    messages: list[AppFeedbackMessageResponse]


class AdminAppFeedbackResponse(BaseModel):
    """Staff view of feedback without account identifiers or contact details."""

    id: uuid.UUID
    campaign_id: uuid.UUID | None
    subject: str
    content: str
    encrypted_payload: str | None = None
    category: FeedbackCategory
    created_at: datetime
    status: FeedbackStatus
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AdminAppFeedbackMessageResponse(BaseModel):
    id: uuid.UUID
    feedback_id: uuid.UUID
    author_role: str
    kind: str
    body: str
    encrypted_payload: str | None = None
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AdminAppFeedbackDetailResponse(AdminAppFeedbackResponse):
    messages: list[AdminAppFeedbackMessageResponse]
    recipient_public_key: SupportPublicKeyResponse | None = None
