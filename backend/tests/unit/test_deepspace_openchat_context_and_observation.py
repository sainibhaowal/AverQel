from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.auth.dependencies import AuthContext
from app.deepspace.orchestration.deepspace_service import DeepSpaceService


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_stream_injects_manual_documents_into_openchat_context(
    monkeypatch,
):
    captured_note_contents: list[str | None] = []
    added_messages: list[dict[str, object]] = []
    document_id = uuid4()

    class _FakeChatRepo:
        def add_message(self, **kwargs):
            added_messages.append(kwargs)
            return SimpleNamespace(id=uuid4())

    class _ContextAwareExecutor:
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

        async def run(self, **kwargs):  # noqa: ARG002
            captured_note_contents.append(kwargs.get("note_content"))
            yield SimpleNamespace(
                type="answer_delta", data={"text": "Manual doc reply."}
            )
            yield SimpleNamespace(type="answer_done", data={"total_steps": 1})

    monkeypatch.setattr(
        "app.deepspace.orchestration.deepspace_service.AgentExecutor", _ContextAwareExecutor
    )

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(
        query_no_result_answer_text="no result",
        deepspace_document_context_doc_limit=3,
        deepspace_document_context_chunk_limit=2,
        deepspace_document_context_max_chars=6000,
    )
    service.chat = _FakeChatRepo()
    service.provider_selection = SimpleNamespace()
    service.answer = SimpleNamespace()
    service.retrieval = SimpleNamespace(
        documents=SimpleNamespace(
            list_accessible_for_user=lambda **kwargs: [
                SimpleNamespace(
                    id=document_id, connector_id=None, filename="manual-note.md"
                )
            ]
        ),
        retrieve=lambda **kwargs: [
            SimpleNamespace(
                document_id=document_id,
                filename="manual-note.md",
                content="Manual upload facts that should reach OpenChat.",
                similarity_score=0.91,
            )
        ],
    )
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
        query_text="Use the uploaded manual note.",
        conversation_id=None,
    ):
        chunks.append(chunk)

    assert any(
        "MANUAL DOCUMENT CONTEXT" in str(note or "") for note in captured_note_contents
    )
    assert any(
        "Manual upload facts" in str(note or "") for note in captured_note_contents
    )
    assert len(added_messages) == 2
    assert any(
        message.get("role") == "assistant"
        and "Manual doc reply." in str(message.get("content") or "")
        for message in added_messages
    )
    metadata = added_messages[-1]["metadata_json"]
    assert isinstance(metadata, dict)


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_stream_emits_observing_step(monkeypatch):
    added_messages: list[dict[str, object]] = []

    class _FakeChatRepo:
        def add_message(self, **kwargs):
            added_messages.append(kwargs)
            return SimpleNamespace(id=uuid4())

    class _ObservingExecutor:
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

        async def run(self, **kwargs):  # noqa: ARG002
            yield SimpleNamespace(
                type="observing",
                data={
                    "step_id": "step-1",
                    "tool_id": "tool-1",
                    "tool_name": "web_search",
                    "tool_input": {"query": "latest"},
                    "summary": "Observed successful search results.",
                    "success": True,
                    "observed_at": "2026-05-12T00:00:00Z",
                },
            )
            yield SimpleNamespace(
                type="answer_delta", data={"text": "Observation complete."}
            )
            yield SimpleNamespace(type="answer_done", data={"total_steps": 2})

    monkeypatch.setattr(
        "app.deepspace.orchestration.deepspace_service.AgentExecutor", _ObservingExecutor
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
        query_text="check the stream",
        conversation_id=None,
    ):
        chunks.append(chunk)

    stream_output = "".join(chunks)
    assert "event: observing" in stream_output
    assert any(
        any(
            step.get("type") == "observing"
            for step in message.get("metadata_json", {}).get("agent_steps", [])
        )
        for message in added_messages
        if message.get("role") == "assistant"
    )


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_stream_routes_simple_turn_to_agent_path():
    routed_paths: list[str] = []

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(query_no_result_answer_text="no result")
    service.chat = SimpleNamespace(add_message=lambda **kwargs: None)
    service.provider_selection = SimpleNamespace()
    service.answer = SimpleNamespace()
    service.retrieval = SimpleNamespace()
    service._resolve_or_create_conversation = lambda **kwargs: SimpleNamespace(
        id=uuid4(),
        title="Untitled Note",
    )
    service._auto_title_conversation = lambda **kwargs: None
    service._build_previous_messages = lambda **kwargs: []

    async def _fake_agent_turn(**kwargs):  # noqa: ARG001
        routed_paths.append("agent")
        yield "agent"

    async def _fake_orchestrated_turn(**kwargs):  # noqa: ARG001
        routed_paths.append("orchestrated")
        yield "orchestrated"

    service._stream_agent_turn = _fake_agent_turn
    service._stream_orchestrated_turn = _fake_orchestrated_turn

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service.stream_chat_agentic(
        auth=auth,
        query_text="Rewrite this sentence more clearly.",
        conversation_id=None,
    ):
        chunks.append(chunk)

    assert chunks == ["agent"]
    assert routed_paths == ["agent"]


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_deepspace_stream_routes_complex_turn_to_orchestration():
    routed_paths: list[str] = []

    service = DeepSpaceService.__new__(DeepSpaceService)
    service.db = SimpleNamespace(commit=lambda: None)
    service.settings = SimpleNamespace(query_no_result_answer_text="no result")
    service.chat = SimpleNamespace(add_message=lambda **kwargs: None)
    service.provider_selection = SimpleNamespace()
    service.answer = SimpleNamespace()
    service.retrieval = SimpleNamespace()
    service._resolve_or_create_conversation = lambda **kwargs: SimpleNamespace(
        id=uuid4(),
        title="Untitled Note",
    )
    service._auto_title_conversation = lambda **kwargs: None
    service._build_previous_messages = lambda **kwargs: [
        {"role": "user", "content": "Earlier context 1"},
        {"role": "assistant", "content": "Earlier context 2"},
        {"role": "user", "content": "Earlier context 3"},
        {"role": "assistant", "content": "Earlier context 4"},
    ]

    async def _fake_agent_turn(**kwargs):  # noqa: ARG001
        routed_paths.append("agent")
        yield "agent"

    async def _fake_orchestrated_turn(**kwargs):  # noqa: ARG001
        routed_paths.append("orchestrated")
        yield "orchestrated"

    service._stream_agent_turn = _fake_agent_turn
    service._stream_orchestrated_turn = _fake_orchestrated_turn

    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )

    chunks = []
    async for chunk in service.stream_chat_agentic(
        auth=auth,
        query_text=(
            "Research the current market, sync connectors, save memory, and create a "
            "proactive follow-up workflow."
        ),
        conversation_id=None,
        note_content="x" * 5000,
    ):
        chunks.append(chunk)

    assert chunks == ["orchestrated"]
    assert routed_paths == ["orchestrated"]


@pytest.mark.unit_no_db
def test_deepspace_simple_turns_use_fast_agent_path():
    assert (
        DeepSpaceService._should_use_orchestrated_turn(
            query_text="Summarize this note in two bullets.",
            previous_messages=[],
            note_content="Short note context.",
        )
        is False
    )


@pytest.mark.unit_no_db
def test_deepspace_complex_turns_escalate_to_orchestration():
    assert (
        DeepSpaceService._should_use_orchestrated_turn(
            query_text=(
                "Research the market, sync Gmail and GitHub connectors, save memory, "
                "and create a proactive follow-up workflow."
            ),
            previous_messages=[
                {"role": "user", "content": "Earlier context 1"},
                {"role": "assistant", "content": "Earlier context 2"},
                {"role": "user", "content": "Earlier context 3"},
                {"role": "assistant", "content": "Earlier context 4"},
            ],
            note_content="x" * 5000,
        )
        is True
    )
