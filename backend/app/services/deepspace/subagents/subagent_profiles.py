from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubagentProfile:
    requested_type: str
    canonical_type: str
    display_name: str
    allowed_tools: tuple[str, ...]
    goal: str
    output_contract: str
    thinking_enabled: bool = True
    web_search_enabled: bool = False


_PROFILE_SPECS: dict[str, dict[str, object]] = {
    "research": {
        "aliases": ("research", "researcher", "explorer"),
        "display_name": "Research Explorer",
        "allowed_tools": ("web_search", "web_fetch", "memory_search", "read_file", "view_file_paginated", "grep_search_limited", "directory_summary_tree", "task"),
        "goal": "Gather reliable evidence, compare sources, and reduce ambiguity.",
        "output_contract": (
            "Return findings, useful evidence, open questions, and a concise bottom line."
        ),
        "web_search_enabled": True,
    },
    "analysis": {
        "aliases": ("analysis", "analyzer"),
        "display_name": "Analysis Specialist",
        "allowed_tools": ("data_analyze", "memory_write", "read_file", "view_file_paginated", "grep_search_limited", "directory_summary_tree", "task"),
        "goal": "Interpret data, explain patterns, and turn raw material into conclusions.",
        "output_contract": (
            "Return key observations, reasoning summary, and the most important implications."
        ),
    },
    "writer": {
        "aliases": ("writer", "draft", "drafting"),
        "display_name": "Writer Specialist",
        "allowed_tools": ("write_file", "edit_file", "memory_read", "read_file", "view_file_paginated", "grep_search_limited", "directory_summary_tree", "task"),
        "goal": "Produce clean deliverables that preserve the user's requirements.",
        "output_contract": (
            "Return the deliverable summary, what was changed, and any follow-up risks."
        ),
    },
    "executor": {
        "aliases": ("executor", "execute", "ops"),
        "display_name": "Execution Specialist",
        "allowed_tools": ("bash", "bash_output"),
        "goal": "Run focused workspace actions and report exact execution outcomes.",
        "output_contract": (
            "Return what was executed, what succeeded or failed, and the next safe action."
        ),
    },
    "implementer": {
        "aliases": ("implementer", "coder", "developer"),
        "display_name": "Implementation Specialist",
        "allowed_tools": ("read_file", "write_file", "edit_file", "grep_search_limited", "directory_summary_tree"),
        "goal": "Make only the requested code changes inside the approved workspace scope.",
        "output_contract": "Return changed files, rationale, and risks; do not claim tests passed unless run.",
    },
    "tester": {
        "aliases": ("tester", "test", "verification", "verifier"),
        "display_name": "Verification Specialist",
        "allowed_tools": ("read_file", "bash", "bash_output", "grep_search_limited"),
        "goal": "Run declared tests and checks without editing the worktree.",
        "output_contract": "Return exact commands, exit status, failures, and reproducible evidence.",
    },
    "reviewer": {
        "aliases": ("reviewer", "review", "security_review"),
        "display_name": "Diff Review Specialist",
        "allowed_tools": ("read_file", "bash", "grep_search_limited", "directory_summary_tree"),
        "goal": "Inspect the diff for correctness, security, regressions, and scope violations without editing.",
        "output_contract": "Return review findings, approval or rejection, and remaining risks.",
    },
    "repair": {
        "aliases": ("repair", "repairer", "fixer"),
        "display_name": "Repair Specialist",
        "allowed_tools": ("read_file", "write_file", "edit_file", "bash", "bash_output", "grep_search_limited"),
        "goal": "Fix one identified failure, then run the smallest relevant verification.",
        "output_contract": "Return the failed evidence addressed, changed files, and verification result.",
    },
    "release": {
        "aliases": ("release", "publisher", "pr"),
        "display_name": "Release Specialist",
        "allowed_tools": ("read_file", "bash", "git_diff", "git_status"),
        "goal": "Prepare a patch or release only after verification and review evidence pass.",
        "output_contract": "Return patch or commit identity, review summary, and remaining risks.",
    },
    "planner": {
        "aliases": ("planner", "plan"),
        "display_name": "Planning Specialist",
        "allowed_tools": ("read_file", "glob", "grep", "memory_search", "view_file_paginated", "grep_search_limited", "directory_summary_tree", "task"),
        "goal": "Break the task into an accurate, dependency-aware execution plan.",
        "output_contract": (
            "Return phases, dependencies, risks, and the recommended execution sequence."
        ),
    },
    "file": {
        "aliases": ("file", "files", "workspace"),
        "display_name": "Workspace Explorer",
        "allowed_tools": ("read_file", "glob", "grep", "view_file_paginated", "grep_search_limited", "directory_summary_tree"),
        "goal": "Inspect the workspace carefully and gather the most relevant code context.",
        "output_contract": (
            "Return the relevant files, findings, and why they matter to the task."
        ),
    },
    "support": {
        "aliases": ("support", "ops_support"),
        "display_name": "Support Specialist",
        "allowed_tools": ("read_file", "memory_search"),
        "goal": "Gather operational support signals without changing system behavior.",
        "output_contract": (
            "Return the current support findings, health signals, and any obvious risks."
        ),
    },
    "general-purpose": {
        "aliases": ("general-purpose", "general", "default"),
        "display_name": "General Specialist",
        "allowed_tools": ("read_file", "view_file_paginated"),
        "goal": "Handle a focused delegated task safely with minimal workspace impact.",
        "output_contract": (
            "Return the most important result, evidence, and any unresolved blocker."
        ),
    },
}


_ALIASES: dict[str, str] = {}
for canonical_type, payload in _PROFILE_SPECS.items():
    aliases = tuple(str(alias).strip().lower() for alias in payload["aliases"])
    for alias in aliases:
        _ALIASES[alias] = canonical_type


def resolve_subagent_profile(stype: str | None) -> SubagentProfile:
    requested_type = str(stype or "general-purpose").strip() or "general-purpose"
    requested_key = requested_type.lower()
    canonical_type = _ALIASES.get(requested_key, "general-purpose")
    payload = _PROFILE_SPECS[canonical_type]
    return SubagentProfile(
        requested_type=requested_type,
        canonical_type=canonical_type,
        display_name=str(payload["display_name"]),
        allowed_tools=tuple(str(tool) for tool in payload["allowed_tools"]),
        goal=str(payload["goal"]),
        output_contract=str(payload["output_contract"]),
        thinking_enabled=bool(payload.get("thinking_enabled", True)),
        web_search_enabled=bool(payload.get("web_search_enabled", False)),
    )
