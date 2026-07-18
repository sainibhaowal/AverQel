from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.core.auth import create_access_token
from app.core.config import get_settings
from app.models.deepspace.agent_activity import AgentActivity
from app.services.deepspace.memory.memory_service import TodoService
from app.services.query.answer_service import StreamEvent
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...]) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_orchestration_endpoint_returns_unified_mission_graph(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Tenant",
        "orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    todo_service = TodoService(db_session)
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Draft follow-up email",
        active_form="Draft follow-up email",
        status="pending",
        priority=80,
        is_recurring=True,
        enabled=True,
        automation_json={
            "action_type": "agent_prompt",
            "schedule_type": "daily",
            "prompt": "Draft the email and queue it for approval.",
            "web_search_enabled": True,
        },
    )
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Review connector health",
        active_form="Review connector health",
        status="in_progress",
        priority=70,
        metadata_json={"source": "connector"},
    )

    db_session.add(
        AgentActivity(
            id=uuid4(),
            tenant_id=seeded.tenant_id,
            activity_type="sync",
            description="Synced Gmail connector into the proactive workspace.",
            source="gmail",
            metadata_json={"connector_id": "gmail-1"},
        )
    )
    db_session.add(
        AgentActivity(
            id=uuid4(),
            tenant_id=seeded.tenant_id,
            activity_type="reason",
            description="Planned a multi-step tool path for a user request.",
            source="openchat",
            metadata_json={"phase": "planning"},
        )
    )
    db_session.commit()

    async def _fake_get_system_vitals(tenant_id):  # noqa: ARG001
        return {
            "internet": "connected",
            "llm": "connected",
            "web_search": "available",
            "sources": 5,
            "connector_statuses": {"active": 3, "error": 1},
            "proactive_daemon": {
                "enabled": True,
                "phase": "running",
                "timestamp": "2026-05-22T08:30:00Z",
                "interval_seconds": 300,
                "healthy": True,
            },
        }

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.orchestration_service.VitalsService.get_system_vitals",
        _fake_get_system_vitals,
    )

    class _FakeExecutor:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        @property
        def model_name(self):
            return "orchestration-test-model"

        @property
        def provider_type(self):
            return "test-provider"

        @property
        def reported_context_limit(self):
            return 128000

        @property
        def context_limit_source(self):
            return "runtime"

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.orchestration_service.AgentExecutor", _FakeExecutor
    )

    class _FakeRegistry:
        def __init__(self, settings=None):  # noqa: ARG002
            self.max_concurrency = 4

        def list_runs(self, **kwargs):  # noqa: ARG002
            return [
                {
                    "run_id": "run-1",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "parent_id": "",
                    "subagent_type": "research",
                    "prompt": "Research the market update.",
                    "status": "running",
                    "slot_index": 1,
                    "summary": "Collecting evidence from sources.",
                    "final_output": "",
                    "error": "",
                    "step_count": 4,
                    "duration_ms": 1000,
                    "last_tool_name": "web_search",
                    "last_tool_id": "tool-1",
                    "last_tool_output": "results",
                    "heartbeat_at": "2026-05-22T08:35:00Z",
                    "created_at": "2026-05-22T08:30:00Z",
                    "started_at": "2026-05-22T08:30:00Z",
                    "updated_at": "2026-05-22T08:35:00Z",
                    "completed_at": None,
                    "cancel_requested": False,
                    "last_event_type": "tool_result",
                    "last_event_message": "Working",
                },
                {
                    "run_id": "run-2",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "parent_id": "",
                    "subagent_type": "analyzer",
                    "prompt": "Analyze the sync gap.",
                    "status": "completed",
                    "slot_index": 2,
                    "summary": "Completed analysis.",
                    "final_output": "All clear.",
                    "error": "",
                    "step_count": 3,
                    "duration_ms": 900,
                    "last_tool_name": "read_file",
                    "last_tool_id": "tool-2",
                    "last_tool_output": "done",
                    "heartbeat_at": "2026-05-22T08:20:00Z",
                    "created_at": "2026-05-22T08:10:00Z",
                    "started_at": "2026-05-22T08:10:00Z",
                    "updated_at": "2026-05-22T08:20:00Z",
                    "completed_at": "2026-05-22T08:20:00Z",
                    "cancel_requested": False,
                    "last_event_type": "completed",
                    "last_event_message": "Complete",
                },
            ]

        def get_daemon_heartbeat(self):
            return {
                "phase": "running",
                "timestamp": "2026-05-22T08:30:00Z",
                "interval_seconds": 300,
            }

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.orchestration_service.SubagentRegistry", _FakeRegistry
    )

    response = client.get("/api/v1/deepspace/chats/orchestration", headers=headers)

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["tool_count"] >= 25
    assert payload["summary"]["active_subagents"] == 1
    assert payload["summary"]["active_tasks"] == 2
    assert payload["summary"]["daemon_healthy"] is True
    assert payload["tool_catalog"]["count"] == payload["summary"]["tool_count"]

    graph = payload["graph"]
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "open_chat" in node_ids
    assert "mission_router" in node_ids
    assert "tool_executor" in node_ids
    assert "subagent_swarm" in node_ids
    assert "proactive_workspace" in node_ids
    assert "connector_mesh" in node_ids
    assert "activity_stream" in node_ids
    assert len(graph["worlds"]) >= 5
    assert any(
        edge["source"] == "tool_executor" and edge["target"] == "mission_output"
        for edge in graph["edges"]
    )


def test_orchestration_stream_endpoint_emits_federated_mission_events(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Stream Tenant",
        "stream-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    monkeypatch.setattr(
        "app.api.v1.deepspace_chats.RateLimitService.enforce_query_user_limit",
        lambda *args, **kwargs: None,
    )

    class _FakeOrchestrator:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        async def stream_mission(
            self,
            *,
            objective,
            note_content=None,  # noqa: ARG002
            previous_messages=None,  # noqa: ARG002
            conversation_id=None,  # noqa: ARG002
            execution_mode="auto_review",  # noqa: ARG002
            mission_id=None,  # noqa: ARG002
        ):
            yield StreamEvent(
                event="mission_start",
                data={"mission_id": "mission-1", "objective": objective},
            )
            yield StreamEvent(
                event="mission_plan",
                data={
                    "mission_id": "mission-1",
                    "plan": {
                        "lanes": [{"lane_id": "main_chat", "lane_type": "main_chat"}]
                    },
                    "execution_mode": execution_mode,
                    "planner_source": "test",
                },
            )
            yield StreamEvent(
                event="mission_graph",
                data={
                    "mission_id": "mission-1",
                    "graph": {
                        "nodes": [{"id": "main_chat", "label": "AverQel Mission Core"}],
                        "edges": [],
                    },
                },
            )
            yield StreamEvent(
                event="lane_start",
                data={
                    "mission_id": "mission-1",
                    "lane_id": "main_chat",
                    "lane_type": "main_chat",
                    "title": "AverQel Mission Core",
                    "depends_on": [],
                },
            )
            yield StreamEvent(
                event="lane_result",
                data={
                    "mission_id": "mission-1",
                    "lane_id": "main_chat",
                    "lane_type": "main_chat",
                    "status": "completed",
                    "summary": "Answer synthesized.",
                    "output": "Answer synthesized.",
                },
            )
            yield StreamEvent(
                event="approval_request",
                data={
                    "mission_id": "mission-1",
                    "lane_id": "approval_1",
                    "lane_type": "approval",
                    "message": "Operator review required.",
                    "tool_name": "bash",
                    "tool_input": {"command": "deploy"},
                },
            )
            yield StreamEvent(
                event="mission_done",
                data={
                    "mission_id": "mission-1",
                    "status": "completed",
                    "summary": "Answer synthesized.",
                },
            )

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.master_orchestrator.MasterOrchestrator",
        _FakeOrchestrator,
    )

    response = client.post(
        "/api/v1/deepspace/chats/orchestrations/stream",
        headers=headers,
        json={"objective": "Research and synthesize the plan."},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: mission_start" in body
    assert "event: mission_plan" in body
    assert "event: mission_graph" in body
    assert "event: lane_start" in body
    assert "event: lane_result" in body
    assert "event: approval_request" in body
    assert "event: mission_done" in body
    assert '"execution_mode":"auto_review"' in body
    assert '"lane_type":"main_chat"' in body


def test_orchestration_stream_endpoint_emits_error_event_on_runtime_failure(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Stream Failure Tenant",
        "stream-failure-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    monkeypatch.setattr(
        "app.api.v1.deepspace_chats.RateLimitService.enforce_query_user_limit",
        lambda *args, **kwargs: None,
    )

    class _FailingOrchestrator:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        async def stream_mission(self, **kwargs):  # noqa: ARG002
            raise RuntimeError("planner unavailable")
            yield  # pragma: no cover

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.master_orchestrator.MasterOrchestrator",
        _FailingOrchestrator,
    )

    response = client.post(
        "/api/v1/deepspace/chats/orchestrations/stream",
        headers=headers,
        json={"objective": "Run a failing orchestration."},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: error" in body
    assert "ORCHESTRATION_STREAM_FAILURE" in body


def test_orchestration_stream_endpoint_emits_lane_failure_contract(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Lane Failure Tenant",
        "lane-failure-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    monkeypatch.setattr(
        "app.api.v1.deepspace_chats.RateLimitService.enforce_query_user_limit",
        lambda *args, **kwargs: None,
    )

    class _LaneFailureOrchestrator:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        async def stream_mission(self, **kwargs):  # noqa: ARG002
            yield StreamEvent(
                event="mission_start",
                data={"mission_id": "mission-2", "objective": kwargs.get("objective")},
            )
            yield StreamEvent(
                event="lane_error",
                data={
                    "mission_id": "mission-2",
                    "lane_id": "connector_lane",
                    "lane_type": "connector",
                    "error": "Connector handoff failed.",
                },
            )
            yield StreamEvent(
                event="lane_result",
                data={
                    "mission_id": "mission-2",
                    "lane_id": "connector_lane",
                    "lane_type": "connector",
                    "status": "failed",
                    "summary": "Connector handoff failed.",
                    "output": "",
                },
            )
            yield StreamEvent(
                event="mission_done",
                data={
                    "mission_id": "mission-2",
                    "status": "failed",
                    "summary": "Connector handoff failed.",
                },
            )

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.master_orchestrator.MasterOrchestrator",
        _LaneFailureOrchestrator,
    )

    response = client.post(
        "/api/v1/deepspace/chats/orchestrations/stream",
        headers=headers,
        json={"objective": "Run a failing lane orchestration."},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: mission_start" in body
    assert "event: lane_error" in body
    assert "event: lane_result" in body
    assert "event: mission_done" in body
    assert '"status":"failed"' in body


def test_orchestration_approval_endpoint_resolves_lane(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Approval Tenant",
        "approval-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    class _FakeRegistry:
        def __init__(self, settings=None, db=None):  # noqa: ARG002
            self.missions = {
                "mission-1": {
                    "mission_id": "mission-1",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "approval_queue": [
                        {"lane_id": "approval_1", "message": "Approve?"}
                    ],
                    "status": "awaiting_approval",
                }
            }

        def get_mission(self, mission_id):
            return self.missions.get(mission_id)

        def resolve_approval(self, mission_id, lane_id, approved):
            payload = self.missions[mission_id]
            payload["approval_queue"] = [
                item
                for item in payload.get("approval_queue") or []
                if str(item.get("lane_id") or "") != lane_id
            ]
            payload["status"] = "running" if approved else "declined"
            return payload

    monkeypatch.setattr(
        "app.services.deepspace.missions.mission_registry.MissionRegistry", _FakeRegistry
    )

    response = client.post(
        "/api/v1/deepspace/chats/orchestrations/missions/mission-1/approval",
        headers=headers,
        json={"lane_id": "approval_1", "approved": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["approval_queue"] == []


def test_orchestration_approval_endpoint_declines_lane(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Decline Tenant",
        "decline-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    class _FakeRegistry:
        def __init__(self, settings=None, db=None):  # noqa: ARG002
            self.missions = {
                "mission-2": {
                    "mission_id": "mission-2",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "approval_queue": [
                        {"lane_id": "approval_2", "message": "Approve?"}
                    ],
                    "status": "awaiting_approval",
                }
            }

        def get_mission(self, mission_id):
            return self.missions.get(mission_id)

        def resolve_approval(self, mission_id, lane_id, approved):
            payload = self.missions[mission_id]
            payload["approval_queue"] = [
                item
                for item in payload.get("approval_queue") or []
                if str(item.get("lane_id") or "") != lane_id
            ]
            payload["status"] = "running" if approved else "declined"
            return payload

    monkeypatch.setattr(
        "app.services.deepspace.missions.mission_registry.MissionRegistry", _FakeRegistry
    )

    response = client.post(
        "/api/v1/deepspace/chats/orchestrations/missions/mission-2/approval",
        headers=headers,
        json={"lane_id": "approval_2", "approved": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "declined"
    assert payload["approval_queue"] == []


def test_resume_stream_endpoint_emits_approved_tool_lifecycle(
    client,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Resume Stream Tenant",
        "resume-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    monkeypatch.setattr(
        "app.api.v1.deepspace_chats.RateLimitService.enforce_query_user_limit",
        lambda *args, **kwargs: None,
    )

    class _FakeService:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        async def resume_chat(
            self,
            *,
            auth,  # noqa: ARG002
            conversation_id,  # noqa: ARG002
            step_id,  # noqa: ARG002
            tool_id,  # noqa: ARG002
            approved,  # noqa: ARG002
            background_tasks,  # noqa: ARG002
        ):
            yield (
                "event: tool_start\n"
                'data: {"step_id":"step-1","tool_id":"tool-1","tool_name":"bash","tool_input":{"command":"echo hello"},"permission_level":"approved"}\n\n'
            )
            yield (
                "event: tool_result\n"
                'data: {"step_id":"step-1","tool_id":"tool-1","tool_name":"bash","tool_input":{"command":"echo hello"},"tool_output":"hello","success":true}\n\n'
            )
            yield 'event: done\ndata: {"completed":true}\n\n'

    monkeypatch.setattr("app.api.v1.deepspace_chats.DeepSpaceService", _FakeService)

    response = client.post(
        "/api/v1/deepspace/chats/resume",
        headers=headers,
        json={
            "conversation_id": str(uuid4()),
            "step_id": "step-1",
            "tool_id": "tool-1",
            "approved": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: tool_start" in body
    assert "event: tool_result" in body
    assert "event: done" in body


def test_orchestration_endpoint_filtering_by_conversation_id(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Orchestration Filter Tenant",
        "filter-orchestrator@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    target_conv_id = str(uuid4())
    other_conv_id = str(uuid4())

    todo_service = TodoService(db_session)
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Target Task",
        active_form="Target Task",
        status="pending",
        thread_id=target_conv_id,
    )
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Other Task",
        active_form="Other Task",
        status="pending",
        thread_id=other_conv_id,
    )

    db_session.add(
        AgentActivity(
            id=uuid4(),
            tenant_id=seeded.tenant_id,
            activity_type="reason",
            description="Target activity",
            source="openchat",
            metadata_json={"conversation_id": target_conv_id},
        )
    )
    db_session.add(
        AgentActivity(
            id=uuid4(),
            tenant_id=seeded.tenant_id,
            activity_type="reason",
            description="Other activity",
            source="openchat",
            metadata_json={"conversation_id": other_conv_id},
        )
    )
    db_session.commit()

    async def _fake_get_system_vitals(tenant_id):  # noqa: ARG001
        return {
            "internet": "connected",
            "llm": "connected",
            "web_search": "available",
            "sources": 0,
            "connector_statuses": {},
            "proactive_daemon": None,
        }

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.orchestration_service.VitalsService.get_system_vitals",
        _fake_get_system_vitals,
    )

    class _FakeExecutor:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        @property
        def model_name(self):
            return "test-model"

        @property
        def provider_type(self):
            return "test-provider"

        @property
        def reported_context_limit(self):
            return 128000

        @property
        def context_limit_source(self):
            return "runtime"

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.orchestration_service.AgentExecutor", _FakeExecutor
    )

    class _FakeRegistry:
        def __init__(self, settings=None):  # noqa: ARG002
            self.max_concurrency = 4

        def list_runs(self, **kwargs):  # noqa: ARG002
            return [
                {
                    "run_id": "run-target",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "parent_id": target_conv_id,
                    "subagent_type": "research",
                    "prompt": "Research target",
                    "status": "running",
                },
                {
                    "run_id": "run-other",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "parent_id": other_conv_id,
                    "subagent_type": "research",
                    "prompt": "Research other",
                    "status": "running",
                },
            ]

        def get_daemon_heartbeat(self):
            return None

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.orchestration_service.SubagentRegistry", _FakeRegistry
    )

    response = client.get(
        f"/api/v1/deepspace/chats/orchestration?conversation_id={target_conv_id}",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["active_subagents"] == 1
    assert payload["summary"]["active_tasks"] == 1
    assert payload["summary"]["recent_activities"] == 1

    assert payload["subagents"]["runs"][0]["run_id"] == "run-target"
    assert payload["tasks"]["all"][0]["content"] == "Target Task"
    assert payload["activities"][0]["description"] == "Target activity"
