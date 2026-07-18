from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.deepspace.execution.agent_permissions import PermissionLevel, get_permission


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    disposition: str
    risk_class: str
    reason: str
    requires_idempotency: bool


class AutonomyPolicy:
    """Policy-owned approval logic. Models cannot self-authorize a risky action."""

    @staticmethod
    def assess(*, tool_name: str, args: dict[str, Any], execution_mode: str) -> AutonomyDecision:
        permission = get_permission(tool_name)
        external = tool_name.startswith(("github_", "drive_", "gmail_", "calendar_", "notion_", "slack_")) or tool_name in {"mcp_call", "sync_connector", "crawl_url"}
        if permission == PermissionLevel.TIER1_AUTO and not external:
            return AutonomyDecision("allow", "read_only", "deterministic read-only capability", False)
        if permission in {PermissionLevel.TIER4_WARN, PermissionLevel.TIER5_SPAWN}:
            return AutonomyDecision("block", "privileged", "privileged or destructive capability requires explicit system policy", True)
        if execution_mode == "full_access" and not external and permission == PermissionLevel.TIER2_CONFIRM:
            return AutonomyDecision("allow", "internal_write", "full-access mode permits scoped internal writes", True)
        risk = "external_side_effect" if external else "write_or_execution"
        return AutonomyDecision("require_human", risk, "side-effecting or uncertain capability requires accountable approval", True)
