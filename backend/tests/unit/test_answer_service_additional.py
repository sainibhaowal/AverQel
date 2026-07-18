from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.core.config import get_settings
from app.services.providers.types import ProviderSelectionCandidate
from app.services.query.answer_service import (
    AnswerService,
    LlmCircuitState,
    NonRetryableLlmError,
    RetryableLlmError,
)
from app.services.query.query_classifier import QueryType
from app.services.query.retrieval_service import RetrievedChunk

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _chunk(similarity: float, text: str = "content") -> RetrievedChunk:
    return RetrievedChunk(
        document_id=UUID("11111111-1111-7111-8111-111111111111"),
        chunk_id=UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
        filename="mock.pdf",
        content=text,
        similarity_score=similarity,
    )


def _reset_state() -> None:
    AnswerService._llm_circuit = LlmCircuitState()
    AnswerService._limit_state.requests.clear()
    AnswerService._limit_state.cost_micros.clear()


def test_synthesize_clamps_confidence_and_snippet_helpers() -> None:
    _reset_state()
    service = AnswerService("no-result")
    result = service.synthesize(
        retrieved_chunks=[_chunk(1.8, "x" * 600), _chunk(1.2, "y"), _chunk(1.1, "z")]
    )
    assert result.confidence == 1.0
    assert result.answer
    assert len(result.citations) == 3
    assert result.citations[0].snippet.endswith("...")
    assert AnswerService._estimate_tokens("") == 0
    from app.services.query.snippet_service import SnippetService

    assert SnippetService.clean("  a   b ", 10) == "a b"


def test_llm_generation_enabled_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state()
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_API_KEY", "k")
    get_settings.cache_clear()
    service = AnswerService("no-result", get_settings())
    assert service._llm_generation_enabled() is True

    monkeypatch.setenv("AKS_LLM_PROVIDER", "disabled")
    get_settings.cache_clear()
    assert AnswerService("no-result", get_settings())._llm_generation_enabled() is False

    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_only")
    get_settings.cache_clear()
    assert AnswerService("no-result", get_settings())._llm_generation_enabled() is False
    get_settings.cache_clear()


def test_generate_with_provider_fallback_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state()
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_API_KEY", "k")
    get_settings.cache_clear()
    service = AnswerService("no-result", get_settings())
    chunks = [_chunk(0.9, "A"), _chunk(0.8, "B")]

    # Circuit-open fallback — stream yields a fallback message
    AnswerService._llm_circuit.opened_until = datetime.now(tz=UTC) + timedelta(
        seconds=10
    )
    result = list(
        service._stream_generate_with_provider(
            tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
            query_text="Q",
            ranked_chunks=chunks,
        )
    )
    assert len(result) == 1
    assert "Circuit Open" in result[0]
    AnswerService._llm_circuit.opened_until = None
    get_settings.cache_clear()


def test_call_llm_provider_status_and_payload_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_state()
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_API_KEY", "k")
    get_settings.cache_clear()
    service = AnswerService("no-result", get_settings())

    class FakeResponse:
        def __init__(self, status_code: int, payload: object) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> object:
            if isinstance(self._payload, Exception):
                raise self._payload
            return self._payload

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(post=lambda *a, **k: FakeResponse(429, {})),
    )
    with pytest.raises(RetryableLlmError):
        service._call_llm_provider(query_text="Q", context="C")

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(post=lambda *a, **k: FakeResponse(400, {})),
    )
    with pytest.raises(NonRetryableLlmError):
        service._call_llm_provider(query_text="Q", context="C")

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            post=lambda *a, **k: FakeResponse(200, json.JSONDecodeError("bad", "x", 0))
        ),
    )
    with pytest.raises(RetryableLlmError):
        service._call_llm_provider(query_text="Q", context="C")

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(post=lambda *a, **k: FakeResponse(200, {"choices": []})),
    )
    with pytest.raises(RetryableLlmError):
        service._call_llm_provider(query_text="Q", context="C")

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            post=lambda *a, **k: FakeResponse(
                200, {"choices": [{"message": {"content": 1}}]}
            )
        ),
    )
    with pytest.raises(RetryableLlmError):
        service._call_llm_provider(query_text="Q", context="C")

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            post=lambda *a, **k: FakeResponse(
                200, {"choices": [{"message": {"content": "ok"}}]}
            )
        ),
    )
    assert service._call_llm_provider(query_text="Q", context="C") == ("ok", {})
    get_settings.cache_clear()


def test_allow_llm_usage_in_memory_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state()
    monkeypatch.setenv("AKS_AI_INTEGRATION_SCOPE", "embeddings_and_generation")
    monkeypatch.setenv("AKS_LLM_PROVIDER", "groq-openai-compatible")
    monkeypatch.setenv("AKS_LLM_API_KEY", "k")
    monkeypatch.setenv("AKS_LLM_MAX_REQUESTS_PER_MINUTE", "1")
    monkeypatch.setenv("AKS_LLM_MAX_TOKENS_PER_REQUEST", "100")
    monkeypatch.setenv("AKS_LLM_MONTHLY_BUDGET_USD", "0.000001")
    get_settings.cache_clear()

    service = AnswerService("no-result", get_settings())
    monkeypatch.setattr(
        "app.services.query.answer_service.get_redis_client",
        lambda: (_ for _ in ()).throw(RuntimeError("down")),
    )
    tenant = UUID("11111111-1111-7111-8111-111111111111")

    assert (
        service._allow_llm_usage(tenant_id=tenant, estimated_input_tokens=10) is False
    )

    _reset_state()
    monkeypatch.setenv("AKS_LLM_MONTHLY_BUDGET_USD", "1")
    get_settings.cache_clear()
    service = AnswerService("no-result", get_settings())
    monkeypatch.setattr(
        "app.services.query.answer_service.get_redis_client",
        lambda: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert service._allow_llm_usage(tenant_id=tenant, estimated_input_tokens=10) is True
    assert (
        service._allow_llm_usage(tenant_id=tenant, estimated_input_tokens=10) is False
    )
    get_settings.cache_clear()


def test_allow_llm_usage_allows_local_provider_candidates() -> None:
    _reset_state()
    service = AnswerService("no-result", get_settings())
    tenant = UUID("11111111-1111-7111-8111-111111111111")

    candidate = ProviderSelectionCandidate(
        provider_type="custom",
        model_name="local-model",
        feature_scope="chat",
        source="tenant",
        base_url="http://host.docker.internal:1234/v1",
        metadata={"is_local": True},
    )

    assert service._allow_llm_usage(
        tenant_id=tenant,
        estimated_input_tokens=100,
        provider_candidates=[candidate],
    )


def test_buffer_text_for_stream_prefers_small_semantic_chunks() -> None:
    chunks = list(
        AnswerService._buffer_text_for_stream(
            "This is a longer fallback answer that should stream in smaller semantic pieces instead of dumping one paragraph at once."
        )
    )

    assert len(chunks) >= 3
    assert all(chunk for chunk in chunks)
    assert all(len(chunk) <= 40 for chunk in chunks)
    assert (
        " ".join(chunks)
        .replace("  ", " ")
        .startswith("This is a longer fallback answer")
    )


def test_structured_output_instruction_prefers_specific_artifacts() -> None:
    comparison_instruction = AnswerService._build_structured_output_instruction(
        query="Compare onboarding latency by stage",
        query_type=QueryType.COMPARISON,
    )
    assert "comparison_table must be filled" in comparison_instruction

    chart_instruction = AnswerService._build_structured_output_instruction(
        query="Show the latency trend over time as a chart",
        query_type=QueryType.FACTUAL,
    )
    assert "chart must be filled" in chart_instruction

    diagram_instruction = AnswerService._build_structured_output_instruction(
        query="Show the sequence handoff between ingest, retrieve, and answer",
        query_type=QueryType.EXPLORATORY,
    )
    assert "diagram must be filled" in diagram_instruction
    assert "mermaid_sequence" in diagram_instruction

    graph_instruction = AnswerService._build_structured_output_instruction(
        query="Show a system dependency graph of client, api, and retriever nodes",
        query_type=QueryType.EXPLORATORY,
    )
    assert "graph_json" in graph_instruction
    assert "graph_canvas" in graph_instruction

    er_instruction = AnswerService._build_structured_output_instruction(
        query="Create an entity relationship diagram for documents, collections, and chunks",
        query_type=QueryType.EXPLORATORY,
    )
    assert "mermaid_er" in er_instruction
    assert "erDiagram" in er_instruction


def test_open_chat_empty_provider_response_falls_back_to_buffered_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_state()
    service = AnswerService("no-result", get_settings())

    async def _empty_provider_events(**kwargs):
        if False:
            yield {"type": "delta", "text": ""}  # pragma: no cover
        return

    async def _collect() -> list:
        events = []
        async for event in service.stream_open_chat_events_async(
            query_text="write code in html",
            tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
            provider_candidates=[
                ProviderSelectionCandidate(
                    provider_type="lmstudio",
                    model_name="test-model",
                    feature_scope="chat",
                    source="tenant",
                )
            ],
        ):
            events.append(event)
        return events

    monkeypatch.setattr(service, "_llm_generation_enabled", lambda **kwargs: True)
    monkeypatch.setattr(service, "_llm_is_circuit_open", lambda: False)
    monkeypatch.setattr(service, "_allow_llm_usage", lambda **kwargs: True)
    monkeypatch.setattr(service, "_estimate_tokens", lambda text: 10)
    monkeypatch.setattr(
        service, "_astream_open_chat_provider_events", _empty_provider_events
    )

    events = asyncio.run(_collect())

    assert events
    assert events[-1].event == "done"
    assert (
        "live model response"
        in " ".join(
            event.data.get("text", "") for event in events if event.event == "delta"
        ).lower()
    )


def test_open_chat_provider_failure_falls_back_to_buffered_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_state()
    service = AnswerService("no-result", get_settings())

    async def _raise_provider_failure(**kwargs):
        if False:
            yield {"type": "delta", "text": ""}  # pragma: no cover
        raise NonRetryableLlmError("provider offline")

    async def _collect() -> list:
        events = []
        async for event in service.stream_open_chat_events_async(
            query_text="write code in html",
            tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
            provider_candidates=[
                ProviderSelectionCandidate(
                    provider_type="lmstudio",
                    model_name="test-model",
                    feature_scope="chat",
                    source="tenant",
                )
            ],
        ):
            events.append(event)
        return events

    monkeypatch.setattr(service, "_llm_generation_enabled", lambda **kwargs: True)
    monkeypatch.setattr(service, "_llm_is_circuit_open", lambda: False)
    monkeypatch.setattr(service, "_allow_llm_usage", lambda **kwargs: True)
    monkeypatch.setattr(service, "_estimate_tokens", lambda text: 10)
    monkeypatch.setattr(
        service, "_astream_open_chat_provider_events", _raise_provider_failure
    )

    events = asyncio.run(_collect())

    assert events
    assert events[-1].event == "done"
    assert not any(event.event == "error" for event in events)
    assert (
        "switch the selected model or provider"
        in " ".join(
            event.data.get("text", "") for event in events if event.event == "delta"
        ).lower()
    )


def test_open_chat_chart_queries_use_structured_chart_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_state()
    service = AnswerService("no-result", get_settings())

    payload = json.dumps(
        {
            "key_findings": ["Sales are increasing month over month."],
            "detailed_analysis": "The chart shows a clean upward trend.",
            "limitations": "",
            "conclusion": "Growth is positive.",
            "confidence_score": 0.94,
            "follow_up_suggestions": [],
            "comparison_table": None,
            "chart": {
                "title": "Monthly Sales",
                "chart_type": "line",
                "series": [
                    {"label": "Jan", "value": 10},
                    {"label": "Feb", "value": 12},
                    {"label": "Mar", "value": 18},
                ],
            },
            "diagram": None,
        }
    )

    async def _provider_events(**kwargs):
        assert kwargs["structured_output"] is True
        yield {"type": "delta", "text": payload}

    async def _collect() -> list:
        events = []
        async for event in service.stream_open_chat_events_async(
            query_text="Create a line chart for Jan 10, Feb 12, Mar 18",
            tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
            provider_candidates=[
                ProviderSelectionCandidate(
                    provider_type="lmstudio",
                    model_name="test-model",
                    feature_scope="chat",
                    source="tenant",
                )
            ],
        ):
            events.append(event)
        return events

    monkeypatch.setattr(service, "_llm_generation_enabled", lambda **kwargs: True)
    monkeypatch.setattr(service, "_llm_is_circuit_open", lambda: False)
    monkeypatch.setattr(service, "_allow_llm_usage", lambda **kwargs: True)
    monkeypatch.setattr(service, "_estimate_tokens", lambda text: 10)
    monkeypatch.setattr(service, "_astream_open_chat_provider_events", _provider_events)

    events = asyncio.run(_collect())

    assert any(event.event == "delta" for event in events)
    assert any(event.event == "replace" for event in events)
    chart_event = next(event for event in events if event.event == "chart")
    assert chart_event.data["chart_type"] == "line"
    assert chart_event.data["title"] == "Monthly Sales"


def test_open_chat_salvages_nested_series_chart_type_without_falling_back_to_line() -> (
    None
):
    payload = {
        "key_findings": ["Distribution is balanced."],
        "detailed_analysis": "Pie chart requested.",
        "limitations": "",
        "conclusion": "Pie is appropriate.",
        "confidence_score": 1.0,
        "follow_up_suggestions": [],
        "comparison_table": None,
        "chart": {
            "chart_type": "pie",
            "series": [
                {
                    "label": "Percentage Share",
                    "data": [
                        {"name": "Marketing", "y": 30},
                        {"name": "Sales", "y": 40},
                        {"name": "Support", "y": 30},
                    ],
                }
            ],
            "title": "Share by Team",
        },
        "diagram": None,
    }

    structured = AnswerService._try_parse_structured_answer(json.dumps(payload))

    assert structured is not None
    assert structured.chart is not None
    assert structured.chart.chart_type == "pie"
    assert len(structured.chart.series) == 3
    assert structured.chart.series[0].label == "Marketing"
    assert structured.chart.series[0].value == 30


def test_build_llm_messages_disables_json_in_streaming_mode() -> None:
    service = AnswerService("no-result")

    messages = service._build_llm_messages(
        "Show the architecture flow",
        "Context block",
        history=None,
        query_type=QueryType.EXPLORATORY,
        structured_output=False,
    )

    system_prompt = messages[0]["content"]
    assert "Respond as a single valid JSON object" not in system_prompt
    assert "Do not wrap the answer in JSON" in system_prompt


def test_try_parse_structured_answer_salvages_partial_json() -> None:
    candidate = """
    {
      "key_findings": ["Dependencies are explicit"],
      "diagram": {
        "title": "Topology",
        "diagram_type": "graph_canvas",
        "source": "graph_json",
        "graph": {
          "layout": "horizontal",
          "nodes": [
            {"id": "a", "label": "Client"},
            {"id": "b", "label": "API"}
          ],
          "edges": [
            {"source": "a", "target": "b", "label": "request"}
          ]
        }
      }
    }
    """

    structured = AnswerService._try_parse_structured_answer(candidate)

    assert structured is not None
    assert structured.diagram is not None
    assert structured.diagram.source == "graph_json"
    assert structured.diagram.graph is not None
    assert structured.diagram.graph.nodes[0].label == "Client"
