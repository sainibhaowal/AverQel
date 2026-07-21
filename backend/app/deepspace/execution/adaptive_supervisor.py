"""Durable, adaptive control for long-running agent executions.

The supervisor deliberately does not encode a fixed number of model turns.  A
run ends when the model has satisfied the goal, the runtime observes a safety
condition, the caller cancels it, or the configurable mission budget is
exhausted.  Mission-level callers can start another run from the checkpoint.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AdaptiveExecutionSupervisor:
    """Decide whether an executor may take another turn and persist progress."""

    mission_id: str | None = None
    max_turns: int | None = None
    max_seconds: float | None = None
    stagnation_limit: int = 4
    checkpoint: Callable[[dict[str, Any]], None] | None = None
    started_at: float = field(default_factory=time.monotonic)
    turns: int = 0
    progress_events: int = 0
    repeated_actions: int = 0
    last_signature: str | None = None
    stop_reason: str | None = None

    def observe(self, *, turn: int, signature: str = "", progress: bool = False, **state: Any) -> None:
        self.turns = max(self.turns, int(turn))
        if progress:
            self.progress_events += 1
        if signature and signature == self.last_signature:
            self.repeated_actions += 1
        elif signature:
            self.repeated_actions = 0
        if signature:
            self.last_signature = signature
        payload = {
            "turn": self.turns,
            "progress_events": self.progress_events,
            "repeated_actions": self.repeated_actions,
            "elapsed_seconds": round(time.monotonic() - self.started_at, 3),
            **state,
        }
        if self.checkpoint:
            self.checkpoint(payload)

    def can_continue(self, *, cancelled: bool = False) -> bool:
        if cancelled:
            self.stop_reason = "cancelled"
            return False
        if self.max_turns is not None and self.turns >= self.max_turns:
            self.stop_reason = "mission_turn_budget_exhausted"
            return False
        if self.max_seconds is not None and time.monotonic() - self.started_at >= self.max_seconds:
            self.stop_reason = "mission_time_budget_exhausted"
            return False
        if self.repeated_actions >= max(1, self.stagnation_limit):
            self.stop_reason = "stagnation_detected"
            return False
        return True
