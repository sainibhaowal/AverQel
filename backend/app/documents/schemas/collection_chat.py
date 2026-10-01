"""Schemas for real-time collection chat."""

from pydantic import BaseModel, ConfigDict, Field


class CollectionChatMessage(BaseModel):
    id: str
    collection_id: str
    user_id: str
    user_email: str
    message: str
    client_message_id: str | None = None
    status: str = "sent"
    is_media: bool = False
    media_mime_type: str | None = None
    media_id: str | None = None
    media_object_key: str | None = None
    reactions: str = "{}"
    receipts: list[dict[str, str | None]] = Field(default_factory=list)
    created_at: str


class CreateChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4096)
    client_message_id: str | None = Field(default=None, max_length=128)
    is_media: bool = False
    media_mime_type: str | None = None
    media_id: str | None = Field(default=None, max_length=64)
    media_object_key: str | None = Field(default=None, max_length=1024)

    model_config = ConfigDict(extra="forbid")
