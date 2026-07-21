from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.deepspace.planning.mission_planner import MissionPlanner


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def generate(self, request):  # noqa: ARG002
        return SimpleNamespace(content=self._content)


class _FakeAgentExecutor:
    def __init__(self, content: str) -> None:
        self.model_name = "test-model"
        self.provider_type = "openai"
        self.base_url = "http://localhost"
        self.api_key = "test-key"
        self.llm = _FakeLLM(content)


def _planner(content: str = "{}") -> MissionPlanner:
    return MissionPlanner(
        agent=_FakeAgentExecutor(content),
        settings=SimpleNamespace(
            llm_model="test-model",
            llm_provider="openai",
            llm_api_base_url="http://localhost",
            llm_api_key="test-key",
            provider_timeout_seconds=30,
        ),
    )


@pytest.mark.asyncio
async def test_model_planner_json_is_validated_before_use() -> None:
    planner = _planner("""
        ```json
        {
          "planner_source": "llm",
          "summary": "Use the model planner",
          "parallel_limit": 4,
          "signals": {"research": true},
          "lane_blueprints": [
            {
              "ref": "main_chat",
              "lane_type": "main_chat",
              "title": "Core",
              "prompt": "Handle the main mission",
              "priority": 100,
              "depends_on": [],
              "blocked_by": [],
              "metadata": {"role": "primary"}
            }
          ]
        }
        ```
        """)

    payload = await planner._try_model_planner_json(
        objective="Plan the mission",
        note_content=None,
        execution_mode="auto_review",
        planner_mode="structured",
    )

    assert payload is not None
    assert payload["planner_source"] == "model"
    assert payload["planner_mode"] == "structured"
    assert payload["lane_blueprints"][0]["ref"] == "main_chat"
    assert payload["lane_blueprints"][0]["lane_type"] == "main_chat"


def test_materialize_plan_sanitizes_duplicate_refs_cycles_and_invalid_approval_refs() -> (
    None
):
    planner = _planner()

    plan = planner._materialize_plan(
        {
            "planner_source": "model",
            "summary": "Test plan",
            "signals": {"support": False},
            "approval_queue": [
                {
                    "lane_ref": "missing_ref",
                    "lane_type": "approval",
                    "message": "Review the gated action.",
                    "reason": "gated_action_detected",
                }
            ],
            "lane_blueprints": [
                {
                    "ref": "main_chat",
                    "lane_type": "main_chat",
                    "title": "Main",
                    "prompt": "Core objective",
                    "priority": 100,
                    "depends_on": ["writer_final"],
                    "blocked_by": [],
                    "metadata": {"role": "primary"},
                },
                {
                    "ref": "writer_final",
                    "lane_type": "writer",
                    "title": "Writer",
                    "prompt": "Draft output",
                    "priority": 80,
                    "depends_on": ["main_chat", "writer_final", "unknown_lane"],
                    "blocked_by": [],
                    "subagent_type": "writer",
                    "metadata": {"role": "writer"},
                },
                {
                    "ref": "writer_final",
                    "lane_type": "analysis",
                    "title": "Analysis",
                    "prompt": "Analyze output",
                    "priority": 70,
                    "depends_on": ["main_chat"],
                    "blocked_by": [],
                    "subagent_type": "analyzer",
                    "metadata": {"role": "analysis"},
                },
                {
                    "ref": "bad_lane",
                    "lane_type": "unsupported_lane",
                    "title": "Invalid",
                    "prompt": "Ignore",
                    "priority": 10,
                },
            ],
        },
        objective="Core objective",
        note_content=None,
        execution_mode="auto_review",
        planner_mode="default",
    )

    lane_blueprints = plan["lane_blueprints"]
    refs = [item["ref"] for item in lane_blueprints]

    assert "bad_lane" not in refs
    assert refs.count("writer_final") == 1
    assert any(ref.startswith("writer_final_") for ref in refs)

    main_blueprint = next(
        item for item in lane_blueprints if item["ref"] == "main_chat"
    )
    writer_blueprint = next(
        item for item in lane_blueprints if item["ref"] == "writer_final"
    )

    assert main_blueprint["depends_on"] == []
    assert writer_blueprint["depends_on"] == ["main_chat"]
    assert plan["approval_queue"][0]["lane_ref"] is None


def test_materialize_plan_falls_back_to_policy_when_all_blueprints_are_invalid() -> (
    None
):
    planner = _planner()

    plan = planner._materialize_plan(
        {
            "planner_source": "model",
            "summary": "Invalid plan",
            "lane_blueprints": [
                {
                    "ref": "bad_lane",
                    "lane_type": "invalid",
                    "title": "Invalid",
                    "prompt": "Invalid",
                    "priority": 1,
                }
            ],
        },
        objective="Research the migration plan",
        note_content=None,
        execution_mode="auto_review",
        planner_mode="default",
    )

    assert plan["planner_source"] == "policy"
    assert plan["planner_mode"] == "default"
    assert any(lane["lane_type"] == "main_chat" for lane in plan["lanes"])


@pytest.mark.asyncio
async def test_build_plan_carries_planner_mode_into_materialized_plan() -> None:
    planner = _planner("{}")

    plan = await planner.build_plan(
        objective="Plan a structured migration mission",
        execution_mode="auto_review",
        planner_mode="structured",
    )

    assert plan["planner_mode"] == "structured"


def test_prevent_proactive_recursion_loop() -> None:
    planner = _planner()

    # 1. Normal objective with proactive keyword should trigger proactive signal
    plan_normal = planner._policy_planner_json(
        objective="Proactive follow-up tasks",
        note_content=None,
        execution_mode="auto_review",
        planner_mode="default",
    )
    assert plan_normal["signals"]["proactive"] is True

    # 2. Objective that is already a proactive task should suppress the signal
    plan_recursive = planner._policy_planner_json(
        objective="Create proactive follow-up work and persisted task tracking for: some task",
        note_content=None,
        execution_mode="auto_review",
        planner_mode="default",
    )
    assert plan_recursive["signals"]["proactive"] is False

    # 3. Suppressing during materialize phase should strip proactive lanes and signals
    plan_materialized = planner._materialize_plan(
        {
            "planner_source": "model",
            "summary": "Recursive plan",
            "signals": {"proactive": True},
            "lane_blueprints": [
                {
                    "ref": "main_chat",
                    "lane_type": "main_chat",
                    "title": "Main",
                    "prompt": "Core objective",
                    "priority": 100,
                    "depends_on": [],
                    "blocked_by": [],
                    "metadata": {"role": "primary"},
                },
                {
                    "ref": "proactive_handoff",
                    "lane_type": "proactive",
                    "title": "Proactive Handoff",
                    "prompt": "Create proactive follow-up work for: ...",
                    "priority": 62,
                    "depends_on": [],
                    "blocked_by": [],
                    "metadata": {"role": "proactive"},
                },
            ],
        },
        objective="Create proactive follow-up work and persisted task tracking for: some task",
        note_content=None,
        execution_mode="auto_review",
        planner_mode="default",
    )
    assert plan_materialized["signals"]["proactive"] is False
    assert not any(
        lane["lane_type"] == "proactive" for lane in plan_materialized["lanes"]
    )
