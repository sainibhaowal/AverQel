"""Canonical, revisioned visual document contracts.

The visual payload is deliberately JSON serialisable so the same document can
be stored in a chat message, a note, or an editable Library artifact.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VisualAssetRef(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    owned_url: str | None = Field(default=None, max_length=4096)
    mime_type: str | None = Field(default=None, max_length=127)
    status: str = Field(default="pending", max_length=32)
    file_id: str | None = Field(default=None, max_length=64)
    retention: Literal["temporary", "library"] | None = None

    model_config = ConfigDict(extra="forbid")


class VisualHistoryEntry(BaseModel):
    revision: int = Field(ge=0)
    source: str = Field(min_length=1, max_length=64)
    actor: str | None = Field(default=None, max_length=128)
    at: str | None = Field(default=None, max_length=64)

    model_config = ConfigDict(extra="forbid")


class VisualDocument(BaseModel):
    """Envelope shared by chat, note and Library persistence."""

    block_id: str = Field(min_length=1, max_length=160)
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    kind: str = Field(min_length=1, max_length=32)
    data: dict[str, Any] = Field(default_factory=dict)
    source_markdown: str | None = None
    source_mermaid: str | None = None
    assets: list[VisualAssetRef] = Field(default_factory=list, max_length=100)
    history: list[VisualHistoryEntry] = Field(default_factory=list, max_length=100)
    undo: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
