from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

from app.platform.database.base import Base


class AgentTodo(Base):
    """Small task ledger used by the DeepSpace productivity surface."""

    __tablename__ = "agent_todos"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=True)
    content = Column(Text, nullable=False)
    active_form = Column(String, nullable=False)
    status = Column(String, default="pending")
    priority = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    automation_json = Column(JSON, default=dict)
    is_recurring = Column(Integer, default=0)
    enabled = Column(Integer, default=1)
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
