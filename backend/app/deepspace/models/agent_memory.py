from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text

from app.core.config import get_settings
from app.platform.database.base import Base

_settings = get_settings()


class AgentMemory(Base):
    """Persistent DeepSpace memory retained for the productivity workspace."""

    __tablename__ = "agent_memory"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    key = Column(String, index=True, nullable=False)
    value = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)
    embedding_vector = Column(Vector(_settings.embedding_dimension), nullable=True)
    embedding_provider = Column(String, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_version = Column(String, nullable=True)
    content_hash = Column(String, index=True, nullable=True)
    importance_score = Column(Float, default=0.5, nullable=False)
    confidence_score = Column(Float, default=1.0, nullable=False)
    status = Column(String, default="active", nullable=False, index=True)
    source = Column(String, nullable=True)
    conversation_id = Column(String, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    access_count = Column(Integer, default=0, nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)
    scope = Column(String, index=True, default="persistent")
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
