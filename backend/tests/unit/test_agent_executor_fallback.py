from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.deepspace.execution.agent_executor as agent_executor_module
import app.deepspace.missions.mission_registry as mission_registry_module
from app.auth.dependencies import AuthContext
from app.query.schemas.chats import ConversationCreateRequest, ConversationUpdate
from app.deepspace.execution.agent_executor import AgentExecutor
from app.deepspace.execution.agent_tools import ToolExecutor, ToolResult
from app.deepspace.orchestration.deepspace_service import DeepSpaceService


class _EmptyStreamLLM:
    async def stream_generate_events(self, request):  # noqa: ARG002
        if False:
            yield {}

    def generate(self, request):  # noqa: ARG002
        return SimpleNamespace(content="Synthesized final answer.")


class _HangingStreamLLM:
    async def stream_generate_events(self, request):  # noqa: ARG002
        await asyncio.sleep(999)
        if False:
            yield {}

    def generate(self, request):  # noqa: ARG002
        return SimpleNamespace(content="Synthesized final answer.")


class _DeltaOnlyLLM:
    async def stream_generate_events(self, request):  # noqa: ARG002
        yield {"type": "delta", "text": "Hello"}
        yield {"type": "delta", "text": " world"}

    def generate(self, request):  # noqa: ARG002
        return SimpleNamespace(content="")


class _ToolCallThenAnswerLLM:
    def __init__(self) -> None:
        self._turn = 0

    async def stream_generate_events(self, request):  # noqa: ARG002
        self._turn += 1
        if self._turn == 1:
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

        yield {"type": "delta", "text": "Live "}
        yield {"type": "delta", "text": "answer"}

    def generate(self, request):  # noqa: ARG002
        return SimpleNamespace(content="")


def test_textual_tool_call_parser_handles_ask_user_question_sentinel():
    raw = (
        '[ASK_USER_QUESTION(QUESTIONS=[{"QUESTION":"Can you clarify the main goal?",'
        '"HEADER":"Clarification needed"}], OPTIONS=[])]<TOOL_CALL_END'
    )

    parsed = AgentExecutor._parse_textual_tool_calls(raw)

    assert parsed[0]["function"]["name"] == "ask_user_question"
    assert '"questions"' in parsed[0]["function"]["arguments"]


def test_parse_tool_call_recovers_partial_arguments_from_string_payload():
    executor = AgentExecutor.__new__(AgentExecutor)
    parsed = executor._parse_tool_call(
        {
            "id": "call_1",
            "function": {
                "name": "web_search",
                "arguments": 'query="latest ai news", source="web"',
            },
        }
    )

    assert parsed is not None
    assert parsed.name == "web_search"
    assert parsed.arguments == {"query": "latest ai news", "source": "web"}


def test_looks_like_textual_tool_call_xml():
    assert (
        AgentExecutor._looks_like_textual_tool_call(
            "<tool_code>write_file()</tool_code>"
        )
        is True
    )
    assert (
        AgentExecutor._looks_like_textual_tool_call(
            "I will do X\n<tool_call>bash()</tool_call>"
        )
        is True
    )
    assert AgentExecutor._looks_like_textual_tool_call("Hello world") is False


def test_parse_textual_tool_calls_xml():
    import json

    raw_xml_func = (
        "<tool_code> write_file(path='test.txt', content='hello') </tool_code>"
    )
    parsed_func = AgentExecutor._parse_textual_tool_calls(raw_xml_func)
    assert len(parsed_func) == 1
    assert parsed_func[0]["function"]["name"] == "write_file"
    args = json.loads(parsed_func[0]["function"]["arguments"])
    assert args == {"path": "test.txt", "content": "hello"}

    raw_xml_json = (
        '<tool_call>{"name": "edit_file", "arguments": {"path": "app.py"}}</tool_call>'
    )
    parsed_json = AgentExecutor._parse_textual_tool_calls(raw_xml_json)
    assert len(parsed_json) == 1
    assert parsed_json[0]["function"]["name"] == "edit_file"
    args_json = json.loads(parsed_json[0]["function"]["arguments"])
    assert args_json == {"path": "app.py"}


@pytest.mark.asyncio
async def test_stream_agent_loop_forwards_conversation_id_to_execute():
    executor = AgentExecutor.__new__(AgentExecutor)
    captured: dict[str, object] = {}
    conversation_id = uuid4()

    async def _fake_execute(*args, **kwargs):  # noqa: ARG001
        captured.update(kwargs)
        if False:
            yield {}

    executor.execute = _fake_execute  # type: ignore[assignment]

    events = []
    async for event in executor.stream_agent_loop(
        conversation_id=conversation_id,
        user_message="Hi there",
    ):
        events.append(event)

    assert events == []
    assert captured["conversation_id"] == conversation_id
    assert captured["user_message"] == "Hi there"


@pytest.mark.asyncio
async def test_task_tool_uses_current_parent_id_for_subagent_lineage(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeSubagentManager:
        def __init__(self, db, settings, auth):  # noqa: D401, ANN001
            self.db = db
            self.settings = settings
            self.auth = auth

        async def spawn_and_execute(
            self,
            *,
            stype,
            prompt,
            parent_id,
            execution_mode="auto_review",
        ):
            captured["stype"] = stype
            captured["prompt"] = prompt
            captured["parent_id"] = parent_id
            captured["execution_mode"] = execution_mode
            return ToolResult(success=True, output="Sub-agent completed.")

    monkeypatch.setattr(
        "app.deepspace.subagents.subagent_manager.SubagentManager",
        _FakeSubagentManager,
    )

    executor = ToolExecutor.__new__(ToolExecutor)
    executor.db = SimpleNamespace()
    executor.settings = SimpleNamespace()
    executor.auth = SimpleNamespace()
    executor.execution_mode = "full_access"
    parent_id = uuid4()
    executor.current_parent_id = parent_id

    result = await executor._exec_task(
        {
            "subagent_type": "research",
            "prompt": "Investigate the issue.",
            "description": "Research issue",
        }
    )

    assert result.success is True
    assert captured["stype"] == "research"
    assert captured["prompt"] == "Investigate the issue."
    assert captured["parent_id"] == parent_id
    assert captured["execution_mode"] == "full_access"


def test_deepspace_note_title_normalization_accepts_blank_titles():
    assert ConversationCreateRequest(title=" ").title == "Untitled Note"
    assert ConversationUpdate(title=" ").title is None


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_synthesizes_final_answer_when_stream_is_empty():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _EmptyStreamLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _noop_execute(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(success=True, output="")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_noop_execute,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Hi"):
        events.append(event)

    assert any(event.type == "step_summary" for event in events)
    final_event = next(event for event in events if event.type == "final_answer")
    assert final_event.data["content"] == "Synthesized final answer."


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_emits_step_boundary_events():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _EmptyStreamLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(*, tenant_id, user_id, query, limit=5):
        return []

    async def _noop_execute(*args, **kwargs):
        return SimpleNamespace(success=True, output="")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_noop_execute,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Hi"):
        events.append(event)

    assert any(event.type == "step_start" for event in events)
    assert any(event.type == "step_finish" for event in events)
    start_index = next(
        i for i, event in enumerate(events) if event.type == "step_start"
    )
    finish_index = next(
        i for i, event in enumerate(events) if event.type == "step_finish"
    )
    assert start_index < finish_index


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_continues_when_memory_bootstrap_fails():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _EmptyStreamLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _failing_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        raise RuntimeError("relation agent_memory does not exist")

    async def _noop_execute(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(success=True, output="")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_failing_search_memories),
        execute=_noop_execute,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Hi"):
        events.append(event)

    final_event = next(event for event in events if event.type == "final_answer")
    assert final_event.data["content"] == "Synthesized final answer."


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_uses_builtin_system_instruction_when_settings_lack_rulebook():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _EmptyStreamLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _noop_execute(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(success=True, output="")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_noop_execute,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    assert executor._base_system_instruction() == executor.SYSTEM_INSTRUCTION

    events = []
    async for event in executor.execute(user_message="Hi"):
        events.append(event)

    final_event = next(event for event in events if event.type == "final_answer")
    assert final_event.data["content"] == "Synthesized final answer."


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_fast_bootstrap_skips_memory_and_preplan_for_simple_turn():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _DeltaOnlyLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
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

    async def _fail_search_memories(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("fast bootstrap should skip memory loading")

    async def _noop_execute(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(success=True, output="")

    async def _fail_build_plan(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("fast bootstrap should skip autonomous preplan")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fail_search_memories),
        execute=_noop_execute,
        get_effective_tier=lambda name: 1,  # noqa: ARG005
    )
    executor._build_autonomous_plan = _fail_build_plan  # type: ignore[assignment]
    executor.execution_mode = "auto_review"
    executor.run_control = None

    events = []
    async for event in executor.execute(user_message="Say hello"):
        events.append(event)

    status_event = next(event for event in events if event.type == "agent_status")
    assert status_event.data["bootstrap_mode"] == "fast"
    deltas = [event.data["text"] for event in events if event.type == "answer_delta"]
    assert "".join(deltas) == "Hello world"


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_streams_textual_tool_like_tokens_to_the_ui():
    class _ToolLikeDeltaLLM:
        async def stream_generate_events(self, request):  # noqa: ARG002
            yield {"type": "delta", "text": "write_file("}
            yield {"type": "delta", "text": 'path="report.md"'}
            yield {"type": "delta", "text": ', content="Hello")'}

        def generate(self, request):  # noqa: ARG002
            return SimpleNamespace(content="")

    executor = AgentExecutor.__new__(AgentExecutor)
    executor._resolved_llm = _ToolLikeDeltaLLM()
    executor._resolved_model_name = "demo"
    executor._resolved_provider_type = "openai"
    executor._resolved_base_url = "http://localhost:1234/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "test"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="demo",
        llm_api_base_url="http://localhost:1234/v1",
        llm_provider="openai",
        max_context_chars=204800,
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
    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=lambda *args, **kwargs: []),
        execute=lambda *args, **kwargs: SimpleNamespace(success=True, output=""),
        get_effective_tier=lambda name: 1,  # noqa: ARG005
    )
    executor._build_autonomous_plan = lambda *args, **kwargs: None  # type: ignore[assignment]
    executor.execution_mode = "auto_review"
    executor.run_control = None

    events = []
    async for event in executor.execute(user_message="Write a file"):
        events.append(event)

    deltas = [event.data["text"] for event in events if event.type == "answer_delta"]
    assert "".join(deltas) == 'write_file(path="report.md", content="Hello")'


@pytest.mark.unit_no_db
def test_agent_executor_fast_bootstrap_only_for_simple_single_turns():
    executor = AgentExecutor.__new__(AgentExecutor)
    executor.settings = SimpleNamespace()

    assert (
        executor._should_use_fast_bootstrap(
            user_message="Rewrite this sentence.",
            previous_messages=None,
            note_content=None,
        )
        is True
    )
    assert (
        executor._should_use_fast_bootstrap(
            user_message="Research the latest AI agent architecture and compare vendors.",
            previous_messages=None,
            note_content=None,
        )
        is False
    )


@pytest.mark.unit_no_db
def test_agent_executor_runtime_resolution_uses_short_ttl_cache(monkeypatch):
    AgentExecutor._runtime_cache.clear()
    resolve_calls = {"count": 0}

    class _FakeRegistry:
        def __init__(self, settings):  # noqa: ARG002
            pass

        def get_chat_provider(self, provider_type=None):  # noqa: ARG002
            return "default-provider"

        @staticmethod
        def _bind_chat_provider(provider, *, base_url, api_key):  # noqa: ARG002
            return {"provider": provider, "base_url": base_url, "api_key": api_key}

    monkeypatch.setattr(agent_executor_module, "ProviderRegistry", _FakeRegistry)

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    candidate = SimpleNamespace(
        provider_type="openai",
        model_name="gpt-test",
        base_url="https://example.test/v1",
        api_key="key-1",
        context_window=32000,
        context_window_source="live_model",
    )

    def _make_executor():
        executor = AgentExecutor.__new__(AgentExecutor)
        executor.auth = auth
        executor.settings = SimpleNamespace(
            llm_model="gpt-test",
            llm_provider="openai",
            llm_api_base_url="https://fallback.test/v1",
            llm_api_key="fallback-key",
            max_context_chars=32000,
        )
        executor._resolved_llm = None
        executor._resolved_model_name = None
        executor._resolved_provider_type = None
        executor._resolved_base_url = None
        executor._resolved_api_key = None
        executor._resolved_context_limit = None
        executor._reported_context_limit = None
        executor._resolved_context_limit_source = "unknown"
        executor.provider_selection = SimpleNamespace(
            resolve_chat=lambda **kwargs: (
                resolve_calls.__setitem__("count", resolve_calls["count"] + 1)
                or SimpleNamespace(candidates=[candidate])
            )
        )
        return executor

    first = _make_executor()
    second = _make_executor()

    first_provider = first._resolve_runtime()
    second_provider = second._resolve_runtime()

    assert resolve_calls["count"] == 1
    assert first_provider == second_provider
    AgentExecutor._runtime_cache.clear()


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_memory_bootstrap_uses_short_ttl_cache():
    AgentExecutor._memory_bootstrap_cache.clear()
    memory_calls = {"count": 0}

    executor = AgentExecutor.__new__(AgentExecutor)
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    async def _search_memories(*, tenant_id, user_id, query, limit=5):  # noqa: ARG001
        memory_calls["count"] += 1
        return [{"key": "project", "value": "AVERQEL"}]

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_search_memories)
    )

    first = await executor._load_memory_facts(query="*", limit=5)
    second = await executor._load_memory_facts(query="*", limit=5)

    assert memory_calls["count"] == 1
    assert first == second == [{"key": "project", "value": "AVERQEL"}]
    AgentExecutor._memory_bootstrap_cache.clear()


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_synthesizes_final_answer_when_stream_stalls():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _HangingStreamLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=0.1,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _noop_execute(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(success=True, output="")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_noop_execute,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Hi"):
        events.append(event)

    assert any(event.type == "step_summary" for event in events)
    final_event = next(event for event in events if event.type == "final_answer")
    assert final_event.data["content"] == "Synthesized final answer."


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_emits_answer_done_for_direct_streamed_reply():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _DeltaOnlyLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _noop_execute(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(success=True, output="")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_noop_execute,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Hi"):
        events.append(event)

    delta_text = "".join(
        event.data["text"] for event in events if event.type == "answer_delta"
    )
    assert delta_text == "Hello world"
    assert any(event.type == "answer_done" for event in events)
    assert all(event.type != "final_answer" for event in events)


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_announces_auto_tool_during_stream_and_preserves_tool_id():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _ToolCallThenAnswerLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _fake_execute(name, args, background_tasks=None):  # noqa: ARG001
        return SimpleNamespace(success=True, output=f"searched for {args['query']}")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_fake_execute,
        get_effective_tier=lambda name: 1 if name == "web_search" else 3,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Find latest AI news"):
        events.append(event)

    tool_starts = [event for event in events if event.type == "tool_start"]
    tool_results = [event for event in events if event.type == "tool_result"]

    assert len(tool_starts) == 1
    assert len(tool_results) == 1
    assert tool_starts[0].data["tool_name"] == "web_search"
    assert tool_starts[0].data["tool_id"] == "call_web_1"
    assert tool_results[0].data["tool_id"] == "call_web_1"
    assert tool_results[0].data["tool_input"] == {"query": "latest ai"}
    assert events.index(tool_starts[0]) < events.index(tool_results[0])
    delta_text = "".join(
        event.data["text"] for event in events if event.type == "answer_delta"
    )
    assert delta_text == "Live answer"


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_streams_tool_delta_before_tool_result():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _ToolCallThenAnswerLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _fake_execute(
        name, args, background_tasks=None, event_sink=None
    ):  # noqa: ARG001
        if event_sink is not None:
            await event_sink(
                {"stream": "stdout", "text": "running...\n", "bash_id": "bash-1"}
            )
            await asyncio.sleep(0)
            await event_sink(
                {"stream": "stdout", "text": "done\n", "bash_id": "bash-1"}
            )
        return SimpleNamespace(success=True, output="running...\ndone\n")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_fake_execute,
        get_effective_tier=lambda name: 1 if name == "web_search" else 3,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    events = []
    async for event in executor.execute(user_message="Find latest AI news"):
        events.append(event)

    tool_delta_events = [event for event in events if event.type == "tool_delta"]
    tool_result_event = next(event for event in events if event.type == "tool_result")
    assert [event.data["text"] for event in tool_delta_events] == [
        "running...\n",
        "done\n",
    ]
    assert events.index(tool_delta_events[0]) < events.index(tool_result_event)


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_forwards_tool_context_to_tool_executor():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _ToolCallThenAnswerLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    seen: dict[str, object] = {}

    async def _fake_execute(
        name,
        args,
        background_tasks=None,
        tool_context=None,
    ):  # noqa: ARG001
        seen["tool_name"] = name
        seen["args"] = dict(args)
        seen["lineage"] = tool_context.lineage() if tool_context else None
        tool_context.set_state("last_query", args.get("query"))
        seen["state"] = dict(tool_context.temp_state_store)
        return SimpleNamespace(success=True, output=f"searched for {args['query']}")

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_fake_execute,
        get_effective_tier=lambda name: 1 if name == "web_search" else 3,
        current_parent_id=None,
        tool_context=None,
    )
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    conversation_id = uuid4()
    async for _event in executor.execute(
        user_message="Find latest AI news",
        conversation_id=conversation_id,
    ):
        pass

    assert seen["tool_name"] == "web_search"
    assert seen["args"] == {"query": "latest ai"}
    assert seen["lineage"] == {
        "tenant_id": str(executor.auth.tenant_id),
        "user_id": str(executor.auth.user_id),
        "conversation_id": str(conversation_id),
        "mission_id": None,
        "lane_id": None,
    }
    assert seen["state"]["last_query"] == "latest ai"
    assert seen["state"]["workspace_mode"]["enabled"] is False


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_passes_workspace_mode_to_runtime_policy_for_code_tasks():
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _ToolCallThenAnswerLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _fake_execute(
        name,
        args,
        background_tasks=None,
        tool_context=None,
    ):  # noqa: ARG001
        return SimpleNamespace(success=True, output=f"searched for {args['query']}")

    seen: dict[str, object] = {}

    class _CapturingRuntimePolicy:
        def assess_tool_call(
            self,
            *,
            mode,
            tool_name,
            tier,
            args=None,
            workspace_mode=None,
            **kwargs,
        ):
            seen["mode"] = mode
            seen["tool_name"] = tool_name
            seen["workspace_mode"] = (
                workspace_mode.summary() if workspace_mode is not None else None
            )
            from app.deepspace.policy.execution_policy import ExecutionDecision

            return ExecutionDecision(
                mode=mode,
                requires_human_approval=False,
                should_block=False,
                reason="ok",
            )

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_fake_execute,
        get_effective_tier=lambda name: 1 if name == "web_search" else 3,
        current_parent_id=None,
        tool_context=None,
    )
    executor.runtime_policy = _CapturingRuntimePolicy()
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]

    async for _event in executor.execute(
        user_message="Check the repo and fix the failing code in src/app.py",
    ):
        pass

    workspace_mode = seen["workspace_mode"]
    assert isinstance(workspace_mode, dict)
    assert workspace_mode["enabled"] is True
    assert workspace_mode["task_kind"] == "code"
    assert seen["tool_name"] == "web_search"


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_agent_executor_keeps_workspace_mode_disabled_when_runtime_flag_is_off(
    monkeypatch,
) -> None:
    executor = AgentExecutor.__new__(AgentExecutor)
    fake_llm = _ToolCallThenAnswerLLM()
    executor._resolved_llm = fake_llm
    executor._resolved_model_name = "minimax-m2.5-free"
    executor._resolved_provider_type = "opencode-zen"
    executor._resolved_base_url = "https://opencode.ai/zen/v1"
    executor._resolved_api_key = "test-key"
    executor._resolved_context_limit = 204800
    executor._reported_context_limit = 204800
    executor._resolved_context_limit_source = "official_docs:minimax"
    executor.settings = SimpleNamespace(
        system_rulebook="RULEBOOK",
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
        llm_model="minimax-m2.5-free",
        llm_api_base_url="https://opencode.ai/zen/v1",
        llm_provider="opencode-zen",
        max_context_chars=204800,
        deepspace_workspace_mode_rollout_enabled=False,
    )
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.background_tasks = None
    executor.restricted_tools = None

    async def _fake_search_memories(
        *, tenant_id, user_id, query, limit=5
    ):  # noqa: ARG001
        return []

    async def _fake_execute(
        name, args, background_tasks=None, tool_context=None
    ):  # noqa: ARG001
        return SimpleNamespace(success=True, output=f"searched for {args['query']}")

    seen: dict[str, object] = {}

    class _CapturingRuntimePolicy:
        def assess_tool_call(
            self,
            *,
            mode,
            tool_name,
            tier,
            args=None,
            workspace_mode=None,
            **kwargs,
        ):
            seen["workspace_mode"] = (
                workspace_mode.summary() if workspace_mode is not None else None
            )
            from app.deepspace.policy.execution_policy import ExecutionDecision

            return ExecutionDecision(
                mode=mode,
                requires_human_approval=False,
                should_block=False,
                reason="ok",
            )

    executor.tool_executor = SimpleNamespace(
        memory=SimpleNamespace(search_memories=_fake_search_memories),
        execute=_fake_execute,
        get_effective_tier=lambda name: 1 if name == "web_search" else 3,
        current_parent_id=None,
        tool_context=None,
    )
    executor.runtime_policy = _CapturingRuntimePolicy()
    executor._is_complex_task = lambda *args, **kwargs: False  # type: ignore[assignment]
    monkeypatch.setattr(
        mission_registry_module.MissionRegistry,
        "get_workspace_mode_enabled",
        lambda self, **kwargs: True,  # noqa: ARG005
    )

    async for _event in executor.execute(
        user_message="Check the repo and fix the failing code in src/app.py",
    ):
        pass

    workspace_mode = seen["workspace_mode"]
    assert isinstance(workspace_mode, dict)
    assert workspace_mode["enabled"] is False


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_service_persists_permission_pause_without_fallback(
    monkeypatch,
):
    added_messages: list[dict[str, object]] = []

    class _FakeChatRepo:
        def add_message(self, **kwargs):
            added_messages.append(kwargs)
            return SimpleNamespace(id=uuid4())

    class _PermissionOnlyExecutor:
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
            return "minimax-m2.5-free"

        @property
        def provider_type(self):
            return "opencode-zen"

        @property
        def context_limit_source(self):
            return "official_docs:minimax"

        async def run(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(
                type="permission_request",
                data={
                    "step_id": "step-1",
                    "tool_id": "tool-1",
                    "tool_name": "bash",
                    "tool_input": {"command": "echo hi"},
                },
            )

    monkeypatch.setattr(
        "app.deepspace.orchestration.deepspace_service.AgentExecutor",
        _PermissionOnlyExecutor,
    )

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(query_no_result_answer_text="no result")
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
    service._should_prefetch_web_context = lambda query_text: False

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service.stream_chat_agentic(
        auth=auth,
        query_text="run a command",
        conversation_id=None,
    ):
        chunks.append(chunk)

    stream_output = "".join(chunks)
    assert "event: permission_request" in stream_output
    assert "event: done" not in stream_output
    assert "I’m ready to help with" not in stream_output
    assert len(added_messages) == 2
    assert added_messages[-1]["role"] == "assistant"
    assert added_messages[-1]["content"] == ""
    metadata = added_messages[-1]["metadata_json"]
    assert isinstance(metadata, dict)
    assert metadata["agent_steps"][0]["tool_name"] == "bash"


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_service_streams_and_persists_normal_assistant_reply(
    monkeypatch,
):
    added_messages: list[dict[str, object]] = []

    class _FakeChatRepo:
        def add_message(self, **kwargs):
            added_messages.append(kwargs)
            return SimpleNamespace(id=uuid4())

    class _SimpleReplyExecutor:
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
            return "minimax-m2.5-free"

        @property
        def provider_type(self):
            return "opencode-zen"

        @property
        def context_limit_source(self):
            return "official_docs:minimax"

        async def run(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(
                type="answer_delta", data={"text": "Hello from DeepSpace."}
            )
            yield SimpleNamespace(type="answer_done", data={"total_steps": 1})

    monkeypatch.setattr(
        "app.deepspace.orchestration.deepspace_service.AgentExecutor",
        _SimpleReplyExecutor,
    )

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(query_no_result_answer_text="no result")
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
    service._should_prefetch_web_context = lambda query_text: False

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service.stream_chat_agentic(
        auth=auth,
        query_text="hi",
        conversation_id=None,
    ):
        chunks.append(chunk)

    stream_output = "".join(chunks)
    assert "event: start" in stream_output
    assert "event: metrics" in stream_output
    assert "event: delta" in stream_output
    assert "Hello from DeepSpace." in stream_output
    assert "event: done" in stream_output
    assert len(added_messages) == 2
    assert added_messages[-1]["role"] == "assistant"
    assert added_messages[-1]["content"] == "Hello from DeepSpace."


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_service_resume_streams_approved_tool_and_versions_response(
    monkeypatch,
):
    created_versions: list[dict[str, object]] = []
    assistant_message_id = uuid4()

    class _FakeChatRepo:
        def get_conversation(self, **kwargs):  # noqa: ARG002
            return SimpleNamespace(id=uuid4())

        def get_messages(self, **kwargs):  # noqa: ARG002
            return [
                SimpleNamespace(
                    role="user", id=uuid4(), content="run a command", metadata_json={}
                ),
                SimpleNamespace(
                    role="assistant",
                    id=assistant_message_id,
                    content="",
                    metadata_json={
                        "agent_steps": [
                            {
                                "step_id": "step-1",
                                "tool_id": "tool-1",
                                "tool_name": "bash",
                                "tool_input": {"command": "echo hi"},
                            }
                        ]
                    },
                ),
            ]

        def create_message_version(self, **kwargs):
            created_versions.append(kwargs)

    class _ResumeExecutor:
        def __init__(self, **kwargs):  # noqa: ARG002
            self.tool_executor = SimpleNamespace(execute=self._execute)

        @property
        def llm(self):
            return object()

        @property
        def reported_context_limit(self):
            return 204800

        @property
        def model_name(self):
            return "minimax-m2.5-free"

        @property
        def provider_type(self):
            return "opencode-zen"

        @property
        def context_limit_source(self):
            return "official_docs:minimax"

        async def _execute(
            self, name, args, background_tasks=None, event_sink=None
        ):  # noqa: ARG002
            if event_sink is not None:
                await event_sink(
                    {"stream": "stdout", "text": "hi\n", "bash_id": "bash-1"}
                )
            return SimpleNamespace(success=True, output="hi\n")

        async def run(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(type="answer_delta", data={"text": "Resumed answer."})
            yield SimpleNamespace(type="answer_done", data={"total_steps": 2})

    monkeypatch.setattr(
        "app.deepspace.orchestration.deepspace_service.AgentExecutor",
        _ResumeExecutor,
    )

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
    )
    service.chat = _FakeChatRepo()
    service.provider_selection = SimpleNamespace()
    service.answer = SimpleNamespace()
    service.retrieval = SimpleNamespace()
    service._build_previous_messages = lambda **kwargs: [
        {"role": "user", "content": "run a command"},
        {"role": "assistant", "content": ""},
    ]
    service._should_prefetch_web_context = lambda query_text: False

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service.resume_chat(
        auth=auth,
        conversation_id=uuid4(),
        step_id="step-1",
        tool_id="tool-1",
        approved=True,
    ):
        chunks.append(chunk)

    stream_output = "".join(chunks)
    assert "event: tool_start" in stream_output
    assert "event: tool_delta" in stream_output
    assert "event: tool_result" in stream_output
    assert "Resumed answer." in stream_output
    assert created_versions[-1]["message_id"] == assistant_message_id
    assert created_versions[-1]["source_type"] == "resume"


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_service_regenerate_uses_agentic_versioning(monkeypatch):
    created_versions: list[dict[str, object]] = []
    assistant_message_id = uuid4()
    user_message_id = uuid4()

    class _FakeChatRepo:
        def get_latest_turn_pair(self, **kwargs):  # noqa: ARG002
            return (
                SimpleNamespace(
                    id=user_message_id,
                    role="user",
                    content="hi",
                    metadata_json={},
                    active_version=None,
                ),
                SimpleNamespace(
                    id=assistant_message_id,
                    role="assistant",
                    content="old answer",
                    metadata_json={},
                    active_version=None,
                ),
            )

        def get_messages(self, **kwargs):  # noqa: ARG002
            return [
                SimpleNamespace(
                    id=user_message_id,
                    role="user",
                    content="hi",
                    metadata_json={},
                    active_version=None,
                )
            ]

        def create_message_version(self, **kwargs):
            created_versions.append(kwargs)

    class _ReplyExecutor:
        def __init__(self, **kwargs):  # noqa: ARG002
            self.tool_executor = SimpleNamespace(execute=lambda *args, **kwargs: None)

        @property
        def llm(self):
            return object()

        @property
        def reported_context_limit(self):
            return 204800

        @property
        def model_name(self):
            return "minimax-m2.5-free"

        @property
        def provider_type(self):
            return "opencode-zen"

        @property
        def context_limit_source(self):
            return "official_docs:minimax"

        async def run(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(
                type="answer_delta", data={"text": "Regenerated answer."}
            )
            yield SimpleNamespace(type="answer_done", data={"total_steps": 1})

    monkeypatch.setattr(
        "app.deepspace.orchestration.deepspace_service.AgentExecutor",
        _ReplyExecutor,
    )

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(
        query_no_result_answer_text="no result",
        provider_timeout_seconds=8,
    )
    service.chat = _FakeChatRepo()
    service.provider_selection = SimpleNamespace()
    service.answer = SimpleNamespace()
    service.retrieval = SimpleNamespace()
    service._should_prefetch_web_context = lambda query_text: False

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service.regenerate_message_stream(
        auth=auth,
        conversation_id=uuid4(),
        assistant_message_id=assistant_message_id,
    ):
        chunks.append(chunk)

    stream_output = "".join(chunks)
    assert "event: start" in stream_output
    assert "Regenerated answer." in stream_output
    assert created_versions[-1]["message_id"] == assistant_message_id
    assert created_versions[-1]["source_type"] == "regenerate"
