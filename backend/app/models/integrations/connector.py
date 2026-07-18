from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_uuid7_with_fallback
from app.db.base import Base


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    SYNCING = "syncing"


class Connector(Base):
    """
    Tenant-specific instance of an integration.
    Configures where to fetch data from and how often.
    """

    __tablename__ = "connectors"
    HEALTH_CONFIG_KEY: ClassVar[str] = "health"
    LAST_SUCCESS_SNAPSHOT_KEY: ClassVar[str] = "last_success_snapshot"
    SYNC_CHECKPOINT_CONFIG_KEY: ClassVar[str] = "sync_checkpoint"

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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConnectorStatus] = mapped_column(
        SQLEnum(ConnectorStatus),
        default=ConnectorStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
        nullable=False,
    )

    # Configuration (e.g. source URL, folder path, etc)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    # Sync settings
    sync_frequency: Mapped[str] = mapped_column(
        String(50), default="daily", server_default=text("'daily'")
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    integration = relationship("Integration")
    secrets = relationship(
        "ConnectorSecret", back_populates="connector", cascade="all, delete-orphan"
    )

    @staticmethod
    def _parse_iso_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return None

    def health_contract(self) -> dict[str, Any]:
        config = self.config if isinstance(self.config, dict) else {}
        health = config.get(self.HEALTH_CONFIG_KEY)
        return dict(health) if isinstance(health, dict) else {}

    @property
    def health_status(self) -> str:
        health = self.health_contract()
        status = str(health.get("status") or "").strip().lower()
        return status or str(self.status.value if hasattr(self.status, "value") else self.status)

    @property
    def last_checked_at(self) -> datetime | None:
        health = self.health_contract()
        return self._parse_iso_datetime(
            health.get("last_checked_at") or health.get("checked_at") or health.get("updated_at")
        )

    @property
    def last_good_at(self) -> datetime | None:
        health = self.health_contract()
        return self._parse_iso_datetime(health.get("last_good_at") or health.get("last_healthy_at"))

    @property
    def circuit_open_until(self) -> datetime | None:
        health = self.health_contract()
        return self._parse_iso_datetime(
            health.get("circuit_open_until") or health.get("retry_after_at")
        )

    @property
    def consecutive_failures(self) -> int:
        health = self.health_contract()
        try:
            return max(0, int(health.get("consecutive_failures") or 0))
        except (TypeError, ValueError):
            return 0

    @property
    def health_metadata(self) -> dict[str, Any]:
        health = self.health_contract()
        metadata = health.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @property
    def last_success_snapshot(self) -> dict[str, Any] | None:
        config = self.config if isinstance(self.config, dict) else {}
        snapshot = config.get(self.LAST_SUCCESS_SNAPSHOT_KEY)
        return dict(snapshot) if isinstance(snapshot, dict) else None
