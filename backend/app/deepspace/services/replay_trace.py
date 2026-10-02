"""Offline, fail-closed replay validation for sanitized DeepSpace traces."""

from __future__ import annotations

from typing import Any

from app.deepspace.services.context_budget import AdaptiveContextBudget
from app.deepspace.services.execution_batches import plan_execution_batches
from app.deepspace.services.runtime_transitions import RuntimePhase, transition_checkpoint


class ReplayTraceValidationError(ValueError):
    """A fixture is malformed or contains data unsafe for checked-in replay."""


_FORBIDDEN_KEY_PARTS = frozenset(
    {
        "prompt",
        "content",
        "response",
        "token",
        "secret",
        "password",
        "credential",
        "authorization",
        "cookie",
        "file_data",
        "tenant_id",
        "user_id",
    }
)


def _assert_safe_value(value: Any, *, path: str = "trace") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
                raise ReplayTraceValidationError(f"Forbidden sensitive trace field: {path}.{key}")
            _assert_safe_value(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_safe_value(nested, path=f"{path}[{index}]")
    elif isinstance(value, str) and len(value) > 512:
        raise ReplayTraceValidationError(f"Trace value is too large: {path}")


def validate_trace(trace: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(trace, dict) or trace.get("fixture_version") != 1:
        raise ReplayTraceValidationError("Trace must declare fixture_version=1")
    if trace.get("sensitive_data") is not False:
        raise ReplayTraceValidationError("Trace must explicitly declare sensitive_data=false")
    _assert_safe_value(trace)
    if not isinstance(trace.get("case"), str) or not trace["case"].strip():
        raise ReplayTraceValidationError("Trace case is required")
    return trace


def replay_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Replay deterministic runtime decisions without providers or storage."""

    trace = validate_trace(trace)
    events = trace.get("events", [])
    if not isinstance(events, list):
        raise ReplayTraceValidationError("Trace events must be a list")
    summary: dict[str, Any] = {"case": trace["case"], "checks": 0, "status": "passed"}
    previous_phase: RuntimePhase | None = None
    terminal_seen = False
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ReplayTraceValidationError("Every event requires a type")
        if terminal_seen:
            raise ReplayTraceValidationError("No events are allowed after final")
        if event["type"] == "model_round":
            required = ("context_window", "workload")
            if any(key not in event for key in required):
                raise ReplayTraceValidationError("model_round requires context_window and workload")
            budget = AdaptiveContextBudget().allocate(
                context_window=event["context_window"],
                system_tokens=1_000,
                tool_schema_tokens=500,
                user_tokens=100,
                prior_tool_result_tokens=0,
                reserved_output_tokens=1_000,
                workload=event["workload"],
            )
            if budget.workload != event["workload"]:
                raise ReplayTraceValidationError("workload normalization changed unexpectedly")
        elif event["type"] == "runtime_transition":
            try:
                next_phase = RuntimePhase(str(event["phase"]))
            except (KeyError, ValueError) as exc:
                raise ReplayTraceValidationError("runtime_transition has an invalid phase") from exc
            turn_index = event.get("turn_index", index)
            if not isinstance(turn_index, int):
                raise ReplayTraceValidationError("runtime_transition turn_index must be an integer")
            try:
                transition_checkpoint(
                    previous=previous_phase,
                    next_phase=next_phase,
                    turn_index=turn_index,
                )
            except ValueError as exc:
                raise ReplayTraceValidationError(str(exc)) from exc
            previous_phase = next_phase
        elif event["type"] == "approval":
            if event.get("status") not in {"requested", "approved", "denied", "expired"}:
                raise ReplayTraceValidationError("approval has an invalid status")
        elif event["type"] == "cancellation":
            if event.get("status") not in {"requested", "completed"}:
                raise ReplayTraceValidationError("cancellation has an invalid status")
        elif event["type"] in {"tool_result_reference", "tool_result_retrieval", "final"}:
            if not isinstance(event.get("status"), str):
                raise ReplayTraceValidationError(f"{event['type']} requires status")
            if event["type"] == "final":
                terminal_seen = True
        else:
            raise ReplayTraceValidationError(f"Unsupported replay event: {event['type']}")
        summary["checks"] += 1

    calls = trace.get("calls")
    expected_batches = trace.get("expected_batches")
    if calls is not None or expected_batches is not None:
        if not isinstance(calls, list) or not isinstance(expected_batches, list):
            raise ReplayTraceValidationError("Batch replay requires calls and expected_batches")
        batches = plan_execution_batches(calls, is_read=lambda call: call.get("mode") == "read")
        actual = [
            {"parallel": batch.parallel, "ids": [str(call.get("id")) for call in batch.calls]}
            for batch in batches
        ]
        if actual != expected_batches:
            raise ReplayTraceValidationError("Execution batch replay did not match expected order")
        summary["checks"] += 1
        summary["batch_count"] = len(actual)
    return summary
