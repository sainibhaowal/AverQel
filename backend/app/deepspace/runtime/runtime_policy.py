from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.deepspace.execution.tool_contracts import ToolContract
from app.deepspace.policy.execution_policy import (
    ExecutionDecision,
    ExecutionMode,
    ExecutionPolicy,
)
from app.deepspace.workspace.workspace_mode import WorkspaceMode

_MAX_RECENT_POLICY_DECISIONS = 24


@dataclass(slots=True)
class RuntimePolicy:
    """Thin execution policy wrapper reserved for runtime-layer extensions."""

    def assess_tool_call(
        self,
        *,
        mode: ExecutionMode,
        tool_name: str,
        tier: int,
        args: dict[str, Any] | None = None,
        workspace_mode: WorkspaceMode | None = None,
        context_state: dict[str, Any] | None = None,
        tool_contract: ToolContract | None = None,
    ) -> ExecutionDecision:
        decision = ExecutionPolicy.assess(
            mode=mode,
            tool_name=tool_name,
            tier=tier,
            args=args,
            workspace_mode=workspace_mode,
            tool_contract=tool_contract,
        )
        _record_policy_decision(
            context_state,
            tool_name=tool_name,
            tier=tier,
            mode=mode,
            args=args,
            workspace_mode=workspace_mode,
            decision=decision,
            tool_contract=tool_contract,
        )
        return decision


def summarize_runtime_policy_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("policy_diagnostics")
    if not isinstance(raw, dict):
        return {
            "counts": {"allow": 0, "approval": 0, "block": 0},
            "recent": [],
        }
    counts_value = raw.get("counts")
    recent_value = raw.get("recent")
    counts: dict[str, Any] = counts_value if isinstance(counts_value, dict) else {}
    recent: list[Any] = recent_value if isinstance(recent_value, list) else []
    return {
        "counts": {
            "allow": int(counts.get("allow") or 0),
            "approval": int(counts.get("approval") or 0),
            "block": int(counts.get("block") or 0),
        },
        "recent": [item for item in recent if isinstance(item, dict)][
            -_MAX_RECENT_POLICY_DECISIONS:
        ],
    }


def _record_policy_decision(
    state: dict[str, Any] | None,
    *,
    tool_name: str,
    tier: int,
    mode: ExecutionMode,
    args: dict[str, Any] | None,
    workspace_mode: WorkspaceMode | None,
    decision: ExecutionDecision,
    tool_contract: ToolContract | None,
) -> None:
    if not isinstance(state, dict):
        return
    diagnostics = state.setdefault("policy_diagnostics", {})
    if not isinstance(diagnostics, dict):
        return
    counts = diagnostics.setdefault("counts", {"allow": 0, "approval": 0, "block": 0})
    recent = diagnostics.setdefault("recent", [])
    classification = _classify_decision(decision)
    if isinstance(counts, dict):
        counts[classification] = int(counts.get(classification) or 0) + 1
    record = {
        "tool_name": tool_name,
        "tier": int(tier),
        "mode": str(mode),
        "decision": classification,
        "reason": str(decision.reason or ""),
        "workspace_scope": (
            workspace_mode.summary() if workspace_mode is not None else None
        ),
        "arg_keys": sorted(str(key) for key in (args or {}).keys() if str(key).strip()),
        "risk_class": tool_contract.risk_class if tool_contract else None,
        "capabilities": list(tool_contract.capabilities) if tool_contract else [],
        "approval_requirement": tool_contract.approval_requirement if tool_contract else None,
        "idempotency_support": tool_contract.idempotency_support if tool_contract else False,
        "compensation_required": tool_contract.compensation_required if tool_contract else False,
    }
    if isinstance(recent, list):
        recent.append(record)
        del recent[:-_MAX_RECENT_POLICY_DECISIONS]


def _classify_decision(decision: ExecutionDecision) -> str:
    if decision.should_block:
        return "block"
    if decision.requires_human_approval:
        return "approval"
    return "allow"
