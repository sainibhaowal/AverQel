from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class NotificationPreferenceResponse(BaseModel):
    email_enabled: bool
    email_delivery_available: bool = False
    digest_frequency: Literal["none", "daily", "weekly"]
    muted_domains: list[str]


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    digest_frequency: Literal["none", "daily", "weekly"] | None = None
    muted_domains: (
        list[
            Literal[
                "support",
                "feedback",
                "query",
                "provider",
                "storage",
                "plan",
                "system",
                "collection_moderation",
            ]
        ]
        | None
    ) = None


class UserNotificationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    recipient_user_id: uuid.UUID
    event_domain: str
    event_type: str
    title: str
    message: str
    href: str
    resource_id: str | None
    created_at: datetime
    read_at: datetime | None
    dismissed_at: datetime | None
    source: Literal["application"] = "application"

    model_config = ConfigDict(from_attributes=True)
