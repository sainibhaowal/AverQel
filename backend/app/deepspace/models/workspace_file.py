from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.base import Base


class DeepSpaceWorkspaceFile(Base):
    """User- or agent-created text file in a conversation's DeepSpace Library."""

    __tablename__ = "deepspace_workspace_files"
    __table_args__ = (
        Index(
            "uq_deepspace_workspace_files_root_name",
            "conversation_id",
            "name",
            unique=True,
            postgresql_where=text("parent_folder_id IS NULL"),
        ),
        Index(
            "uq_deepspace_workspace_files_folder_name",
            "conversation_id",
            "parent_folder_id",
            "name",
            unique=True,
            postgresql_where=text("parent_folder_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid7_with_fallback
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deepspace_workspace_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(127), nullable=False, server_default=text("'text/markdown'")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'user'"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    storage_bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_binary: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
