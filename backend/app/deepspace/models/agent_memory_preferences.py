from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, String, UniqueConstraint

from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.base import Base


class AgentMemoryPreferences(Base):
    """Tenant/user-owned consent controls for DeepSpace memory consolidation."""

    __tablename__ = "agent_memory_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_agent_memory_preferences_owner"),
    )

    id = Column(String, primary_key=True, default=lambda: str(generate_uuid7_with_fallback()))
    tenant_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    automatic_capture_enabled = Column(Boolean, default=False, nullable=False)
    review_inferred_memories = Column(Boolean, default=True, nullable=False)
    memory_retrieval_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
