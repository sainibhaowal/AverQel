"""
Agent Permission System for DeepSpace Autonomous Intelligence.

Defines permission levels for each tool the agent can invoke.
AUTO: Always allowed, no user notification needed.
NOTIFY: Auto-executed but user sees a notification of what happened.
APPROVAL: Agent must pause and wait for explicit user approval.
"""

from __future__ import annotations

from enum import Enum


class PermissionLevel(str, Enum):
    TIER1_AUTO = "tier1_auto"  # Read-only, no side effects
    TIER2_CONFIRM = "tier2_confirm"  # Writes, edits
    TIER3_APPROVE = "tier3_approve"  # Execution (Bash)
    TIER4_WARN = "tier4_warn"  # Destructive (rm, drop)
    TIER5_SPAWN = "tier5_spawn"  # Subagent spawning


TOOL_PERMISSIONS: dict[str, PermissionLevel] = {
    # Tier 1 - Auto-approve (Read-only, no side effects)
    "read_file": PermissionLevel.TIER1_AUTO,
    "list_dir": PermissionLevel.TIER1_AUTO,
    "glob": PermissionLevel.TIER1_AUTO,
    "grep": PermissionLevel.TIER1_AUTO,
    "web_search": PermissionLevel.TIER1_AUTO,
    "web_fetch": PermissionLevel.TIER1_AUTO,
    "memory_read": PermissionLevel.TIER1_AUTO,
    "todo_read": PermissionLevel.TIER1_AUTO,
    "ask_user_question": PermissionLevel.TIER1_AUTO,
    "search_ecosystem_docs": PermissionLevel.TIER1_AUTO,
    "get_connector_status": PermissionLevel.TIER1_AUTO,
    "list_connectors": PermissionLevel.TIER1_AUTO,
    "bash_output": PermissionLevel.TIER1_AUTO,
    "enter_plan_mode": PermissionLevel.TIER1_AUTO,
    "exit_plan_mode": PermissionLevel.TIER1_AUTO,
    "skill": PermissionLevel.TIER1_AUTO,
    "slash_command": PermissionLevel.TIER1_AUTO,
    "memory_search": PermissionLevel.TIER1_AUTO,
    # Tier 2 - Require Confirmation (Writes, state mutations)
    "write_file": PermissionLevel.TIER2_CONFIRM,
    "edit_file": PermissionLevel.TIER2_CONFIRM,
    "notebook_edit": PermissionLevel.TIER2_CONFIRM,
    "memory_write": PermissionLevel.TIER2_CONFIRM,
    "todo_write": PermissionLevel.TIER2_CONFIRM,
    "sync_connector": PermissionLevel.TIER2_CONFIRM,
    "crawl_url": PermissionLevel.TIER2_CONFIRM,
    "data_analyze": PermissionLevel.TIER2_CONFIRM,
    "document_convert": PermissionLevel.TIER2_CONFIRM,
    "mcp_call": PermissionLevel.TIER2_CONFIRM,  # MCP-delegated tool calls
    # Tier 3 - Require Explicit Approval (Shell execution)
    "bash": PermissionLevel.TIER3_APPROVE,
    "kill_shell": PermissionLevel.TIER3_APPROVE,
    # Tier 5 - Subagent spawning
    "task": PermissionLevel.TIER5_SPAWN,
}


def get_permission(tool_name: str) -> PermissionLevel:
    return TOOL_PERMISSIONS.get(tool_name, PermissionLevel.TIER3_APPROVE)


_PERMISSION_TIER_NUMBERS: dict[PermissionLevel, int] = {
    PermissionLevel.TIER1_AUTO: 1,
    PermissionLevel.TIER2_CONFIRM: 2,
    PermissionLevel.TIER3_APPROVE: 3,
    PermissionLevel.TIER4_WARN: 4,
    PermissionLevel.TIER5_SPAWN: 5,
}


def permission_tier_number(level: PermissionLevel | str) -> int:
    """Return the numeric tier for comparisons while preserving string enum values elsewhere."""
    normalized = (
        level.value if isinstance(level, PermissionLevel) else level.strip().lower()
    )
    for permission_level, tier_number in _PERMISSION_TIER_NUMBERS.items():
        if permission_level.value == normalized:
            return tier_number
    return _PERMISSION_TIER_NUMBERS[PermissionLevel.TIER3_APPROVE]
