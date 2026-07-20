from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class RuntimeEvent:
    """Internal runtime event before mapping to the stable frontend SSE contract."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


def runtime_event(name: str, **data: Any) -> RuntimeEvent:
    return RuntimeEvent(name=name, data=data)
