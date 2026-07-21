from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.platform.database.base import Base

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class FeedbackCampaign(Base):
    __tablename__ = "feedback_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(tz=UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )


class AppFeedback(Base):
    __tablename__ = "app_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(
        UUID(as_uuid=True), ForeignKey("feedback_campaigns.id", ondelete="SET NULL"), nullable=True
    )

    subject = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    rating = Column(JSON, nullable=True)  # Store structured ratings if needed
    category = Column(String(50), default="suggestion")  # suggestion, bug, achievement, etc

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(tz=UTC))
