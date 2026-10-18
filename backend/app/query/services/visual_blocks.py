"""Validation helpers for visual Markdown fences emitted by model answers."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.query.schemas.stream_events import (
    StreamCardPayload,
    StreamChartPayload,
    StreamDiagramPayload,
)

_VISUAL_FENCE_RE = re.compile(
    r"```(?P<kind>chart|card|graph|gallery)\s*\n(?P<body>[\s\S]*?)\n```", re.IGNORECASE
)

_CARD_TONES = {
    "info": "info",
    "informational": "info",
    "success": "success",
    "positive": "success",
    "warning": "warning",
    "caution": "warning",
    "error": "error",
    "negative": "error",
    "critical": "error",
    "neutral": "neutral",
}


class GalleryItem(BaseModel):
    src: str
    alt: str = "Gallery image"
    caption: str | None = None
    href: str | None = None

    model_config = ConfigDict(extra="forbid")


class GalleryPayload(BaseModel):
    id: str | None = None
    block_id: str | None = None
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=0, ge=0)
    title: str = "Gallery"
    items: list[GalleryItem] = Field(min_length=1)
    source_markdown: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    undo: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def validate_visual_block_payload(payload: dict[str, Any]) -> None:
    """Validate a block before it is persisted from an interactive client."""

    kind = str(payload.get("type") or payload.get("kind") or "").lower()
    clean_payload = {key: value for key, value in payload.items() if key not in {"type", "kind"}}
    if kind == "chart":
        chart = StreamChartPayload.model_validate({"id": "persisted-chart", **clean_payload})
        if len(chart.series) < 2 and not chart.series_groups:
            raise ValueError("chart requires at least two points or one named series")
        return
    if kind == "card":
        card = StreamCardPayload.model_validate({"id": "persisted-card", **clean_payload})
        if not card.content.strip():
            raise ValueError("card content must not be empty")
        return
    if kind == "diagram":
        StreamDiagramPayload.model_validate({"id": "persisted-diagram", **clean_payload})
        return
    if kind == "graph":
        graph = clean_payload.get("graph", clean_payload)
        StreamDiagramPayload.model_validate(
            {
                "id": "persisted-graph",
                "title": clean_payload.get("title", "Diagram canvas"),
                "diagram_type": "graph_canvas",
                "source": "graph_json",
                "syntax": "graph_json",
                "graph": graph,
            }
        )
        return
    if kind == "gallery":
        GalleryPayload.model_validate(clean_payload)
        return
    raise ValueError("unsupported visual block type")


def validate_visual_fence(kind: str, body: str) -> None:
    payload: Any = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("visual block must be a JSON object")
    normalized = kind.lower()
    if normalized == "chart":
        chart = StreamChartPayload.model_validate({"id": "markdown-chart", **payload})
        if len(chart.series) < 2:
            raise ValueError("chart requires at least two series points")
    elif normalized == "card":
        card = StreamCardPayload.model_validate({"id": "markdown-card", **payload})
        if not card.content.strip():
            raise ValueError("card content must not be empty")
    elif normalized == "graph":
        graph = payload.get("graph", payload)
        StreamDiagramPayload.model_validate(
            {
                "id": "markdown-graph",
                "title": payload.get("title", "Diagram canvas"),
                "diagram_type": "graph_canvas",
                "source": "graph_json",
                "syntax": body,
                "graph": graph,
            }
        )
    else:
        GalleryPayload.model_validate(payload)


def _normalize_visual_fence_body(kind: str, body: str) -> str:
    """Canonicalize common model-generated card tone names before validation."""

    if kind.lower() != "card":
        return body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(payload, dict):
        return body
    tone = payload.get("tone")
    if not isinstance(tone, str):
        return body
    canonical = _CARD_TONES.get(tone.strip().lower())
    if canonical is None or canonical == tone:
        return body
    payload["tone"] = canonical
    return json.dumps(payload, ensure_ascii=False, indent=2)


def normalize_visual_markdown(text: str) -> tuple[str, list[str]]:
    """Keep valid visual fences renderable and demote invalid ones to text code."""

    errors: list[str] = []

    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        body = match.group("body")
        normalized_body = _normalize_visual_fence_body(kind, body)
        try:
            validate_visual_fence(kind, normalized_body)
            if normalized_body == body:
                return match.group(0)
            return f"```{kind}\n{normalized_body}\n```"
        except Exception as exc:  # model output is untrusted; preserve it as code
            errors.append(f"{kind}: {exc}")
            return f"```text\n{body}\n```"

    return _VISUAL_FENCE_RE.sub(replace, text), errors
