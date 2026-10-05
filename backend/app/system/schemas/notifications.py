from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

NotificationDomain = Literal[
    "support",
    "feedback",
    "query",
    "provider",
    "storage",
    "plan",
    "system",
    "documents",
    "deepspace",
    "collection_moderation",
    "collections",
]


class NotificationCategoryResponse(BaseModel):
    code: NotificationDomain
    label: str
    channels: list[Literal["in_app", "email"]]

    model_config = ConfigDict(extra="forbid")


NOTIFICATION_CATEGORY_CATALOG = (
    NotificationCategoryResponse(code="support", label="Support", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="feedback", label="Feedback", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="query", label="Query", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="provider", label="Provider", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="storage", label="Storage", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="plan", label="Plan", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="system", label="System", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="documents", label="Documents", channels=["in_app", "email"]),
    NotificationCategoryResponse(code="deepspace", label="DeepSpace", channels=["in_app", "email"]),
    NotificationCategoryResponse(
        code="collection_moderation", label="Collection moderation", channels=["in_app", "email"]
    ),
    NotificationCategoryResponse(code="collections", label="Collections", channels=["in_app"]),
)


class NotificationPreferenceResponse(BaseModel):
    email_enabled: bool
    email_delivery_available: bool = False
    digest_frequency: Literal["none", "daily", "weekly"]
    timezone: str = "UTC"
    preferences_configured: bool = False
    muted_domains: list[NotificationDomain]
    categories: list[NotificationCategoryResponse]

    model_config = ConfigDict(extra="forbid")


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    digest_frequency: Literal["none", "daily", "weekly"] | None = None
    timezone: str | None = None
    muted_domains: list[NotificationDomain] | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def reject_null_updates(self) -> NotificationPreferenceUpdate:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self

    model_config = ConfigDict(extra="forbid")


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
