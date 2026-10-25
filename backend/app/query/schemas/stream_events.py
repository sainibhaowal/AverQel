from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.query.schemas.structured_response import (
    ReasoningTraceModel,
    StructuredAnswerResponse,
)

VisualIconName = Literal[
    "sparkles",
    "lightbulb",
    "target",
    "shield",
    "layers",
    "zap",
    "globe",
    "chart",
    "check",
    "clock",
    "map-pin",
    "building",
    "users",
    "database",
    "cloud",
    "code",
    "star",
    "heart",
    "phone",
    "calendar",
    "landmark",
    "compass",
    "info",
]


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
    z: float | None = None

    model_config = ConfigDict(extra="allow")


class StreamChartSeries(BaseModel):
    """Named chart series used by multi-series visualizations."""

    name: str = Field(min_length=1, max_length=120)
    points: list[StreamChartPoint] = Field(default_factory=list)
    axis: Literal["left", "right"] = "left"
    color: str | None = None
    visible: bool = True

    model_config = ConfigDict(extra="forbid")


class StreamChartAnnotation(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    x: str | float | int
    y: float | int | None = None
    color: str | None = None

    model_config = ConfigDict(extra="forbid")


class StreamChartPayload(BaseModel):
    id: str
    title: str | None = None
    chart_type: Literal["bar", "line", "area", "scatter", "pie"] = "bar"
    series: list[StreamChartPoint] = Field(default_factory=list)
    series_groups: list[StreamChartSeries] = Field(default_factory=list)
    annotations: list[StreamChartAnnotation] = Field(default_factory=list)
    legend: bool = True
    secondary_y_label: str | None = None
    raw_payload: str | None = None
    parser_source: Literal["json", "pattern", "structured"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    fields: list[str] = Field(default_factory=list)
    is_streaming: bool = False
    x_key: str | None = None
    y_key: str | None = None
    z_key: str | None = None
    equation: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    block_id: str | None = None
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    source_markdown: str | None = None
    source_mermaid: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    undo: dict[str, Any] = Field(default_factory=dict)
    visual_model: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class StreamCardPayload(BaseModel):
    class Metric(BaseModel):
        label: str
        value: str | int | float
        detail: str | None = None

        model_config = ConfigDict(extra="forbid")

    class Score(BaseModel):
        value: float = Field(ge=0, allow_inf_nan=False)
        max: float = Field(gt=0, allow_inf_nan=False)
        tone: Literal["info", "success", "warning", "error", "neutral"] = "warning"

        model_config = ConfigDict(extra="forbid")

        @model_validator(mode="after")
        def value_must_not_exceed_max(self) -> Any:
            if self.value > self.max:
                raise ValueError("score value must not exceed its maximum")
            return self

    class Action(BaseModel):
        label: str
        href: str | None = None
        action: Literal["open", "copy", "download"] = "open"
        content: str | None = None

        model_config = ConfigDict(extra="forbid")

    class Detail(BaseModel):
        label: str = Field(min_length=1, max_length=80)
        value: str = Field(min_length=1, max_length=500)
        icon: VisualIconName | None = None
        href: str | None = Field(default=None, max_length=2048)

        model_config = ConfigDict(extra="forbid")

    class Source(BaseModel):
        title: str = Field(min_length=1, max_length=160)
        url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")

        model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    content: str = ""
    tone: Literal["info", "success", "warning", "error", "neutral"] = "neutral"
    layout: Literal["standard", "feature", "place", "evaluation", "referral"] = "standard"
    subtitle: str | None = None
    image_url: str | None = None
    image_alt: str | None = Field(default=None, max_length=300)
    icon: VisualIconName | None = None
    href: str | None = None
    metrics: list[Metric] = Field(default_factory=list)
    score: Score | None = None
    primary_metric: Metric | None = None
    code: str | None = Field(default=None, max_length=100)
    actions: list[Action] = Field(default_factory=list)
    details: list[Detail] = Field(default_factory=list, max_length=8)
    sources: list[Source] = Field(default_factory=list, max_length=8)
    incomplete: bool = False
    block_id: str | None = None
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    source_markdown: str | None = None
    source_mermaid: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    undo: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_sources_for_place_layout(self) -> StreamCardPayload:
        if self.layout == "place" and not self.sources:
            raise ValueError("place cards require at least one source URL")
        if self.layout == "evaluation":
            if self.score is None:
                raise ValueError("evaluation cards require a score")
            if not self.metrics:
                raise ValueError("evaluation cards require at least one supporting metric")
        if self.layout == "referral":
            if self.primary_metric is None:
                raise ValueError("referral cards require a primary metric")
            if not self.details:
                raise ValueError("referral cards require at least one terms detail")
        return self


class StreamInfographicPayload(BaseModel):
    class Item(BaseModel):
        title: str = Field(min_length=1, max_length=120)
        description: str | None = Field(default=None, max_length=600)
        value: str | int | float | None = None
        date: str | None = Field(default=None, max_length=300)
        icon: VisualIconName | None = None
        image_url: str | None = Field(default=None, max_length=2048)

        model_config = ConfigDict(extra="forbid")

    class Source(BaseModel):
        title: str = Field(min_length=1, max_length=160)
        url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")

        model_config = ConfigDict(extra="forbid")

    id: str
    title: str = Field(min_length=1, max_length=180)
    subtitle: str | None = Field(default=None, max_length=300)
    layout: Literal["steps", "timeline", "comparison", "feature_grid", "stats"]
    direction: Literal["LR", "RL", "TD", "DT"] = "LR"
    items: list[Item] = Field(min_length=2, max_length=8)
    note: str | None = Field(default=None, max_length=500)
    sources: list[Source] = Field(default_factory=list, max_length=8)
    block_id: str | None = None
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    source_markdown: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    undo: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_layout_items(self) -> StreamInfographicPayload:
        if self.layout == "timeline" and any(not item.date for item in self.items):
            raise ValueError("timeline items require a date or period label")
        if self.layout == "stats" and any(item.value is None for item in self.items):
            raise ValueError("statistics items require a value")
        return self


class StreamDiagramPayload(BaseModel):
    class GraphNode(BaseModel):
        id: str
        label: str
        category: str | None = None
        x: float | None = None
        y: float | None = None
        width: float | None = Field(default=None, gt=0)
        height: float | None = Field(default=None, gt=0)
        group_id: str | None = None

        model_config = ConfigDict(extra="forbid")

    class GraphEdge(BaseModel):
        source: str
        target: str
        label: str | None = None
        style: Literal["solid", "dashed", "dotted"] = "solid"

        model_config = ConfigDict(extra="forbid")

    class GraphPayload(BaseModel):
        class Drawing(BaseModel):
            d: str
            color: str | None = None
            width: float | None = Field(default=None, gt=0)

            model_config = ConfigDict(extra="forbid")

        nodes: list[StreamDiagramPayload.GraphNode] = Field(default_factory=list)
        edges: list[StreamDiagramPayload.GraphEdge] = Field(default_factory=list)
        layout: Literal["horizontal", "vertical", "radial"] = "horizontal"
        drawings: list[Drawing] = Field(default_factory=list)

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
    incomplete: bool = False
    graph: GraphPayload | None = None
    block_id: str | None = None
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    source_markdown: str | None = None
    source_mermaid: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    undo: dict[str, Any] = Field(default_factory=dict)
    visual_model: dict[str, Any] = Field(default_factory=dict)

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
