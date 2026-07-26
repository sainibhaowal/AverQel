import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.platform.database.base import Base


class AgentActivity(Base):
    """Audit activity row retained for connector/MCP compatibility."""

    __tablename__ = "agent_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    activity_type = Column(String, index=True)
    description = Column(String, nullable=False)
    source = Column(String)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
