"""Provider-neutral, conservative per-round context budgeting for DeepSpace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RoundBudget:
    context_window: int | None
    system_tokens: int
    tool_schema_tokens: int
    user_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    available_dynamic_tokens: int | None
    history_budget_tokens: int | None
    tool_result_budget_tokens: int | None
    mcp_preview_chars: int
    workload: str


class AdaptiveContextBudget:
    """Allocate only optional context after protected request material.

    This is intentionally a deterministic controller.  It has no cross-user
    learning state and never decides authorization, tool availability, or
    output limits.  A provider without a verified context window keeps the
    existing result preview ceiling rather than relying on a guessed window.
    """

    MIN_MCP_PREVIEW_CHARS = 500
    DEFAULT_MCP_PREVIEW_CHARS = 1_800
    MAX_MCP_PREVIEW_CHARS = 12_000

    def __init__(self, *, safety_margin_tokens: int = 512) -> None:
        self.safety_margin_tokens = max(128, min(int(safety_margin_tokens), 4_096))

    def allocate(
        self,
        *,
        context_window: int | None,
        system_tokens: int,
        tool_schema_tokens: int,
        user_tokens: int,
        prior_tool_result_tokens: int,
        reserved_output_tokens: int,
        workload: Literal["balanced", "conversation", "research", "coding"] = "balanced",
    ) -> RoundBudget:
        protected = (
            max(0, system_tokens)
            + max(0, tool_schema_tokens)
            + max(0, user_tokens)
            + max(0, reserved_output_tokens)
            + self.safety_margin_tokens
        )
        if context_window is None or context_window <= 0:
            return RoundBudget(
                context_window=None,
                system_tokens=max(0, system_tokens),
                tool_schema_tokens=max(0, tool_schema_tokens),
                user_tokens=max(0, user_tokens),
                reserved_output_tokens=max(0, reserved_output_tokens),
                safety_margin_tokens=self.safety_margin_tokens,
                available_dynamic_tokens=None,
                history_budget_tokens=None,
                tool_result_budget_tokens=None,
                mcp_preview_chars=self.DEFAULT_MCP_PREVIEW_CHARS,
                workload=workload,
            )

        available = max(0, int(context_window) - protected)
        # Retain more result capacity after evidence-heavy rounds while always
        # reserving a meaningful history share. These are allocation targets,
        # not permission to exceed the existing hard context fit.
        normalized_workload = (
            workload
            if workload in {"balanced", "conversation", "research", "coding"}
            else "balanced"
        )
        if normalized_workload == "research":
            result_ratio = 0.65
        elif normalized_workload == "conversation":
            result_ratio = 0.35
        elif normalized_workload == "coding":
            result_ratio = 0.55
        else:
            result_ratio = 0.60 if prior_tool_result_tokens > max(1, available // 4) else 0.45
        tool_results = int(available * result_ratio)
        history = max(0, available - tool_results)
        # One half of the result pool is available to an individual MCP
        # preview, bounded by the broker's existing max-result controls.
        preview = max(self.MIN_MCP_PREVIEW_CHARS, (tool_results * 4) // 2)
        preview = min(self.MAX_MCP_PREVIEW_CHARS, preview)
        return RoundBudget(
            context_window=int(context_window),
            system_tokens=max(0, system_tokens),
            tool_schema_tokens=max(0, tool_schema_tokens),
            user_tokens=max(0, user_tokens),
            reserved_output_tokens=max(0, reserved_output_tokens),
            safety_margin_tokens=self.safety_margin_tokens,
            available_dynamic_tokens=available,
            history_budget_tokens=history,
            tool_result_budget_tokens=tool_results,
            mcp_preview_chars=preview,
            workload=normalized_workload,
        )
