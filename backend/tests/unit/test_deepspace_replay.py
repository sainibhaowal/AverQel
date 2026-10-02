from __future__ import annotations

import json
from pathlib import Path

from app.deepspace.services.context_budget import AdaptiveContextBudget
from app.deepspace.services.execution_batches import plan_execution_batches
from app.deepspace.services.replay_trace import ReplayTraceValidationError, replay_trace

FIXTURES = Path(__file__).parents[1] / "fixtures" / "deepspace_replay"


def _load_fixture(name: str) -> dict:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert payload["fixture_version"] == 1
    assert payload["sensitive_data"] is False
    return payload


def test_long_research_fixture_replays_budget_and_reference_shape() -> None:
    fixture = _load_fixture("long_research_reference.json")
    budget = AdaptiveContextBudget().allocate(
        context_window=fixture["events"][0]["context_window"],
        system_tokens=2_000,
        tool_schema_tokens=1_000,
        user_tokens=200,
        prior_tool_result_tokens=100,
        reserved_output_tokens=2_000,
        workload=fixture["events"][0]["workload"],
    )

    assert budget.workload == "research"
    assert any(event["type"] == "tool_result_reference" for event in fixture["events"])


def test_mixed_batch_fixture_replays_ordering_barriers() -> None:
    fixture = _load_fixture("mixed_read_write_batch.json")
    calls = fixture["calls"]
    batches = plan_execution_batches(calls, is_read=lambda call: call["mode"] == "read")

    actual = [
        {"parallel": batch.parallel, "ids": [call["id"] for call in batch.calls]}
        for batch in batches
    ]
    assert actual == fixture["expected_batches"]


def test_replay_harness_replays_fixture_without_live_dependencies() -> None:
    assert replay_trace(_load_fixture("long_research_reference.json"))["status"] == "passed"
    assert replay_trace(_load_fixture("mixed_read_write_batch.json"))["status"] == "passed"
    lifecycle = replay_trace(_load_fixture("runtime_lifecycle.json"))
    assert lifecycle["status"] == "passed"
    assert lifecycle["checks"] == 10


def test_replay_harness_rejects_sensitive_fixture_fields() -> None:
    unsafe = {"fixture_version": 1, "sensitive_data": False, "case": "unsafe", "prompt": "x"}

    try:
        replay_trace(unsafe)
    except ReplayTraceValidationError as exc:
        assert "Forbidden sensitive" in str(exc)
    else:
        raise AssertionError("unsafe trace was accepted")


def test_replay_harness_rejects_events_after_terminal_outcome() -> None:
    unsafe = {
        "fixture_version": 1,
        "sensitive_data": False,
        "case": "terminal_order",
        "events": [
            {"type": "final", "status": "ready"},
            {"type": "final", "status": "ready"},
        ],
    }

    try:
        replay_trace(unsafe)
    except ReplayTraceValidationError as exc:
        assert "after final" in str(exc)
    else:
        raise AssertionError("events after final were accepted")
