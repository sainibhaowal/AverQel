"""Explicit, validated durable DeepSpace runtime phase transitions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class RuntimePhase(StrEnum):
    CONTEXT_ASSEMBLED = "context_assembled"
    MODEL_REQUESTED = "model_requested"
    ACTIONS_VALIDATED = "actions_validated"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    RESULTS_RECORDED = "results_recorded"
    FINALIZING = "finalizing"


_ALLOWED: dict[RuntimePhase, frozenset[RuntimePhase]] = {
    RuntimePhase.CONTEXT_ASSEMBLED: frozenset({RuntimePhase.MODEL_REQUESTED}),
    RuntimePhase.MODEL_REQUESTED: frozenset(
        {RuntimePhase.ACTIONS_VALIDATED, RuntimePhase.FINALIZING}
    ),
    RuntimePhase.ACTIONS_VALIDATED: frozenset(
        {RuntimePhase.AWAITING_APPROVAL, RuntimePhase.EXECUTING, RuntimePhase.FINALIZING}
    ),
    RuntimePhase.AWAITING_APPROVAL: frozenset({RuntimePhase.EXECUTING, RuntimePhase.FINALIZING}),
    RuntimePhase.EXECUTING: frozenset({RuntimePhase.RESULTS_RECORDED, RuntimePhase.FINALIZING}),
    RuntimePhase.RESULTS_RECORDED: frozenset(
        {RuntimePhase.MODEL_REQUESTED, RuntimePhase.FINALIZING}
    ),
    RuntimePhase.FINALIZING: frozenset(),
}


def transition_checkpoint(
    *,
    previous: RuntimePhase | None,
    next_phase: RuntimePhase,
    turn_index: int,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a sanitized checkpoint fragment or reject an illegal transition."""

    if previous is not None and next_phase not in _ALLOWED[previous]:
        raise ValueError(f"Illegal DeepSpace runtime transition: {previous} -> {next_phase}")
    checkpoint: dict[str, Any] = {"phase": str(next_phase), "turn_index": max(0, turn_index)}
    if details:
        checkpoint["transition"] = {
            key: value
            for key, value in details.items()
            if key
            in {
                "tool_count",
                "batch_count",
                "schema_digest",
                "history_budget_tokens",
                "tool_result_budget_tokens",
            }
        }
    return checkpoint
