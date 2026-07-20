"""Schemas for real-time collection chat."""

from pydantic import BaseModel


class CollectionChatMessage(BaseModel):
    id: str
    collection_id: str
    user_id: str
    user_email: str
    message: str
    status: str = "sent"
    is_media: bool = False
    media_mime_type: str | None = None
    reactions: str = "{}"
    created_at: str


class CreateChatMessage(BaseModel):
    message: str
    is_media: bool = False
    media_mime_type: str | None = None
