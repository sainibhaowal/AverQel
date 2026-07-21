import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.platform.database.base import Base


class AgentActivity(Base):
    """
    Logs autonomous actions performed by the Zevaris Agent (DeepSpace).
    Provides transparency for proactive tasks like Gmail scanning,
    Calendar scheduling, and background ingestion.
    """

    __tablename__ = "agent_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    activity_type = Column(String, index=True)  # e.g., "scan", "sync", "reason", "notify"
    description = Column(String, nullable=False)
    source = Column(String)  # e.g., "gmail", "calendar", "notion"
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return f"<AgentActivity {self.activity_type} - {self.description}>"
