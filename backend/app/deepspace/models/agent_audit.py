import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.platform.database.base import Base


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), index=True)
    user_id = Column(UUID(as_uuid=True), index=True)
    conversation_id = Column(UUID(as_uuid=True), index=True)

    tool_name = Column(String(255), nullable=False)
    tool_args = Column(JSON, nullable=True)
    tool_result = Column(Text, nullable=True)

    status = Column(String(50), default="success")  # success, failed, denied
    execution_time_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return f"<AgentAuditLog {self.tool_name} {self.status}>"
