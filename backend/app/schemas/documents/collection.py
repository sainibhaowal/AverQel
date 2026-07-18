from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionPermissionBase(BaseModel):
    user_id: uuid.UUID
    role: str = Field(pattern="^(member|pending|owner|shared)$")

    model_config = ConfigDict(extra="forbid")


class CollectionPermissionResponse(CollectionPermissionBase):
    id: uuid.UUID
    collection_id: uuid.UUID
    user_email: str | None = None
    user_avatar: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class DocumentCollectionBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: str = Field(default="", max_length=1024)
    expiry_days: int = Field(default=0)

    model_config = ConfigDict(extra="forbid")


class DocumentCollectionCreate(DocumentCollectionBase):
    pass


class DocumentCollectionResponse(DocumentCollectionBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    connection_code: str
    other_member_email: str | None = None
    other_member_avatar: str | None = None
    requester_access_role: str | None = Field(
        default=None,
        pattern="^(member|pending|owner|shared)$",
    )
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class CollectionInvitationResponse(DocumentCollectionResponse):
    inviter_user_id: uuid.UUID | None = None
    inviter_user_email: str | None = None


class CollectionInvitationRespond(BaseModel):
    action: str = Field(pattern="^(approve|deny)$")

    model_config = ConfigDict(extra="forbid")


class CollectionDocumentAdd(BaseModel):
    document_ids: list[uuid.UUID]

    model_config = ConfigDict(extra="forbid")


class CollectionDocumentRemove(BaseModel):
    document_ids: list[uuid.UUID]

    model_config = ConfigDict(extra="forbid")


class CollectionPermissionAdd(BaseModel):
    connection_code: str = Field(min_length=6, max_length=16)

    model_config = ConfigDict(extra="forbid")


class CollectionPermissionRemove(BaseModel):
    user_ids: list[uuid.UUID]

    model_config = ConfigDict(extra="forbid")


class CollectionNotificationResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID | None = None
    collection_name: str
    event_type: str
    idempotency_key: str | None = None
    message: str
    created_at: datetime
    read_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")
