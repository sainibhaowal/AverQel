"""Contract coverage for the lightweight query/workspace stream schemas."""

from datetime import UTC, datetime
from uuid import uuid4

from app.query.schemas.stream_events import (
    StreamCardPayload,
    StreamChartPayload,
    StreamChartPoint,
    StreamCitationPayload,
    StreamDeltaPayload,
    StreamDiagramPayload,
    StreamDonePayload,
    StreamErrorPayload,
    StreamEventCursor,
    StreamFilePayload,
    StreamFilesPayload,
    StreamFollowupsPayload,
    StreamMetaPayload,
    StreamOutputPayload,
    StreamReplacePayload,
    StreamStartPayload,
    StreamStatusPayload,
    StreamTablePayload,
    StreamTracePayload,
)
from app.query.schemas.structured_response import ReasoningTraceModel
from app.query.schemas.workspace import (
    CommentCreate,
    CommentResponse,
    PinFindingRequest,
    PinnedFindingResponse,
    ShareQueryRequest,
)


def test_workspace_schemas_accept_valid_payloads() -> None:
    query_id, chunk_id, user_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    assert ShareQueryRequest(user_ids=[user_id]).user_ids == [user_id]
    assert PinFindingRequest(query_id=query_id, chunk_id=chunk_id, notes="note").notes == "note"
    pinned = PinnedFindingResponse(
        id=uuid4(), query_id=query_id, chunk_id=chunk_id, notes="n", created_at=now
    )
    assert pinned.created_at == now
    comment = CommentCreate(target_type="query", target_id=query_id, content="hello")
    assert comment.parent_id is None
    response = CommentResponse(
        id=uuid4(),
        user_id=user_id,
        target_type="finding",
        target_id=chunk_id,
        parent_id=None,
        content="hello",
        created_at=now,
        updated_at=now,
    )
    assert response.target_type == "finding"


def test_stream_schemas_cover_defaults_and_nested_payloads() -> None:
    assert StreamEventCursor().sequence == 0
    citation = StreamCitationPayload(
        document_id="d", chunk_id="c", filename="a.md", snippet="s", similarity_score=0.5
    )
    table = StreamTablePayload(id="t", headers=["a"], rows=[["b"]])
    chart = StreamChartPayload(id="c", series=[StreamChartPoint(label="x", value=1)])
    node = StreamDiagramPayload.GraphNode(id="n", label="Node")
    edge = StreamDiagramPayload.GraphEdge(source="n", target="n")
    diagram = StreamDiagramPayload(
        id="d",
        source="graph_json",
        diagram_type="graph_canvas",
        graph=StreamDiagramPayload.GraphPayload(nodes=[node], edges=[edge]),
    )
    assert citation.source_type == "text"
    assert table.rows == [["b"]]
    assert chart.chart_type == "bar"
    assert diagram.graph is not None

    assert StreamCardPayload(id="card", title="T", content="C").tone == "neutral"
    assert StreamDeltaPayload(text="delta").text == "delta"
    assert StreamReplacePayload(content="**markdown**").format == "markdown"
    assert StreamFollowupsPayload(items=["next"]).items == ["next"]
    meta = StreamMetaPayload(conversation_id="conv", trace_id="trace", confidence=1)
    assert meta.cached is False
    start = StreamStartPayload(message_id="m", conversation_id="c", started_at="now")
    assert start.operation == "new_turn"
    status = StreamStatusPayload(label="working")
    assert status.state == "running"
    file_payload = StreamFilePayload(name="a.txt", url="/a")
    assert StreamFilesPayload(items=[file_payload]).items[0].name == "a.txt"
    assert StreamOutputPayload(items=[{"ok": True}]).items[0]["ok"] is True
    assert StreamDonePayload().completed is True
    assert StreamErrorPayload(code="E", message="failed").details == {}


def test_stream_trace_payload_accepts_reasoning_trace() -> None:
    trace = ReasoningTraceModel()
    assert StreamTracePayload(trace=trace).trace.chunks_searched == 0
