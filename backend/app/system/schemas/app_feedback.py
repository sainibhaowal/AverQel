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


class AppFeedbackCreate(BaseModel):
    campaign_id: uuid.UUID | None = None
    subject: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    category: Literal["suggestion", "bug", "achievement", "ux_improvement"] = (
        "suggestion"
    )


class AppFeedbackResponse(AppFeedbackCreate):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
