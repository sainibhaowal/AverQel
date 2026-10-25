"""Validation helpers for visual Markdown fences emitted by model answers."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.query.schemas.stream_events import (
    StreamCardPayload,
    StreamChartPayload,
    StreamDiagramPayload,
    StreamInfographicPayload,
)

_VISUAL_FENCE_RE = re.compile(
    r"```(?P<kind>chart|card|graph|gallery|infographic)\s*\n(?P<body>[\s\S]*?)\n```",
    re.IGNORECASE,
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
        if not card.content.strip() and card.layout not in {"evaluation", "referral"}:
            raise ValueError("card content must not be empty")
        return
    if kind == "infographic":
        StreamInfographicPayload.model_validate({"id": "persisted-infographic", **clean_payload})
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
        if not card.content.strip() and card.layout not in {"evaluation", "referral"}:
            raise ValueError("card content must not be empty")
    elif normalized == "infographic":
        StreamInfographicPayload.model_validate({"id": "markdown-infographic", **payload})
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
    """Canonicalize common model-generated visual field aliases before validation."""

    normalized_kind = kind.lower()
    if normalized_kind not in {"card", "infographic"}:
        return body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(payload, dict):
        return body
    changed = False
    if normalized_kind == "card":
        tone = payload.get("tone")
        if isinstance(tone, str):
            canonical = _CARD_TONES.get(tone.strip().lower())
            if canonical is not None and canonical != tone:
                payload["tone"] = canonical
                changed = True

        details = payload.get("details")
        if isinstance(details, list):
            normalized_details: list[Any] = []
            for detail in details:
                if not isinstance(detail, str):
                    normalized_details.append(detail)
                    continue
                match = re.match(
                    r"^\s*\*\*([^:*]{1,80}):\*\*\s*(.+?)\s*$|" r"^\s*([^:*]{1,80}):\s*(.+?)\s*$",
                    detail,
                )
                if match is None:
                    normalized_details.append(detail)
                    continue
                label, value = match.group(1) or match.group(3), match.group(2) or match.group(4)
                normalized_details.append({"label": label.strip(), "value": value.strip()})
                changed = True
            if normalized_details != details:
                payload["details"] = normalized_details

    sources = payload.get("sources")
    if isinstance(sources, list):
        normalized_sources: list[Any] = []
        for source in sources:
            if isinstance(source, str):
                match = re.fullmatch(r"\s*\[([^\]]+)\]\((https?://[^)]+)\)\s*", source)
                if match is not None:
                    normalized_sources.append({"title": match.group(1), "url": match.group(2)})
                    changed = True
                    continue
            if isinstance(source, dict) and ("label" in source or "href" in source):
                title = source.get("title") or source.get("label")
                url = source.get("url") or source.get("href")
                if isinstance(title, str) and isinstance(url, str):
                    normalized_sources.append({"title": title, "url": url})
                    changed = True
                    continue
            normalized_sources.append(source)
        if normalized_sources != sources:
            payload["sources"] = normalized_sources

    return json.dumps(payload, ensure_ascii=False, indent=2) if changed else body


def _infer_visual_json_kind(language: str, body: str) -> str | None:
    normalized_language = language.lower()
    visual_languages = {"chart", "card", "graph", "gallery", "infographic"}
    if normalized_language and normalized_language not in {"json", *visual_languages}:
        return None
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if normalized_language in visual_languages:
        return normalized_language
    graph = payload.get("graph")
    if (
        isinstance(graph, dict)
        and isinstance(graph.get("nodes"), list)
        and isinstance(graph.get("edges"), list)
    ):
        return "graph"
    if isinstance(payload.get("nodes"), list) and isinstance(payload.get("edges"), list):
        return "graph"
    items = payload.get("items")
    if isinstance(items, list) and any(
        isinstance(item, dict) and isinstance(item.get("src"), str) for item in items
    ):
        return "gallery"
    if (
        isinstance(payload.get("title"), str)
        and payload.get("layout") in {"steps", "timeline", "comparison", "feature_grid", "stats"}
        and isinstance(items, list)
        and len(items) >= 2
        and all(isinstance(item, dict) and isinstance(item.get("title"), str) for item in items)
    ):
        return "infographic"
    if (
        isinstance(payload.get("chart_type"), str)
        or isinstance(payload.get("series"), list)
        or isinstance(payload.get("chart_data"), list)
        or isinstance(payload.get("chartData"), list)
    ):
        return "chart"
    if isinstance(payload.get("title"), str) and (
        isinstance(payload.get("content"), str)
        or isinstance(payload.get("body"), str)
        or (
            payload.get("layout") == "evaluation"
            and isinstance(payload.get("score"), dict)
            and isinstance(payload.get("metrics"), list)
        )
        or (
            payload.get("layout") == "referral"
            and isinstance(payload.get("primary_metric"), dict)
            and isinstance(payload.get("details"), list)
        )
    ):
        return "card"
    return None


def _repair_mismatched_visual_fences(text: str) -> str:
    """Recover valid visual JSON from malformed or nested Markdown fences."""

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = _unwrap_outer_markdown_fence(normalized_text).split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        opening = re.match(r"^([ \t]*)(`{3,}|~{3,})(.*)$", line)
        if opening is None:
            output.append(line)
            index += 1
            continue

        marker = opening.group(2)
        info = opening.group(3)
        if marker.startswith("`") and "`" in info:
            output.append(line)
            index += 1
            continue
        language = info.strip().split(maxsplit=1)[0].lower() if info.strip() else ""
        json_like_languages = {"", "json", "markdown", "md", "text", "txt", "plaintext"}
        if language not in json_like_languages and language not in {
            "chart",
            "card",
            "graph",
            "gallery",
            "infographic",
        }:
            output.append(line)
            index += 1
            continue

        proper_close: int | None = None
        for close_index in range(index + 1, len(lines)):
            closing = re.match(r"^([ \t]*)(`{3,}|~{3,})[ \t]*$", lines[close_index])
            if (
                closing is not None
                and closing.group(2)[0] == marker[0]
                and len(closing.group(1)) <= 3
                and len(closing.group(2)) >= len(marker)
            ):
                proper_close = close_index
                break

        body_end = proper_close if proper_close is not None else len(lines)
        body = "\n".join(lines[index + 1 : body_end])
        extracted = _extract_leading_visual_json(body)
        if extracted is not None:
            kind, visual_json, json_end = extracted
            normalized_body = _normalize_visual_fence_body(kind, visual_json)
            is_valid_visual = True
            try:
                validate_visual_fence(kind, normalized_body)
            except (ValidationError, ValueError, TypeError):
                is_valid_visual = False
            if is_valid_visual:
                tail_lines = body[json_end:].split("\n")
                if tail_lines and tail_lines[0] == "":
                    tail_lines.pop(0)
                first_content_line = next(
                    (position for position, value in enumerate(tail_lines) if value.strip()),
                    None,
                )
                if first_content_line is not None and re.fullmatch(
                    r"[`~]{3,}", tail_lines[first_content_line].strip()
                ):
                    tail_lines.pop(first_content_line)
                if proper_close is None:
                    last_content_line = next(
                        (
                            position
                            for position in range(len(tail_lines) - 1, -1, -1)
                            if tail_lines[position].strip()
                        ),
                        None,
                    )
                    if last_content_line is not None and re.fullmatch(
                        r"[`~]{3,}", tail_lines[last_content_line].strip()
                    ):
                        tail_lines.pop(last_content_line)
                output.extend([f"```{kind}", *normalized_body.split("\n"), "```", *tail_lines])
                if proper_close is not None:
                    output.extend(lines[proper_close + 1 :])
                    index = len(lines)
                else:
                    index = len(lines)
                continue

        if proper_close is not None:
            output.extend(lines[index : proper_close + 1])
            index = proper_close + 1
            continue
        output.extend(lines[index:])
        break

    return "\n".join(output)


def _unwrap_outer_markdown_fence(text: str) -> str:
    lines = text.split("\n")
    first = next((index for index, value in enumerate(lines) if value.strip()), None)
    last = next((index for index in range(len(lines) - 1, -1, -1) if lines[index].strip()), None)
    if first is None or last is None:
        return text
    opening = re.match(r"^\s*(`{3,}|~{3,})\s*(?:markdown|md)\s*$", lines[first], re.IGNORECASE)
    closing = re.match(r"^\s*(`{3,}|~{3,})\s*$", lines[last])
    if (
        opening is None
        or closing is None
        or opening.group(1)[0] != closing.group(1)[0]
        or len(closing.group(1)) < 3
    ):
        return text
    return "\n".join([*lines[:first], *lines[first + 1 : last], *lines[last + 1 :]])


def _extract_leading_visual_json(value: str) -> tuple[str, str, int] | None:
    leading = len(value) - len(value.lstrip())
    if leading >= len(value) or value[leading] != "{":
        return None
    try:
        payload, end = json.JSONDecoder().raw_decode(value[leading:])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    visual_json = value[leading : leading + end]
    kind = _infer_visual_json_kind("json", visual_json)
    return (kind, visual_json, leading + end) if kind is not None else None


def normalize_visual_markdown(text: str) -> tuple[str, list[str]]:
    """Keep valid visual fences renderable and demote invalid ones to text code."""

    errors: list[str] = []
    text = _repair_mismatched_visual_fences(text)

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
