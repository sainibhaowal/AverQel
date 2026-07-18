from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.auth import AuthContext
from app.core.config import Settings
from app.services.deepspace.orchestration.deepspace_service import DeepSpaceService


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_orchestrated_stream_emits_normalized_mission_and_lane_events(
    monkeypatch,
):
    added_messages: list[dict[str, object]] = []

    class _FakeChatRepo:
        def add_message(self, **kwargs):
            added_messages.append(kwargs)
            return SimpleNamespace(id=uuid4())

    class _RuntimeAgentExecutor:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        @property
        def llm(self):
            return object()

        @property
        def reported_context_limit(self):
            return 204800

        @property
        def model_name(self):
            return "test-model"

        @property
        def provider_type(self):
            return "test-provider"

        @property
        def context_limit_source(self):
            return "live_model"

    class _FakeOrchestrator:
        def __init__(self, **kwargs):  # noqa: ARG002
            pass

        async def stream_mission(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(
                event="mission_start",
                data={
                    "mission_id": "mission-1",
                    "objective": "Run a mission.",
                    "execution_mode": "auto_review",
                    "runtime_state": {
                        "planner_mode": "structured",
                        "diagnostics": {
                            "planner": {"lane_count": 2, "parallel_limit": 2},
                        },
                    },
                },
            )
            yield SimpleNamespace(
                event="mission_plan",
                data={
                    "mission_id": "mission-1",
                    "plan": {
                        "summary": "Mission plan ready.",
                        "lanes": [
                            {
                                "lane_id": "main_chat",
                                "lane_type": "main_chat",
                                "title": "Main Chat",
                                "prompt": "Answer the user.",
                                "priority": 100,
                                "depends_on": [],
                                "blocked_by": [],
                                "subagent_type": None,
                                "metadata": {},
                            },
                            {
                                "lane_id": "research_lane",
                                "lane_type": "research",
                                "title": "Research Lane",
                                "prompt": "Do research.",
                                "priority": 50,
                                "depends_on": ["main_chat"],
                                "blocked_by": [],
                                "subagent_type": "research",
                                "metadata": {},
                            },
                        ],
                    },
                    "runtime_state": {
                        "planner_validation_status": "validated",
                        "runtime_hooks_state": "active",
                    },
                },
            )
            yield SimpleNamespace(
                event="lane_start",
                data={
                    "mission_id": "mission-1",
                    "lane_id": "research_lane",
                    "lane_type": "research",
                    "title": "Research Lane",
                    "prompt": "Do research.",
                    "metadata": {
                        "delegation_rationale": "Gather current evidence first.",
                    },
                },
            )
            yield SimpleNamespace(
                event="approval_request",
                data={
                    "mission_id": "mission-1",
                    "lane_id": "research_lane",
                    "lane_type": "research",
                    "message": "Approve research connector use.",
                },
            )
            yield SimpleNamespace(
                event="lane_result",
                data={
                    "mission_id": "mission-1",
                    "lane_id": "research_lane",
                    "lane_type": "research",
                    "status": "completed",
                    "summary": "Research complete.",
                    "output": "Research output.",
                    "metadata": {
                        "tool_density": {"started": 3, "completed": 3},
                    },
                },
            )
            yield SimpleNamespace(
                event="mission_done",
                data={
                    "mission_id": "mission-1",
                    "status": "completed",
                    "summary": "Mission complete.",
                },
            )

    monkeypatch.setattr(
        "app.services.deepspace.orchestration.deepspace_service.AgentExecutor",
        _RuntimeAgentExecutor,
    )
    monkeypatch.setattr(
        "app.services.deepspace.orchestration.master_orchestrator.MasterOrchestrator",
        _FakeOrchestrator,
    )

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = Settings()
    service.chat = _FakeChatRepo()
    service.provider_selection = SimpleNamespace()
    service.answer = SimpleNamespace()
    service.retrieval = SimpleNamespace()
    service._resolve_or_create_conversation = lambda **kwargs: SimpleNamespace(
        id=uuid4(),
        title="Untitled Note",
    )
    service._auto_title_conversation = lambda **kwargs: None
    service._build_previous_messages = lambda **kwargs: []

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service._stream_orchestrated_turn(
        auth=auth,
        conversation_id=uuid4(),
        query_text="Run a mission.",
        previous_messages=[],
        note_content=None,
        thinking_enabled=True,
        web_search_enabled=True,
        background_tasks=None,
        execution_mode="auto_review",
        agentic_mode=True,
    ):
        chunks.append(chunk)

    stream_output = "".join(chunks)
    assert "event: mission_start" in stream_output
    assert "event: mission_plan" in stream_output
    assert "event: lane_start" in stream_output
    assert "event: approval_request" in stream_output
    assert "event: lane_result" in stream_output
    assert "event: mission_done" in stream_output
    assert "event: done" in stream_output
    assert any(message.get("role") == "assistant" for message in added_messages)
