"""Safe execution batches for model-requested DeepSpace tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionBatch:
    calls: tuple[dict[str, Any], ...]
    parallel: bool


def plan_execution_batches(
    calls: list[dict[str, Any]], *, is_read: Callable[[dict[str, Any]], bool]
) -> list[ExecutionBatch]:
    """Make contiguous reads parallel, with each non-read as an ordering barrier."""

    batches: list[ExecutionBatch] = []
    pending_reads: list[dict[str, Any]] = []
    for call in calls:
        if is_read(call):
            pending_reads.append(call)
            continue
        if pending_reads:
            batches.append(ExecutionBatch(tuple(pending_reads), parallel=True))
            pending_reads = []
        batches.append(ExecutionBatch((call,), parallel=False))
    if pending_reads:
        batches.append(ExecutionBatch(tuple(pending_reads), parallel=True))
    return batches
