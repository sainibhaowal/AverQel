from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.auth.dependencies import AuthContext
from app.deepspace.execution.agent_tools import ToolResult
from app.deepspace.orchestration.master_orchestrator import MasterOrchestrator


class _FakeRegistry:
    def __init__(self, settings=None, db=None):  # noqa: ARG002
        self.missions: dict[str, dict[str, object]] = {}
        self.approvals: list[dict[str, object]] = []

    def register_mission(
        self,
        *,
        mission_id,
        tenant_id,
        user_id,
        objective,
        plan,
        parent_id=None,
        status="planning",
        execution_mode="auto_review",
    ):  # noqa: ARG002
        payload = {
            "mission_id": mission_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "objective": objective,
            "plan": plan,
            "status": status,
            "execution_mode": execution_mode,
            "lane_states": plan.get("lanes", []),
            "lane_results": [],
            "approval_queue": list(plan.get("approval_queue") or []),
        }
        self.missions[mission_id] = payload
        return payload

    def touch_mission(self, mission_id, **updates):
        self.missions.setdefault(mission_id, {}).update(updates)

    def update_lane(self, mission_id, lane_id, **updates):
        payload = self.missions.setdefault(mission_id, {"lane_states": []})
        lanes = list(payload.get("lane_states") or [])
        found = False
        for lane in lanes:
            if lane.get("lane_id") == lane_id:
                lane.update(updates)
                found = True
                break
        if not found:
            lanes.append({"lane_id": lane_id, **updates})
        payload["lane_states"] = lanes

    def append_lane_result(self, mission_id, result):
        self.missions.setdefault(mission_id, {}).setdefault("lane_results", []).append(
            result
        )

    def request_approval(self, mission_id, data):
        self.approvals.append(data)
        payload = self.missions.setdefault(mission_id, {})
        payload.setdefault("approval_queue", []).append(data)
        payload["status"] = "awaiting_approval"

    def complete_mission(
        self,
        *,
        mission_id,
        status,
        summary=None,
        final_output=None,
        error=None,
        duration_ms=None,
    ):  # noqa: ARG002
        payload = self.missions.setdefault(mission_id, {})
        payload["status"] = status
        payload["summary"] = summary
        payload["final_output"] = final_output
        payload["duration_ms"] = duration_ms
        return payload

    def get_mission(self, mission_id):
        return self.missions.get(mission_id)

    def is_cancel_requested(self, mission_id):  # noqa: ARG002
        return False

    def get_planner_mode(
        self, *, tenant_id, user_id, conversation_id=None  # noqa: ARG002
    ):
        return "structured"

    def get_subagent_profile(
        self, *, tenant_id, user_id, conversation_id=None  # noqa: ARG002
    ):
        return "analysis"

    def get_runtime_hooks_enabled(
        self, *, tenant_id, user_id, conversation_id=None  # noqa: ARG002
    ):
        return True

    def get_workspace_mode_enabled(
        self, *, tenant_id, user_id, conversation_id=None  # noqa: ARG002
    ):
        return True


class _CancellingRegistry(_FakeRegistry):
    def append_lane_result(self, mission_id, result):
        super().append_lane_result(mission_id, result)
        payload = self.missions.setdefault(mission_id, {})
        if len(payload.get("lane_results") or []) >= 1:
            payload["cancel_requested"] = True

    def is_cancel_requested(self, mission_id):  # noqa: ARG002
        payload = self.missions.get(mission_id) or {}
        return bool(payload.get("cancel_requested"))


class _FakeAgentExecutor:
    def __init__(self, **kwargs):  # noqa: ARG002
        self.execution_mode = kwargs.get("execution_mode", "auto_review")
        self._runtime_diagnostics = {
            "tool_density": {
                "started": 2,
                "completed": 2,
                "failed": 0,
                "blocked": 0,
                "awaiting_approval": 0,
            },
            "hooks": {
                "active": True,
                "counts": {"pre_tool": 1, "post_tool": 1},
                "recent": [
                    {
                        "phase": "pre_tool",
                        "hook": "test_hook",
                        "status": "applied",
                        "changed_fields": ["tool_input"],
                    }
                ],
            },
            "policy": {
                "counts": {"allow": 2, "approval": 0, "block": 0},
                "recent": [
                    {
                        "tool_name": "read_file",
                        "decision": "allow",
                        "reason": "",
                    }
                ],
            },
            "memory": {
                "recent": [
                    {
                        "kind": "persistent_memory_bootstrap",
                        "count": 3,
                        "fast_bootstrap": False,
                    }
                ],
            },
            "compaction": {
                "recent": [
                    {
                        "trigger": "automatic",
                        "saved_tokens": 1200,
                    }
                ],
                "latest": {
                    "trigger": "automatic",
                    "saved_tokens": 1200,
                },
            },
        }

    @property
    def model_name(self):
        return "orchestrator-test-model"

    @property
    def provider_type(self):
        return "test-provider"

    @property
    def base_url(self):
        return "http://localhost"

    @property
    def api_key(self):
        return "test-key"

    @property
    def llm(self):
        class _LLM:
            def generate(self, request):  # noqa: ARG002
                return SimpleNamespace(content="Synthesized mission answer.")

        return _LLM()

    @property
    def runtime_diagnostics(self):
        return dict(self._runtime_diagnostics)

    @property
    def last_compaction_state(self):
        return {"trigger": "automatic", "saved_tokens": 1200}

    async def run(self, **kwargs):  # noqa: ARG002
        yield SimpleNamespace(type="agent_plan", data={"plan": "plan"})
        yield SimpleNamespace(type="answer_delta", data={"text": "Main answer. "})
        yield SimpleNamespace(type="step_summary", data={"message": "Working."})
        yield SimpleNamespace(
            type="final_answer", data={"content": "Main answer complete."}
        )


class _FakeSubagentManager:
    last_parent_id = None

    def __init__(self, *args, **kwargs):  # noqa: ARG002
        pass

    async def spawn_and_execute(
        self,
        subagent_type,
        prompt,
        parent_id,
        execution_mode="auto_review",
        conversation_id=None,
    ):  # noqa: ARG002
        _FakeSubagentManager.last_parent_id = parent_id
        return ToolResult(
            success=True,
            output=f"{subagent_type.upper()} lane finished for {prompt}",
            data={
                "subagent_type": subagent_type,
                "requested_subagent_type": subagent_type,
                "resolved_subagent_type": subagent_type,
                "parent_id": str(parent_id),
                "execution_mode": execution_mode,
                "conversation_id": (
                    str(conversation_id) if conversation_id is not None else None
                ),
            },
        )


class _PlannerJsonAgentExecutor(_FakeAgentExecutor):
    @property
    def llm(self):
        class _LLM:
            def generate(self, request):  # noqa: ARG002
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "planner_source": "model",
                            "summary": "Model-authored mission plan.",
                            "parallel_limit": 3,
                            "signals": {
                                "research": False,
                                "analysis": False,
                                "writer": True,
                                "executor": False,
                                "memory": False,
                                "proactive": False,
                                "approval": False,
                                "connector": False,
                            },
                            "approval_queue": [],
                            "lane_blueprints": [
                                {
                                    "ref": "main_chat",
                                    "lane_type": "main_chat",
                                    "title": "AverQel Mission Core",
                                    "prompt": "Draft the report.",
                                    "priority": 100,
                                    "depends_on": [],
                                    "blocked_by": [],
                                    "subagent_type": None,
                                    "metadata": {"role": "primary"},
                                },
                                {
                                    "ref": "writer_final",
                                    "lane_type": "writer",
                                    "title": "Writer Swarm",
                                    "prompt": "Draft a crisp final deliverable for the report.",
                                    "priority": 70,
                                    "depends_on": ["main_chat"],
                                    "blocked_by": [],
                                    "subagent_type": "writer",
                                    "metadata": {"role": "writer"},
                                },
                            ],
                        }
                    )
                )

        return _LLM()


class _FakeSupportDb:
    def __init__(self, rows):
        self.rows = rows
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, stmt):  # noqa: ARG002
        return SimpleNamespace(all=lambda: self.rows)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


async def _noop_async(*args, **kwargs):  # noqa: ARG001
    return None


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_runs_parallel_lanes_and_synthesizes(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _FakeAgentExecutor
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Research and analyze the migration, remember the result, and create a proactive follow-up.",
        note_content="Workspace note.",
        conversation_id=uuid4(),
    ):
        chunks.append(event)

    event_names = [event.event for event in chunks]
    assert "mission_start" in event_names
    assert "mission_planning" in event_names
    assert "mission_plan" in event_names
    assert "lane_start" in event_names
    assert "lane_result" in event_names
    assert "mission_summary" in event_names
    assert "mission_done" in event_names
    assert any(
        event.event == "lane_result" and event.data.get("lane_type") == "research"
        for event in chunks
    )
    assert any(
        event.event == "lane_result" and event.data.get("lane_type") == "analysis"
        for event in chunks
    )
    assert any(
        event.event == "lane_result" and event.data.get("lane_type") == "memory"
        for event in chunks
    )
    assert any(
        event.event == "lane_result" and event.data.get("lane_type") == "proactive"
        for event in chunks
    )
    assert any(
        event.event == "mission_done" and event.data.get("status") == "completed"
        for event in chunks
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_stops_launching_lanes_after_cancellation(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry",
        _CancellingRegistry,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _FakeAgentExecutor
    )

    class _FailOnSpawnSubagentManager(_FakeSubagentManager):
        async def spawn_and_execute(self, *args, **kwargs):  # noqa: ARG002
            raise AssertionError("subagent lanes should not start after cancellation")

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FailOnSpawnSubagentManager,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    async def _canceling_plan(*args, **kwargs):  # noqa: ARG001
        return {
            "planner_source": "test",
            "summary": "Cancellation test mission.",
            "parallel_limit": 2,
            "signals": {
                "research": True,
                "analysis": False,
                "writer": False,
                "executor": False,
                "memory": False,
                "proactive": False,
                "approval": False,
                "connector": False,
            },
            "approval_queue": [],
            "lanes": [
                {
                    "lane_id": "main_chat",
                    "lane_type": "main_chat",
                    "title": "Main Chat",
                    "prompt": "Answer the question.",
                    "priority": 100,
                    "depends_on": [],
                    "blocked_by": [],
                    "metadata": {},
                },
                {
                    "lane_id": "research_lane",
                    "lane_type": "research",
                    "title": "Research Lane",
                    "prompt": "Do extra research.",
                    "priority": 50,
                    "depends_on": ["main_chat"],
                    "blocked_by": [],
                    "subagent_type": "research",
                    "metadata": {},
                },
            ],
            "graph": {
                "nodes": [
                    {"id": "main_chat", "label": "Main Chat"},
                    {"id": "research_lane", "label": "Research Lane"},
                ],
                "edges": [{"from": "main_chat", "to": "research_lane"}],
            },
        }

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionPlanner.build_plan",
        _canceling_plan,
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Cancel once the first lane completes.",
        conversation_id=uuid4(),
    ):
        chunks.append(event)

    assert any(
        event.event == "mission_done" and event.data.get("status") == "cancelled"
        for event in chunks
    )
    assert any(
        event.event == "mission_summary" and event.data.get("status") == "cancelled"
        for event in chunks
    )
    assert not any(
        event.event == "lane_result" and event.data.get("lane_type") == "research"
        for event in chunks
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_uses_mission_id_as_subagent_parent_when_no_conversation(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _FakeAgentExecutor
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    _FakeSubagentManager.last_parent_id = None
    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Research and analyze the migration.",
        note_content="Workspace note.",
        conversation_id=None,
    ):
        chunks.append(event)

    mission_id = next(
        event.data["mission_id"] for event in chunks if event.event == "mission_start"
    )
    assert _FakeSubagentManager.last_parent_id is not None
    assert str(_FakeSubagentManager.last_parent_id) == mission_id


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_uses_model_authored_planner_json(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor",
        _PlannerJsonAgentExecutor,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Draft the report and prepare a final summary.",
        conversation_id=uuid4(),
    ):
        chunks.append(event)

    assert any(
        event.event == "mission_plan" and event.data.get("planner_source") == "model"
        for event in chunks
    )
    assert any(
        event.event == "mission_plan"
        and isinstance(event.data.get("runtime_state"), dict)
        and event.data["runtime_state"].get("planner_validation_status") == "validated"
        and event.data["runtime_state"].get("subagent_profile") == "analysis"
        for event in chunks
    )
    assert any(
        event.event == "lane_result" and event.data.get("lane_type") == "writer"
        for event in chunks
    )
    writer_result = next(
        event
        for event in chunks
        if event.event == "lane_result" and event.data.get("lane_type") == "writer"
    )
    assert writer_result.data["metadata"]["requested_subagent_type"] == "writer"
    assert (
        writer_result.data["metadata"]["lane_lifecycle_summary"]["status"]
        == "completed"
    )

    mission_done = next(event for event in chunks if event.event == "mission_done")
    assert (
        mission_done.data["runtime_state"]["diagnostics"]["planner"]["lane_count"] >= 1
    )
    assert (
        mission_done.data["runtime_state"]["diagnostics"]["policy"]["counts"]["allow"]
        >= 0
    )
    assert any(
        event.event == "mission_done" and event.data.get("status") == "completed"
        for event in chunks
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_pauses_on_approval_request(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )

    class _ApprovalAgent(_FakeAgentExecutor):
        async def run(self, **kwargs):  # noqa: ARG002
            if self.execution_mode == "full_access":
                yield SimpleNamespace(
                    type="final_answer", data={"content": "Handled directly."}
                )
                return
            yield SimpleNamespace(
                type="permission_request",
                data={
                    "tool_name": "delete_file",
                    "tool_input": {"path": "danger.txt"},
                    "message": "Approval required for delete_file.",
                },
            )

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _ApprovalAgent
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Delete the stale artifact and summarize the fallout.",
        conversation_id=uuid4(),
    ):
        chunks.append(event)

    assert any(event.event == "approval_request" for event in chunks)
    assert any(
        event.event == "mission_done"
        and event.data.get("status") == "awaiting_approval"
        for event in chunks
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_reports_declined_approval(
    monkeypatch,
    db_session,
) -> None:
    class _DecliningRegistry(_FakeRegistry):
        def request_approval(self, mission_id, data):
            super().request_approval(mission_id, data)
            payload = self.missions.setdefault(mission_id, {})
            payload["approval_queue"] = []
            payload["status"] = "declined"

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry",
        _DecliningRegistry,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )

    class _ApprovalAgent(_FakeAgentExecutor):
        async def run(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(
                type="permission_request",
                data={
                    "tool_name": "delete_file",
                    "tool_input": {"path": "danger.txt"},
                    "message": "Approval required for delete_file.",
                },
            )

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _ApprovalAgent
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    async def _fake_build_plan(*args, **kwargs):  # noqa: ARG001
        return {
            "planner_source": "test",
            "summary": "Approval-gated mission plan.",
            "parallel_limit": 2,
            "signals": {"approval": True},
            "approval_queue": [{"lane_id": "approval_1", "message": "Approve?"}],
            "lanes": [
                {
                    "lane_id": "approval_1",
                    "lane_type": "approval",
                    "title": "Approval Gate",
                    "prompt": "Approve the risky action.",
                    "priority": 100,
                    "depends_on": [],
                    "blocked_by": [],
                    "metadata": {},
                },
                {
                    "lane_id": "followup_1",
                    "lane_type": "analysis",
                    "title": "Follow-up Analysis",
                    "prompt": "Prepare a follow-up once approval is resolved.",
                    "priority": 10,
                    "depends_on": ["approval_1"],
                    "blocked_by": [],
                    "metadata": {},
                },
            ],
            "graph": {
                "nodes": [
                    {"id": "approval_1", "label": "Approval Gate"},
                    {"id": "followup_1", "label": "Follow-up Analysis"},
                ],
                "edges": [{"from": "approval_1", "to": "followup_1"}],
            },
        }

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionPlanner.build_plan",
        _fake_build_plan,
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Delete the stale artifact and summarize the fallout.",
        conversation_id=uuid4(),
    ):
        chunks.append(event)

    assert any(event.event == "approval_request" for event in chunks)
    assert any(
        event.event == "mission_done" and event.data.get("status") == "declined"
        for event in chunks
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_full_access_skips_approval_pause(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )

    class _ApprovalAwareAgent(_FakeAgentExecutor):
        async def run(self, **kwargs):  # noqa: ARG002
            if self.execution_mode == "full_access":
                yield SimpleNamespace(
                    type="final_answer", data={"content": "Handled directly."}
                )
                return
            yield SimpleNamespace(
                type="permission_request",
                data={"tool_name": "bash", "tool_input": {"command": "echo hi"}},
            )

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _ApprovalAwareAgent
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-1",
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=db_session,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Delete the stale artifact and summarize the fallout.",
        conversation_id=uuid4(),
        execution_mode="full_access",
    ):
        chunks.append(event)

    assert not any(event.event == "approval_request" for event in chunks)
    assert any(
        event.event == "mission_done" and event.data.get("status") == "completed"
        for event in chunks
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_connector_lane_emits_progress_and_result_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _FakeAgentExecutor
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.SubagentManager",
        _FakeSubagentManager,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MemoryService.store_fact",
        _noop_async,
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.TodoService.upsert_task",
        lambda *args, **kwargs: "task-connector",
    )

    class _FakeConnectorOrchestrator:
        def __init__(self, db):  # noqa: ARG002
            pass

        def sync_connector(
            self, connector_id, tenant_id, progress_callback=None
        ):  # noqa: ARG002
            if progress_callback:
                progress_callback(
                    {
                        "phase": "fetch",
                        "message": "Fetched GitHub repository metadata.",
                        "connector_id": str(connector_id),
                    }
                )
            return {
                "status": "success",
                "message": "GitHub connector synced.",
                "health": {"healthy": True, "status": "healthy"},
            }

        def validate_connector_health(self, connector_id, tenant_id):  # noqa: ARG002
            return {
                "status": "healthy",
                "healthy": True,
                "message": "ok",
                "health": {"status": "healthy", "healthy": True},
            }

    monkeypatch.setattr(
        "app.integrations.services.connector_orchestrator.ConnectorOrchestrator",
        _FakeConnectorOrchestrator,
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    connector_row = SimpleNamespace(
        id=uuid4(),
        name="GitHub Source",
        tenant_id=auth.tenant_id,
    )
    integration_row = SimpleNamespace(slug="github")
    db = _FakeSupportDb([(connector_row, integration_row)])
    orchestrator = MasterOrchestrator(
        db=db,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    chunks: list[SimpleNamespace] = []
    async for event in orchestrator.stream_mission(
        objective="Sync the GitHub connector.",
        conversation_id=uuid4(),
    ):
        chunks.append(event)

    assert any(
        event.event == "lane_observation"
        and event.data.get("tool_name") == "sync_connector"
        and "Fetched GitHub" in str(event.data.get("summary"))
        for event in chunks
    )
    connector_result = next(
        event
        for event in chunks
        if event.event == "lane_result" and event.data.get("lane_type") == "connector"
    )
    metadata = connector_result.data["metadata"]
    assert metadata["synced_connectors"] == ["github"]
    assert any(
        result["integration_slug"] == "github" and result["status"] == "success"
        for result in metadata["connector_results"]
    )
    assert any(
        result["status"] == "not_found" for result in metadata["connector_results"]
    )
    github_result = next(
        result
        for result in metadata["connector_results"]
        if result.get("integration_slug") == "github"
    )
    assert github_result["health"]["healthy"] is True


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_master_orchestrator_support_sweep_routes_through_internal_support_lanes(
    monkeypatch,
) -> None:
    integration_row = SimpleNamespace(slug="gmail")

    async def _fake_vitals(tenant_id):  # noqa: ARG001
        return {
            "internet": "connected",
            "llm": "connected",
            "web_search": "available",
            "sources": 1,
        }

    class _FakeDaemonRegistry:
        def __init__(self, settings):  # noqa: ARG002
            pass

        def get_daemon_heartbeat(self):
            return {
                "phase": "running",
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "interval_seconds": 300,
            }

    class _FakeConnectorOrchestrator:
        def __init__(self, db):  # noqa: ARG002
            pass

        def validate_connector_health(self, connector_id, tenant_id):  # noqa: ARG002
            return {
                "status": "healthy",
                "healthy": True,
                "message": "ok",
                "health": {"status": "healthy", "healthy": True},
            }

    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.MissionRegistry", _FakeRegistry
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.AgentExecutor", _FakeAgentExecutor
    )
    monkeypatch.setattr(
        "app.deepspace.orchestration.master_orchestrator.VitalsService.get_system_vitals",
        _fake_vitals,
    )
    monkeypatch.setattr(
        "app.deepspace.subagents.subagent_registry.SubagentRegistry",
        _FakeDaemonRegistry,
    )
    monkeypatch.setattr(
        "app.integrations.services.connector_orchestrator.ConnectorOrchestrator",
        _FakeConnectorOrchestrator,
    )

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    connector_row = SimpleNamespace(
        id=uuid4(), name="Support Connector", tenant_id=auth.tenant_id
    )
    db = _FakeSupportDb([(connector_row, integration_row)])
    orchestrator = MasterOrchestrator(
        db=db,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    report = await orchestrator.execute_support_mission()

    assert report["healthy"] is True
    assert report["vitals"]["internet"] == "connected"
    assert "connector_health" in report
    assert db.commits > 0


def test_master_orchestrator_prevent_proactive_recursion_loop() -> None:
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    orchestrator = MasterOrchestrator(
        db=None,
        auth=auth,
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="test-provider",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )

    # 1. Normal proactive objective triggers proactive signal
    plan_normal = orchestrator._build_plan(
        objective="proactive tasks check",
    )
    assert plan_normal["signals"]["proactive"] is True

    # 2. Objective containing the recursion pattern disables proactive signal
    plan_recursive = orchestrator._build_plan(
        objective="Create proactive follow-up work for: normal check",
    )
    assert plan_recursive["signals"]["proactive"] is False
