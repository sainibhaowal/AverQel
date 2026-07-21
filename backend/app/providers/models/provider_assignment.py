from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_uuid7_with_fallback
from app.db.base import Base


class ProviderAssignment(Base):
    __tablename__ = "provider_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "owner_user_id",
            "feature_scope",
            "priority",
            name="uq_provider_assignments_owner_scope_priority",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7_with_fallback,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    visibility_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="tenant",
        server_default=text("'tenant'"),
        index=True,
    )
    feature_scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=text("100"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )
