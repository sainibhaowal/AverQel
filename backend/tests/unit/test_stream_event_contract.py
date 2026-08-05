import asyncio
from uuid import UUID

from app.providers.services.selection_service import ProviderSelectionCandidate
from app.query.services.answer_service import AnswerService, NonRetryableLlmError
from app.query.services.query_classifier import QueryType
from app.query.services.retrieval_service import RetrievedChunk


def _chunk(text: str, similarity: float = 0.93) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=UUID("11111111-1111-7111-8111-111111111111"),
        chunk_id=UUID("aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
        filename="architecture.pdf",
        content=text,
        similarity_score=similarity,
    )


def test_markdown_post_stream_events_emit_replace_chart_and_done() -> None:
    service = AnswerService("no-result")
    markdown = """
### Comparison

| Company | Investment |
| --- | --- |
| A | 10 |
| B | 20 |

Chart Data
- A: 10
- B: 20
""".strip()

    events = list(service._emit_post_stream_events(markdown, QueryType.COMPARISON))
    names = [event.event for event in events]

    assert names == ["replace", "chart", "done"]
    assert events[0].data["format"] == "markdown"
    assert events[1].data["series"] == [
        {"label": "A", "value": 10.0},
        {"label": "B", "value": 20.0},
    ]


def test_structured_post_stream_events_emit_replace_and_done() -> None:
    service = AnswerService("no-result")
    structured_json = (
        "{"
        '"key_findings":["Point A","Point B"],'
        '"detailed_analysis":"### Analysis\\nA grounded answer.",'
        '"limitations":"Limited sample",'
        '"conclusion":"Proceed",'
        '"confidence_score":0.81'
        "}"
    )

    events = list(service._emit_post_stream_events(structured_json, QueryType.ANALYTICAL))
    names = [event.event for event in events]

    assert names == ["replace", "done"]
    assert events[0].data["format"] == "structured"


def test_async_stream_provider_failure_emits_error_without_fallback_text(
    monkeypatch,
) -> None:
    service = AnswerService("no-result")

    async def _collect() -> list:
        events = []
        async for event in service.stream_synthesize_events_async(
            retrieved_chunks=[_chunk("Unreadable PDF glyph noise /uni00000057", 0.57)],
            query_text="Hi",
            tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
            query_type=QueryType.FACTUAL,
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

    async def _raise_provider_failure(**kwargs):
        if False:
            yield ""  # pragma: no cover
        raise NonRetryableLlmError("provider offline")

    monkeypatch.setattr(service, "_llm_generation_enabled", lambda **kwargs: True)
    monkeypatch.setattr(service, "_llm_is_circuit_open", lambda: False)
    monkeypatch.setattr(service, "_allow_llm_usage", lambda **kwargs: True)
    monkeypatch.setattr(service, "_build_prompt_context", lambda chunks: "Context block")
    monkeypatch.setattr(service, "_estimate_tokens", lambda text: 10)
    monkeypatch.setattr(service, "_astream_provider_text", _raise_provider_failure)

    events = asyncio.run(_collect())

    assert [event.event for event in events] == ["error"]
    assert events[0].data["code"] == "STREAM_PROVIDER_FAILURE"
    assert "failed to answer" in events[0].data["message"].lower()
    assert events[0].data["fallback_used"] is False
