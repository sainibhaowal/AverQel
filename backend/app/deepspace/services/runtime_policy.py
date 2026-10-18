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
        "discover_tools": "read",
        "web_search": "read",
        "url_read": "read",
        "image_read": "read",
        "analyze": "read",
        "read": "read",
        "find": "read",
        "todo_write": "write",
        "write": "write",
        "edit": "write",
        "delete": "write",
        "sandbox_execute": "write",
        "artifact_create": "write",
        "ask_user": "interactive",
    }

    def decide(self, tool_name: str, arguments: dict[str, Any]) -> ToolPolicyDecision:
        if tool_name == "todo_write" and str(arguments.get("operation") or "") in {
            "read",
            "check",
        }:
            return ToolPolicyDecision(True, mode="read")
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
