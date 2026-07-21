"""Schemas for message feedback."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeedbackCreate(BaseModel):
    message_id: UUID
    is_helpful: bool
    reason: str | None = None


class FeedbackResponse(BaseModel):
    id: UUID
    message_id: UUID
    is_helpful: bool
    reason: str | None

    model_config = ConfigDict(from_attributes=True)
