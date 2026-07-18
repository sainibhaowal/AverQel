import json
import uuid
from typing import Any
from unittest.mock import patch

import pytest

from app.core.auth import AuthContext
from app.db.session import get_session_factory
from app.repositories.query.chat import ChatRepository
from app.schemas.query.followups import FollowupSuggestions
from app.services.providers.types import (
    ProviderSelectionCandidate,
    ProviderSelectionResult,
)
from app.services.query.query_service import QueryService


@pytest.fixture
def db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _parse_sse_frame(frame: str) -> tuple[str, dict]:
    event_name = "message"
    data_lines: list[str] = []
    for raw_line in frame.splitlines():
        if raw_line.startswith("event:"):
            event_name = raw_line.split(":", 1)[1].strip()
        elif raw_line.startswith("data:"):
            data_lines.append(raw_line.split(":", 1)[1].strip())
    payload = json.loads("\n".join(data_lines)) if data_lines else {}
    return event_name, payload


def _fake_httpx_module(lines: list[str]):
    class _FakeResponse:
        def __init__(self, payload_lines: list[str]) -> None:
            self.status_code = 200
            self._payload_lines = payload_lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def aiter_lines(self):
            for line in self._payload_lines:
                yield line

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        def stream(self, *args: Any, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse(lines)

    class _FakeTimeout:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class _FakeHttpxModule:
        AsyncClient = _FakeAsyncClient
        Timeout = _FakeTimeout

    return _FakeHttpxModule()


@pytest.mark.asyncio
async def test_stream_execute_flow(settings, seed_user):
    user_data = seed_user(
        "Stream Tenant", "stream@example.com", "StrongPass!1234", ("reader",)
    )
    settings.llm_provider = "openai"
    settings.ai_integration_scope = "embeddings_and_generation"
    settings.llm_api_key = "test"
    settings.llm_api_base_url = "http://mock-api"
    settings.llm_model = "gpt-3.5-turbo"

    auth = AuthContext(
        user_id=user_data.user_id,
        tenant_id=user_data.tenant_id,
        roles=frozenset({"reader"}),
        permissions=frozenset(),
        token_id=str(uuid.uuid4()),
        auth_type="jwt",
    )
    from app.services.query.retrieval_service import RetrievedChunk

    mock_chunk = RetrievedChunk(
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        filename="mock.pdf",
        content="This is the ground truth.",
        similarity_score=0.9,
        source_type="text",
    )

    db_session = get_session_factory()()
    try:
        service = QueryService(db_session, settings)

        with (
            patch(
                "app.services.query.retrieval_service.RetrievalService.retrieve",
                return_value=[mock_chunk],
            ),
            patch(
                "app.services.providers.selection_service.ProviderSelectionService.resolve_chat",
                return_value=ProviderSelectionResult(
                    feature_scope="chat",
                    candidates=[
                        ProviderSelectionCandidate(
                            provider_type="openai",
                            model_name="gpt-3.5-turbo",
                            feature_scope="chat",
                            source="env_fallback",
                            base_url="http://mock-api",
                            api_key="test",
                            metadata={},
                        )
                    ],
                    selection_notes=[],
                ),
            ),
            patch(
                "app.services.query.answer_service.importlib.import_module",
                return_value=_fake_httpx_module(
                    [
                        'data: {"choices": [{"delta": {"content": "Hello"}}]}',
                        'data: {"choices": [{"delta": {"content": " world"}}]}',
                        "data: [DONE]",
                    ]
                ),
            ),
        ):
            frames: list[tuple[str, dict]] = []
            async for frame in service.stream_execute(
                auth=auth,
                query_text="Tell me hello",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
            ):
                frames.append(_parse_sse_frame(frame))

        event_names = [name for name, _ in frames]
        error_frames = [payload for name, payload in frames if name == "error"]
        assert event_names[0] == "start"
        assert "meta" in event_names
        assert "trace" in event_names
        assert "citation" in event_names
        assert (
            "delta" in event_names
        ), f"Expected 'delta' event, but got error: {error_frames}"
        assert "replace" in event_names
        assert "done" in event_names
        assert event_names[-1] == "status"
        status_payloads = [payload for name, payload in frames if name == "status"]
        assert len(status_payloads) >= 6
        assert any(payload.get("code") == "retrieval" for payload in status_payloads)
        assert any(payload.get("code") == "grounding" for payload in status_payloads)
        assert any(payload.get("code") == "trace" for payload in status_payloads)
        assert any(payload.get("code") == "synthesis" for payload in status_payloads)
        assert all(payload.get("timestamp") for payload in status_payloads)

        meta_payload = next(payload for name, payload in frames if name == "meta")
        assert meta_payload["conversation_id"]
        assert meta_payload["trace_id"]
        assert meta_payload["source_count"] == 1

        delta_text = "".join(
            payload.get("text", "") for name, payload in frames if name == "delta"
        )
        assert delta_text == "Hello world"

        replace_payload = next(payload for name, payload in frames if name == "replace")
        assert replace_payload["content"] == "Hello world"
        assert replace_payload["format"] == "markdown"

        repo = ChatRepository(db_session)
        messages = repo.get_messages(
            tenant_id=user_data.tenant_id,
            conversation_id=uuid.UUID(meta_payload["conversation_id"]),
        )
        assert len(messages) == 2
        assert messages[1].role == "assistant"
        assert messages[1].content == "Hello world"
        assert messages[1].metadata_json["trace_id"] == meta_payload["trace_id"]
        persisted_status_history = messages[1].metadata_json["status_history"]
        assert any(item["code"] == "retrieval" for item in persisted_status_history)
        assert any(item["code"] == "grounding" for item in persisted_status_history)
        assert any(item["code"] == "synthesis" for item in persisted_status_history)
    finally:
        db_session.close()


@pytest.mark.asyncio
async def test_stream_execute_emits_thinking_events_when_supported(settings, seed_user):
    user_data = seed_user(
        "Thinking Tenant", "thinking@example.com", "StrongPass!1234", ("reader",)
    )
    settings.llm_provider = "openai"
    settings.ai_integration_scope = "embeddings_and_generation"
    settings.llm_api_key = "test"
    settings.llm_api_base_url = "http://mock-api"
    settings.llm_model = "nvidia/nemotron-3-nano-4b"

    auth = AuthContext(
        user_id=user_data.user_id,
        tenant_id=user_data.tenant_id,
        roles=frozenset({"reader"}),
        permissions=frozenset(),
        token_id=str(uuid.uuid4()),
        auth_type="jwt",
    )
    from app.services.query.retrieval_service import RetrievedChunk

    mock_chunk = RetrievedChunk(
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        filename="mock.pdf",
        content="Grounding text.",
        similarity_score=0.9,
        source_type="text",
    )

    db_session = get_session_factory()()
    try:
        service = QueryService(db_session, settings)
        with (
            patch(
                "app.services.query.retrieval_service.RetrievalService.retrieve",
                return_value=[mock_chunk],
            ),
            patch(
                "app.services.providers.selection_service.ProviderSelectionService.resolve_chat",
                return_value=ProviderSelectionResult(
                    feature_scope="chat",
                    candidates=[
                        ProviderSelectionCandidate(
                            provider_type="openai",
                            model_name="nvidia/nemotron-3-nano-4b",
                            feature_scope="chat",
                            source="env_fallback",
                            base_url="http://mock-api",
                            api_key="test",
                            metadata={},
                        )
                    ],
                    selection_notes=[],
                ),
            ),
            patch(
                "app.services.query.answer_service.importlib.import_module",
                return_value=_fake_httpx_module(
                    [
                        'data: {"choices": [{"delta": {"reasoning_content": "Thinking..."}}]}',
                        'data: {"choices": [{"delta": {"content": "Final"}}]}',
                        "data: [DONE]",
                    ]
                ),
            ),
        ):
            frames: list[tuple[str, dict]] = []
            async for frame in service.stream_execute(
                auth=auth,
                query_text="Explain this",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
                thinking_enabled=True,
            ):
                frames.append(_parse_sse_frame(frame))

        assert ("thinking", {"text": "Thinking..."}) in frames
    finally:
        db_session.close()


@pytest.mark.asyncio
async def test_stream_execute_ignores_reasoning_chunks_when_thinking_disabled(
    settings, seed_user
):
    user_data = seed_user(
        "Thinking Off Tenant",
        "thinking-off@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    settings.llm_provider = "openai"
    settings.ai_integration_scope = "embeddings_and_generation"
    settings.llm_api_key = "test"
    settings.llm_api_base_url = "http://mock-api"
    settings.llm_model = "nvidia/nemotron-3-nano-4b"

    auth = AuthContext(
        user_id=user_data.user_id,
        tenant_id=user_data.tenant_id,
        roles=frozenset({"reader"}),
        permissions=frozenset(),
        token_id=str(uuid.uuid4()),
        auth_type="jwt",
    )
    from app.services.query.retrieval_service import RetrievedChunk

    mock_chunk = RetrievedChunk(
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        filename="mock.pdf",
        content="Grounding text.",
        similarity_score=0.9,
        source_type="text",
    )

    db_session = get_session_factory()()
    try:
        service = QueryService(db_session, settings)

        with (
            patch(
                "app.services.query.retrieval_service.RetrievalService.retrieve",
                return_value=[mock_chunk],
            ),
            patch(
                "app.services.providers.selection_service.ProviderSelectionService.resolve_chat",
                return_value=ProviderSelectionResult(
                    feature_scope="chat",
                    candidates=[
                        ProviderSelectionCandidate(
                            provider_type="openai",
                            model_name="nvidia/nemotron-3-nano-4b",
                            feature_scope="chat",
                            source="env_fallback",
                            base_url="http://mock-api",
                            api_key="test",
                            metadata={},
                        )
                    ],
                    selection_notes=[],
                ),
            ),
            patch(
                "app.services.query.answer_service.importlib.import_module",
                return_value=_fake_httpx_module(
                    [
                        'data: {"choices": [{"delta": {"reasoning_content": "Thinking..."}}]}',
                        'data: {"choices": [{"delta": {"content": "Final"}}]}',
                        "data: [DONE]",
                    ]
                ),
            ),
        ):
            frames: list[tuple[str, dict]] = []
            async for frame in service.stream_execute(
                auth=auth,
                query_text="Explain this",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
                thinking_enabled=False,
            ):
                frames.append(_parse_sse_frame(frame))

        meta_payload = next(payload for event, payload in frames if event == "meta")

        assert ("thinking", {"text": "Thinking..."}) not in frames
        assert any(event == "trace" for event, _payload in frames)
        assert meta_payload.get("reasoning_trace") is not None
        assert ("delta", {"text": "Final"}) in frames
    finally:
        db_session.close()


@pytest.mark.asyncio
async def test_stream_execute_falls_back_to_grounded_text_when_llm_usage_is_denied(
    settings, seed_user
):
    user_data = seed_user(
        "Fallback Tenant", "fallback@example.com", "StrongPass!1234", ("reader",)
    )
    settings.llm_provider = "openai"
    settings.ai_integration_scope = "embeddings_and_generation"
    settings.llm_api_key = "test"
    settings.llm_api_base_url = "http://mock-api"
    settings.llm_model = "gpt-3.5-turbo"

    auth = AuthContext(
        user_id=user_data.user_id,
        tenant_id=user_data.tenant_id,
        roles=frozenset({"reader"}),
        permissions=frozenset(),
        token_id=str(uuid.uuid4()),
        auth_type="jwt",
    )
    from app.services.query.retrieval_service import RetrievedChunk

    mock_chunk = RetrievedChunk(
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        filename="mock.pdf",
        content="Unit 2 Random Variables study goals and core concepts.",
        similarity_score=0.95,
        source_type="text",
    )

    db_session = get_session_factory()()
    try:
        service = QueryService(db_session, settings)

        with (
            patch(
                "app.services.query.retrieval_service.RetrievalService.retrieve",
                return_value=[mock_chunk],
            ),
            patch(
                "app.services.providers.selection_service.ProviderSelectionService.resolve_chat",
                return_value=ProviderSelectionResult(
                    feature_scope="chat",
                    candidates=[
                        ProviderSelectionCandidate(
                            provider_type="openai",
                            model_name="gpt-3.5-turbo",
                            feature_scope="chat",
                            source="env_fallback",
                            base_url="http://mock-api",
                            api_key="test",
                            metadata={},
                        )
                    ],
                    selection_notes=[],
                ),
            ),
            patch.object(type(service.answer), "_allow_llm_usage", return_value=False),
        ):
            frames: list[tuple[str, dict]] = []
            async for frame in service.stream_execute(
                auth=auth,
                query_text="Explain unit 2",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
            ):
                frames.append(_parse_sse_frame(frame))

        event_names = [name for name, _ in frames]
        assert "error" not in event_names
        assert "replace" in event_names
        replace_payload = next(payload for name, payload in frames if name == "replace")
        assert "Unit 2 Random Variables" in replace_payload["content"]
    finally:
        db_session.close()


@pytest.mark.asyncio
async def test_stream_execute_emits_diagram_event_for_structured_answer(
    settings, seed_user
):
    user_data = seed_user(
        "Diagram Tenant", "diagram@example.com", "StrongPass!1234", ("reader",)
    )
    settings.llm_provider = "openai"
    settings.ai_integration_scope = "embeddings_and_generation"
    settings.llm_api_key = "test"
    settings.llm_api_base_url = "http://mock-api"
    settings.llm_model = "gpt-3.5-turbo"

    auth = AuthContext(
        user_id=user_data.user_id,
        tenant_id=user_data.tenant_id,
        roles=frozenset({"reader"}),
        permissions=frozenset(),
        token_id=str(uuid.uuid4()),
        auth_type="jwt",
    )
    from app.services.query.retrieval_service import RetrievedChunk

    mock_chunk = RetrievedChunk(
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        filename="architecture.md",
        content="The architecture has ingest, retrieve, and answer stages.",
        similarity_score=0.91,
        source_type="text",
    )

    structured_response = json.dumps(
        {
            "key_findings": ["Three-stage pipeline"],
            "detailed_analysis": "### Pipeline\nThe system flows from ingest to retrieve to answer.",
            "limitations": "Grounded in the provided documentation.",
            "conclusion": "Architecture is retrieval-first.",
            "confidence_score": 0.83,
            "follow_up_suggestions": ["What are the retrieval bottlenecks?"],
            "diagram": {
                "title": "Pipeline",
                "diagram_type": "mermaid_flowchart",
                "source": "mermaid",
                "syntax": "flowchart LR\\nA[Ingest] --> B[Retrieve] --> C[Answer]",
                "description": "High-level request flow.",
            },
        }
    )

    db_session = get_session_factory()()
    try:
        service = QueryService(db_session, settings)

        with (
            patch(
                "app.services.query.retrieval_service.RetrievalService.retrieve",
                return_value=[mock_chunk],
            ),
            patch(
                "app.services.providers.selection_service.ProviderSelectionService.resolve_chat",
                return_value=ProviderSelectionResult(
                    feature_scope="chat",
                    candidates=[
                        ProviderSelectionCandidate(
                            provider_type="openai",
                            model_name="gpt-3.5-turbo",
                            feature_scope="chat",
                            source="env_fallback",
                            base_url="http://mock-api",
                            api_key="test",
                            metadata={},
                        )
                    ],
                    selection_notes=[],
                ),
            ),
            patch(
                "app.services.query.followup_service.FollowupService.generate",
                return_value=FollowupSuggestions(
                    follow_ups=["What are the retrieval bottlenecks?"]
                ),
            ),
            patch(
                "app.services.query.answer_service.importlib.import_module",
                return_value=_fake_httpx_module(
                    [
                        f'data: {{"choices": [{{"delta": {{"content": {json.dumps(structured_response)} }} }}]}}',
                        "data: [DONE]",
                    ]
                ),
            ),
        ):
            frames: list[tuple[str, dict]] = []
            async for frame in service.stream_execute(
                auth=auth,
                query_text="Show the architecture diagram",
                top_k=5,
                filters={},
                document_ids=None,
                created_at_from=None,
                created_at_to=None,
                source_types=None,
                min_extraction_coverage=None,
                max_extraction_coverage=None,
            ):
                frames.append(_parse_sse_frame(frame))

        event_names = [name for name, _ in frames]
        error_frames = [payload for name, payload in frames if name == "error"]
        assert (
            "diagram" in event_names
        ), f"Expected 'diagram' event, but got error: {error_frames}"
        assert "followups" in event_names
        diagram_payload = next(payload for name, payload in frames if name == "diagram")
        assert diagram_payload["diagram_type"] == "mermaid_flowchart"
        assert "flowchart LR" in diagram_payload["syntax"]
        followups_payload = next(
            payload for name, payload in frames if name == "followups"
        )
        assert followups_payload["items"] == ["What are the retrieval bottlenecks?"]
    finally:
        db_session.close()
