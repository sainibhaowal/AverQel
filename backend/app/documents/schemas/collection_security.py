from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionDeviceUpsert(BaseModel):
    device_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    label: str = Field(default="Browser", min_length=1, max_length=128)
    identity_public_key: str | None = Field(default=None, max_length=4096)
    protocol_version: str = Field(default="legacy-shared-key", max_length=32)
    model_config = ConfigDict(extra="forbid")


class CollectionDeviceResponse(BaseModel):
    id: uuid.UUID
    device_id: str
    label: str
    protocol_version: str
    revoked_at: datetime | None
    last_seen_at: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class CollectionBlockRequest(BaseModel):
    user_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=255)
    model_config = ConfigDict(extra="forbid")


class CollectionReportRequest(BaseModel):
    reported_user_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=64)
    details: str | None = Field(default=None, max_length=4000)
    model_config = ConfigDict(extra="forbid")


class CollectionPushSubscriptionRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    endpoint: str = Field(min_length=1, max_length=2048)
    p256dh: str = Field(min_length=16, max_length=512)
    auth: str = Field(min_length=8, max_length=256)
    model_config = ConfigDict(extra="forbid")
