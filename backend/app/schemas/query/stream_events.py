from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.query.structured_response import (
    ReasoningTraceModel,
    StructuredAnswerResponse,
)


class StreamEventCursor(BaseModel):
    """Optional cursor metadata for reconnectable streams."""

    sequence: int = Field(default=0, ge=0)
    after_sequence: int = Field(default=0, ge=0)
    has_more: bool = False

    model_config = ConfigDict(extra="forbid")


class StreamCitationPayload(BaseModel):
    document_id: str
    chunk_id: str
    filename: str
    snippet: str
    similarity_score: float
    source_type: str = "text"
    section_header: str | None = None
    page_number: int | None = None

    model_config = ConfigDict(extra="forbid")


class StreamTablePayload(BaseModel):
    id: str
    title: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StreamChartPoint(BaseModel):
    label: str
    value: float

    model_config = ConfigDict(extra="forbid")


class StreamChartPayload(BaseModel):
    id: str
    title: str | None = None
    chart_type: Literal["bar", "line"] = "bar"
    series: list[StreamChartPoint] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StreamCardPayload(BaseModel):
    id: str
    title: str
    content: str
    tone: Literal["info", "success", "warning", "error", "neutral"] = "neutral"

    model_config = ConfigDict(extra="forbid")


class StreamDiagramPayload(BaseModel):
    class GraphNode(BaseModel):
        id: str
        label: str
        category: str | None = None

        model_config = ConfigDict(extra="forbid")

    class GraphEdge(BaseModel):
        source: str
        target: str
        label: str | None = None

        model_config = ConfigDict(extra="forbid")

    class GraphPayload(BaseModel):
        nodes: list[StreamDiagramPayload.GraphNode] = Field(default_factory=list)
        edges: list[StreamDiagramPayload.GraphEdge] = Field(default_factory=list)
        layout: Literal["horizontal", "vertical", "radial"] = "horizontal"

        model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None = None
    diagram_type: Literal[
        "mermaid_flowchart",
        "mermaid_sequence",
        "mermaid_state",
        "mermaid_class",
        "mermaid_er",
        "mermaid_journey",
        "mermaid_timeline",
        "mermaid_gantt",
        "mermaid_mindmap",
        "mermaid_pie",
        "mermaid_gitgraph",
        "mermaid_quadrant",
        "mermaid_requirement",
        "mermaid_block",
        "mermaid_xychart",
        "mermaid_c4",
        "mermaid_architecture",
        "mermaid_sankey",
        "mermaid_packet",
        "mermaid_kanban",
        "graph_canvas",
    ] = "mermaid_flowchart"
    source: Literal["mermaid", "graph_json"] = "mermaid"
    syntax: str = ""
    description: str = ""
    graph: GraphPayload | None = None

    model_config = ConfigDict(extra="forbid")


class StreamMetaPayload(BaseModel):
    conversation_id: str
    trace_id: str
    message_id: str | None = None
    version_id: str | None = None
    version_index: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    cached: bool = False
    query_type: str = "factual"
    source_count: int = 0

    model_config = ConfigDict(extra="forbid")


class StreamStartPayload(BaseModel):
    message_id: str
    conversation_id: str
    started_at: str
    version_id: str | None = None
    version_index: int | None = None
    operation: Literal["new_turn", "regenerate", "edit_regenerate"] = "new_turn"

    model_config = ConfigDict(extra="forbid")


class StreamDeltaPayload(BaseModel):
    text: str

    model_config = ConfigDict(extra="forbid")


class StreamReplacePayload(BaseModel):
    content: str
    format: Literal["markdown", "structured"] = "markdown"
    structured: StructuredAnswerResponse | None = None

    model_config = ConfigDict(extra="forbid")


class StreamTracePayload(BaseModel):
    trace: ReasoningTraceModel

    model_config = ConfigDict(extra="forbid")


class StreamFollowupsPayload(BaseModel):
    items: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StreamStatusPayload(BaseModel):
    code: str | None = None
    label: str
    state: Literal["pending", "running", "completed", "error"] = "running"
    detail: str | None = None
    timestamp: str | None = None
    duration_ms: float | None = Field(default=None, ge=0.0)

    model_config = ConfigDict(extra="forbid")


class StreamFilePayload(BaseModel):
    name: str
    url: str
    type: str | None = None

    model_config = ConfigDict(extra="forbid")


class StreamFilesPayload(BaseModel):
    items: list[StreamFilePayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StreamOutputPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StreamDonePayload(BaseModel):
    completed: bool = True

    model_config = ConfigDict(extra="forbid")


class StreamErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
