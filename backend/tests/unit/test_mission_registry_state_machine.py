import pytest

from app.deepspace.missions.mission_registry import MissionRegistry


class _MemoryRegistry(MissionRegistry):
    def __init__(self) -> None:
        self.payload = {
            "mission_id": "m1",
            "status": "planning",
            "events": [],
            "mission_graph": {"nodes": [{"id": "n1", "status": "pending"}]},
        }

    def get_mission(self, mission_id: str):  # type: ignore[no-untyped-def]
        return self.payload if mission_id == "m1" else None

    def _write_payload(self, mission_id: str, payload):  # type: ignore[no-untyped-def]
        self.payload = payload

    def _write_heartbeat(self, **kwargs):  # type: ignore[no-untyped-def]
        return None


def test_invalid_mission_transition_is_rejected() -> None:
    registry = _MemoryRegistry()

    with pytest.raises(ValueError, match="Invalid mission transition"):
        registry.transition_mission("m1", "completed")


def test_event_append_is_idempotent_and_advances_node() -> None:
    registry = _MemoryRegistry()
    registry.transition_mission("m1", "ready")
    registry.transition_mission("m1", "running")

    first = registry.append_event(
        "m1",
        event_type="node_started",
        node_id="n1",
        node_status="ready",
        idempotency_key="k1",
    )
    second = registry.append_event(
        "m1",
        event_type="node_started",
        node_id="n1",
        node_status="ready",
        idempotency_key="k1",
    )

    assert first == second
    assert len(registry.payload["events"]) == 3
    assert registry.payload["mission_graph"]["nodes"][0]["status"] == "ready"


def test_completion_uses_validated_transition() -> None:
    registry = _MemoryRegistry()
    registry.transition_mission("m1", "ready")
    registry.transition_mission("m1", "running")

    registry.complete_mission(mission_id="m1", status="completed", summary="verified")

    assert registry.payload["status"] == "completed"
    assert registry.payload["completed_at"]


def test_failed_branch_is_invalidated_and_repair_node_is_created() -> None:
    registry = _MemoryRegistry()
    assert registry.invalidate_plan_branch("m1", node_id="n1", reason="test failed")
    repair_id = registry.create_repair_node(
        "m1", failed_node_id="n1", reason="repair the assertion"
    )

    assert repair_id is not None
    nodes = registry.payload["mission_graph"]["nodes"]
    assert nodes[0]["status"] == "failed"
    assert nodes[0]["invalidated"] is True
    assert any(node["id"] == repair_id and node["kind"] == "repair" for node in nodes)
