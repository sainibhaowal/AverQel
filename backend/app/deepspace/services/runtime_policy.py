from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ToolMode = Literal["read", "write", "interactive"]


@dataclass(frozen=True, slots=True)
class ToolPolicyDecision:
    allowed: bool
    mode: ToolMode | None = None
    reason: str | None = None


class DeepSpaceToolPolicy:
    """The allowlist and workspace boundary for DeepSpace productivity tools."""

    _MODES: dict[str, ToolMode] = {
        "web_search": "read",
        "url_read": "read",
        "image_read": "read",
        "todo_read": "read",
        "todo_check": "read",
        "observe": "read",
        "analyze": "read",
        "read": "read",
        "find": "read",
        "todo_write": "write",
        "todo_mark": "write",
        "write": "write",
        "edit": "write",
        "delete": "write",
        "ask_user": "interactive",
        # Final verification must not race a write-capable tool emitted in the
        # same provider response.
        "final": "write",
    }

    def decide(self, tool_name: str, arguments: dict[str, Any]) -> ToolPolicyDecision:
        del arguments
        mode = self._MODES.get(tool_name)
        if mode is None:
            return ToolPolicyDecision(
                False, reason="Tool is not in the DeepSpace productivity allowlist."
            )
        return ToolPolicyDecision(True, mode=mode)

    def before_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolPolicyDecision:
        """Hook point for future tenant policy extensions; deny by default outside the allowlist."""

        return self.decide(tool_name, arguments)

    def after_tool(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
        """Hook point that prevents internal runtime values from reaching the model/UI."""

        del tool_name
        return {key: value for key, value in result.items() if not key.startswith("_")}

    @classmethod
    def mode(cls, tool_name: str) -> ToolMode | None:
        return cls._MODES.get(tool_name)
