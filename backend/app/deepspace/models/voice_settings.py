from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class DeepSpaceVoiceSettings(Base):
    """Durable voice settings for one tenant-owned user."""

    __tablename__ = "deepspace_voice_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voice: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("'alba'"))
    speed: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    pitch: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    volume: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))
    cloned_voice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloned_voice_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloned_voice_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
