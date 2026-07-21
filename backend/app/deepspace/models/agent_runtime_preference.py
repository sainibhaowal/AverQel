from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint

from app.platform.database.base import Base


class AgentRuntimePreference(Base):
    __tablename__ = "agent_runtime_preferences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "conversation_id",
            "preference_key",
            name="uq_agent_runtime_preference_scope_key",
        ),
        Index("ix_agent_runtime_preferences_tenant_id", "tenant_id"),
        Index("ix_agent_runtime_preferences_user_id", "user_id"),
        Index("ix_agent_runtime_preferences_conversation_id", "conversation_id"),
        Index("ix_agent_runtime_preferences_preference_key", "preference_key"),
    )

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    conversation_id = Column(String, nullable=True)
    preference_key = Column(String, nullable=False)
    preference_value = Column(String, nullable=False)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
