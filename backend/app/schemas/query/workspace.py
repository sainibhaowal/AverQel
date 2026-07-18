from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShareQueryRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PinFindingRequest(BaseModel):
    query_id: uuid.UUID
    chunk_id: uuid.UUID
    notes: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")


class PinnedFindingResponse(BaseModel):
    id: uuid.UUID
    query_id: uuid.UUID
    chunk_id: uuid.UUID
    notes: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class CommentCreate(BaseModel):
    target_type: str = Field(..., pattern="^(query|finding)$")
    target_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    content: str = Field(..., min_length=1, max_length=5000)

    model_config = ConfigDict(extra="forbid")


class CommentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    parent_id: uuid.UUID | None
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
