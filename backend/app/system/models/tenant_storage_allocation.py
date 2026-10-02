from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class TenantStorageAllocation(Base):
    """Durable logical storage allocation for one tenant/workspace."""

    __tablename__ = "tenant_storage_allocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    allocated_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    measured_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Retention is intentionally tenant-scoped because the quota is tenant-
    # scoped.  ``off`` is the safe default for every existing allocation.
    retention_mode: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'off'")
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    retention_policy_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    retention_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
