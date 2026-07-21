from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from app.deepspace.execution.tool_contracts import ToolContract
from app.deepspace.workspace.workspace_mode import WorkspaceMode
from app.deepspace.workspace.workspace_policy import WorkspacePolicy

ExecutionMode = Literal["auto_review", "full_access"]


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    mode: ExecutionMode
    requires_human_approval: bool
    should_block: bool
    reason: str
    tool_contract: ToolContract | None = None


class ExecutionPolicy:
    """Translate mission execution mode + tool tier into a runtime decision."""

    _workspace_policy = WorkspacePolicy()

    @staticmethod
    def assess(
        *,
        mode: ExecutionMode,
        tool_name: str,
        tier: int,
        args: dict[str, Any] | None = None,
        workspace_mode: WorkspaceMode | None = None,
        tool_contract: ToolContract | None = None,
    ) -> ExecutionDecision:
        normalized_tier = max(1, int(tier or 1))
        active_workspace_mode = workspace_mode or WorkspaceMode()

        if tool_contract is not None:
            if tool_contract.tenant_scope not in {"tenant", "tenant_user", "auth_context"}:
                return ExecutionDecision(mode=mode, requires_human_approval=False, should_block=True, reason="Tool contract has no valid tenant scope.", tool_contract=tool_contract)
            if tool_contract.workspace_scope == "required" and not active_workspace_mode.enabled and tool_name in {"read_file", "write_file", "edit_file", "notebook_edit", "glob", "grep"}:
                return ExecutionDecision(mode=mode, requires_human_approval=False, should_block=True, reason="Tool contract requires an active workspace scope.", tool_contract=tool_contract)
            if tool_contract.approval_requirement == "block":
                return ExecutionDecision(mode=mode, requires_human_approval=False, should_block=True, reason=f"{tool_name} is blocked by its tool contract.", tool_contract=tool_contract)
            if tool_contract.approval_requirement == "human" and tool_contract.risk_class in {"internal_write", "external_side_effect", "destructive", "privileged", "untrusted", "ambiguous"}:
                return ExecutionDecision(mode=mode, requires_human_approval=True, should_block=False, reason=f"{tool_name} requires human approval because its contract is {tool_contract.risk_class}.", tool_contract=tool_contract)

        if (
            active_workspace_mode.enabled
            and ExecutionPolicy._workspace_policy.tool_is_scoped(tool_name)
        ):
            out_of_scope_paths = ExecutionPolicy._workspace_policy.out_of_scope_paths(
                workspace_mode=active_workspace_mode,
                tool_name=tool_name,
                args=args,
            )
            if out_of_scope_paths:
                blocked_paths = ", ".join(out_of_scope_paths[:3])
                return ExecutionDecision(
                    mode=mode,
                    requires_human_approval=False,
                    should_block=True,
                    reason=(
                        "Workspace-aware code mode blocked access outside the active "
                        f"workspace scope: {blocked_paths}"
                    ),
                    tool_contract=tool_contract,
                )

        # Check hybrid workspace rules for command tool execution
        if tool_name == "bash" and args:
            cmd = str(args.get("command") or "").strip().lower()

            # 1. Block package/dependency/extension installation commands
            install_patterns = [
                # Node package managers
                r"\bnpm\s+(?:install|i|add|update|upgrade)\b",
                r"\byarn\s+(?:add|install)\b",
                r"\bpnpm\s+(?:add|install)\b",
                # Python package manager
                r"\bpip\d*\s+install\b",
                r"\bpython\d*\s+-m\s+pip\s+install\b",
                # System package managers
                r"\b(?:apt|apt-get|yum|dnf|pacman|apk)\s+install\b",
                # Rust package manager
                r"\bcargo\s+(?:install|add)\b",
                # Go package manager
                r"\bgo\s+(?:get|install)\b",
                # Ruby package manager
                r"\bgem\s+install\b",
                # Extension installation
                r"\b(?:code|codium|cursor)\s+--install-extension\b",
            ]
            if any(re.search(pattern, cmd) for pattern in install_patterns):
                return ExecutionDecision(
                    mode=mode,
                    requires_human_approval=False,
                    should_block=True,
                    reason="Package, dependency, or extension installation commands are not allowed in this restricted hybrid workspace. You have no terminal shell for downloading extensions or packages.",
                    tool_contract=tool_contract,
                )

            # 2. Allow test runners in full_access mode, or require approval otherwise.
            test_runner_patterns = [
                r"\bpytest\b",
                r"\bpython\s+-m\s+pytest\b",
                r"\bpython\d*\s+-m\s+pytest\b",
                r"\bnpm\s+test\b",
                r"\bpnpm\s+test\b",
                r"\byarn\s+test\b",
                r"\bbun\s+test\b",
                r"\bpython\s+-m\s+unittest\b",
                r"\bpython\d*\s+-m\s+unittest\b",
            ]
            if any(re.search(pattern, cmd) for pattern in test_runner_patterns):
                if mode == "full_access":
                    return ExecutionDecision(
                        mode=mode,
                        requires_human_approval=False,
                        should_block=False,
                        reason="Test runner commands are allowed under full access.",
                        tool_contract=tool_contract,
                    )
                return ExecutionDecision(
                    mode=mode,
                    requires_human_approval=True,
                    should_block=False,
                    reason="Test runner commands require approval in auto review mode.",
                    tool_contract=tool_contract,
                )

            # 3. Allow script execution in full_access mode, or block otherwise
            execution_patterns = [
                r"\bpython\d*\s+\S+\.py\b",
                r"\bnode\s+\S+\.js\b",
                r"\bgo\s+run\b",
                r"\bgcc\b",
                r"\bg\+\+\b",
                r"\bclang\b",
                r"\bjavac\b",
                r"\bjava\s+-jar\b",
                r"\bjava\s+\S+\b",
                r"\brustc\b",
                r"\bsh\s+\S+\.sh\b",
                r"\bbash\s+\S+\.sh\b",
                r"\./\S+\.sh\b",
            ]
            if any(re.search(pattern, cmd) for pattern in execution_patterns):
                if mode == "full_access":
                    return ExecutionDecision(
                        mode=mode,
                        requires_human_approval=False,
                        should_block=False,
                        reason="Script execution and compilation are allowed under full access for verification and testing.",
                        tool_contract=tool_contract,
                    )
                return ExecutionDecision(
                    mode=mode,
                    requires_human_approval=False,
                    should_block=True,
                    reason="Compiling or running user code scripts is blocked in this restricted hybrid workspace. Please use standard filesystem tools or provide static content.",
                    tool_contract=tool_contract,
                )

        if mode == "full_access":
            if tool_name == "task":
                return ExecutionDecision(
                    mode=mode,
                    requires_human_approval=False,
                    should_block=False,
                    reason="Sub-agent spawning is allowed under full access.",
                    tool_contract=tool_contract,
                )
            if normalized_tier >= 4:
                return ExecutionDecision(
                    mode=mode,
                    requires_human_approval=False,
                    should_block=True,
                    reason=f"{tool_name} remains blocked because it is destructive.",
                    tool_contract=tool_contract,
                )
            return ExecutionDecision(
                mode=mode,
                requires_human_approval=False,
                should_block=False,
                reason=f"{tool_name} is allowed under full access.",
                tool_contract=tool_contract,
            )

        if normalized_tier >= 2:
            return ExecutionDecision(
                mode=mode,
                requires_human_approval=True,
                should_block=False,
                reason=f"{tool_name} requires approval in auto review mode.",
                tool_contract=tool_contract,
            )

        return ExecutionDecision(
            mode=mode,
            requires_human_approval=False,
            should_block=False,
            reason=f"{tool_name} is safe.",
            tool_contract=tool_contract,
        )
