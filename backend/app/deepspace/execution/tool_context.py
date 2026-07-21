from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    mission_id: str | None = None
    lane_id: str | None = None
    tool_call_id: str | None = None
    temp_state_store: dict[str, Any] = field(default_factory=dict)

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.temp_state_store.get(key, default)

    def set_state(self, key: str, value: Any) -> Any:
        self.temp_state_store[key] = value
        return value

    def pop_state(self, key: str, default: Any = None) -> Any:
        return self.temp_state_store.pop(key, default)

    def ensure_state(self, key: str, factory: Any) -> Any:
        if key not in self.temp_state_store:
            self.temp_state_store[key] = factory() if callable(factory) else factory
        return self.temp_state_store[key]

    def lineage(self) -> dict[str, str | None]:
        lineage: dict[str, str | None] = {
            "tenant_id": str(self.tenant_id),
            "user_id": str(self.user_id),
            "conversation_id": (
                str(self.conversation_id) if self.conversation_id is not None else None
            ),
            "mission_id": self.mission_id,
            "lane_id": self.lane_id,
        }
        return lineage

    def audit_snapshot(self) -> dict[str, str | None]:
        return self.lineage()
