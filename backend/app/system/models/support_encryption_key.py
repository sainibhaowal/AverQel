from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class SupportEncryptionKey(Base):
    """Public key plus client-encrypted private-key backup for support E2EE."""

    __tablename__ = "support_encryption_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", name="uq_support_encryption_keys_user_scope"),
        Index("ix_support_encryption_keys_scope_tenant", "scope", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    iv: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
