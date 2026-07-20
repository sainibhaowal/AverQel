from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.deepspace.missions.mission_registry as mission_registry_module
from app.auth.dependencies import AuthContext
from app.services.deepspace.execution.agent_executor import AgentExecutor
from app.services.deepspace.execution.agent_tools import ToolResult
from app.services.deepspace.deepspace_runtime.runtime_hooks import RuntimeHooks


class _EchoSynthesisLLM:
    async def stream_generate_events(self, request):  # noqa: ARG002
        if False:
            yield {}

    def generate(self, request):
        return SimpleNamespace(content=request.messages[-1]["content"])


class _ToolCallThenAnswerLLM:
    def __init__(self) -> None:
        self.turn = 0

    async def stream_generate_events(self, request):  # noqa: ARG002
        self.turn += 1
        if self.turn == 1:
            yield {
                "type": "tool_calls_delta",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_web_1",
                        "function": {"name": "web_search", "arguments": ""},
                    }
                ],
            }
            yield {
                "type": "tool_calls_delta",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_web_1",
                        "function": {"arguments": '{"query":"latest ai"}'},
                    }
                ],
            }
            return
        yield {"type": "delta", "text": "done"}

    def generate(self, request):  # noqa: ARG002
        return SimpleNamespace(content="done")


async def _fake_search_memories(*, tenant_id, user_id, query, limit=5):  # noqa: ARG001
    return []


def _base_executor(fake_llm, hooks: RuntimeHooks) -> AgentExecutor:
    executor = AgentExecutor.__new__(AgentExecutor)
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "test-model"
    executor._resolved_provider_type = "openai"
    executor._resolved_base_url = "http://localhost"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 2048
    executor._reported_context_limit = 2048
    executor._resolved_context_limit_source = "test"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="test-model",
        llm_api_base_url="http://localhost",
        llm_provider="openai",
        max_context_chars=2048,
        deepspace_agent_max_steps=12,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None
    executor.run_control = None
    executor.execution_mode = "auto_review"
    executor.runtime_hooks = hooks
    executor.runtime_policy = None
    executor.db = None
    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=None,
        dynamic_tools={},
        current_parent_id=None,
        execution_mode="auto_review",
        get_effective_tier=lambda name: 1 if name == "web_search" else 3,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]
    return executor


@pytest.mark.asyncio
async def test_runtime_hooks_can_modify_turn_input_and_final_answer() -> None:
    async def pre_turn(_context, payload):
        return {"user_message": f"{payload['user_message']} [hooked]"}

    async def pre_answer_finalize(_context, payload):
        return {"content": f"{payload['content']} [finalized]"}

    hooks = RuntimeHooks(
        pre_turn=[pre_turn],
        pre_answer_finalize=[pre_answer_finalize],
    )
    executor = _base_executor(_EchoSynthesisLLM(), hooks)
    executor.tool_executor.execute = lambda *args, **kwargs: ToolResult(  # type: ignore[assignment]
        success=True,
        output="",
    )

    events = []
    async for event in executor.execute(user_message="Hello"):
        events.append(event)

    final_event = next(event for event in events if event.type == "final_answer")
    assert final_event.data["content"] == "Hello [hooked] [finalized]"


@pytest.mark.asyncio
async def test_runtime_hooks_observe_tool_lifecycle() -> None:
    observed: list[tuple[str, str]] = []

    async def pre_tool(_context, payload):
        observed.append(("pre", str(payload["tool_name"])))
        return payload

    async def post_tool(_context, payload):
        observed.append(("post", str(payload["tool_name"])))

    hooks = RuntimeHooks(pre_tool=[pre_tool], post_tool=[post_tool])
    executor = _base_executor(_ToolCallThenAnswerLLM(), hooks)

    async def execute_tool(name, args, **kwargs):  # noqa: ARG001
        return ToolResult(success=True, output="search results")

    executor.tool_executor.execute = execute_tool

    events = []
    async for event in executor.execute(user_message="Find latest ai news"):
        events.append(event)

    assert ("pre", "web_search") in observed
    assert ("post", "web_search") in observed
    assert any(event.type == "tool_result" for event in events)


@pytest.mark.asyncio
async def test_runtime_hooks_can_be_disabled_by_runtime_preference(monkeypatch) -> None:
    async def pre_turn(_context, payload):
        return {"user_message": f"{payload['user_message']} [hooked]"}

    hooks = RuntimeHooks(pre_turn=[pre_turn])
    executor = _base_executor(_EchoSynthesisLLM(), hooks)
    executor.tool_executor.execute = lambda *args, **kwargs: ToolResult(  # type: ignore[assignment]
        success=True,
        output="",
    )
    monkeypatch.setattr(
        mission_registry_module.MissionRegistry,
        "get_runtime_hooks_enabled",
        lambda self, **kwargs: False,  # noqa: ARG005
    )

    events = []
    async for event in executor.execute(user_message="Hello"):
        events.append(event)

    final_event = next(event for event in events if event.type == "final_answer")
    assert final_event.data["content"] == "Hello"
