from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.auth.dependencies import AuthContext


@dataclass(slots=True)
class RuntimeContext:
    """Executor lifecycle context passed to runtime hooks."""

    auth: AuthContext
    execution_mode: str
    conversation_id: str | None = None
    mission_id: str | None = None
    turn_index: int | None = None
    step_id: str | None = None
    phase: str | None = None
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def tenant_id(self) -> str:
        return str(self.auth.tenant_id)

    @property
    def user_id(self) -> str:
        return str(self.auth.user_id)


@dataclass(slots=True)
class ToolRuntimeContext(RuntimeContext):
    """Tool-scoped context passed to tool hooks."""

    tool_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
