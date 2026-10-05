from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    subject: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=20_000)
    category: FeedbackCategory = "suggestion"


class AppFeedbackResponse(AppFeedbackCreate):
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
    body: str = Field(..., min_length=1, max_length=10_000)


class AdminFeedbackMessageCreate(AppFeedbackMessageCreate):
    visibility: Literal["public", "internal"] = "public"


class AppFeedbackMessageResponse(BaseModel):
    id: uuid.UUID
    feedback_id: uuid.UUID
    author_user_id: uuid.UUID | None
    author_role: str
    kind: str
    body: str
    is_internal: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppFeedbackDetailResponse(AppFeedbackResponse):
    messages: list[AppFeedbackMessageResponse]
