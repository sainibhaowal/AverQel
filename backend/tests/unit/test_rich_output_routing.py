from __future__ import annotations

import json
from typing import Any

from app.query.services.answer_service import AnswerService
from app.query.services.query_classifier import QueryType


def test_emit_post_stream_events_from_structured_json() -> None:
    payload = {
        "key_findings": ["Architecture has three stages"],
        "detailed_analysis": "### System Flow\nThe request moves through ingest, retrieve, and answer.",
        "limitations": "Limited to the provided documents.",
        "conclusion": "The architecture is retrieval-first.",
        "confidence_score": 0.82,
        "follow_up_suggestions": ["What are the bottlenecks?"],
        "comparison_table": {
            "title": "Stage Comparison",
            "headers": ["Stage", "Role"],
            "rows": [["Ingest", "Prepare data"], ["Retrieve", "Find evidence"]],
        },
        "chart": {
            "title": "Latency Split",
            "chart_type": "bar",
            "series": [
                {"label": "Retrieve", "value": 120},
                {"label": "Answer", "value": 340},
            ],
        },
        "diagram": {
            "title": "Pipeline",
            "diagram_type": "mermaid_flowchart",
            "source": "mermaid",
            "syntax": "flowchart LR\nA[Ingest] --> B[Retrieve] --> C[Answer]",
            "description": "High-level request flow.",
        },
    }

    events = list(
        AnswerService("no-result")._emit_post_stream_events(
            json.dumps(payload),
            QueryType.SYNTHESIS,
        )
    )

    event_names = [event.event for event in events]
    assert event_names == [
        "replace",
        "table",
        "chart",
        "diagram",
        "followups",
        "done",
    ]

    replace_event = events[0]
    assert replace_event.data["format"] == "structured"
    assert replace_event.data["structured"]["diagram"]["diagram_type"] == "mermaid_flowchart"

    diagram_event = next(event for event in events if event.event == "diagram")
    assert diagram_event.data["title"] == "Pipeline"
    assert "flowchart LR" in diagram_event.data["syntax"]


def test_extract_diagram_payloads_from_mermaid_markdown() -> None:
    text = """
### Architecture

```mermaid
flowchart LR
A[Client] --> B[API]
B --> C[Retriever]
```
"""
    payloads = AnswerService._extract_diagram_payloads(text)
    assert len(payloads) == 1
    assert payloads[0]["diagram_type"] == "mermaid_flowchart"
    assert "A[Client] --> B[API]" in payloads[0]["syntax"]
    assert payloads[0]["incomplete"] is False


def test_extract_diagram_payloads_from_incomplete_mermaid_markdown() -> None:
    text = """
### Architecture

```mermaid
flowchart LR
A[Client] --> B[API]
"""
    payloads = AnswerService._extract_diagram_payloads(text)
    assert len(payloads) == 1
    assert payloads[0]["diagram_type"] == "mermaid_flowchart"
    assert payloads[0]["incomplete"] is True


def test_extract_diagram_payloads_ignores_invalid_mermaid_markdown() -> None:
    text = """
### Architecture

```mermaid
diagram TD
A[Client] --> B[API]
```
"""
    payloads = AnswerService._extract_diagram_payloads(text)
    assert payloads == []


def test_extract_diagram_payloads_detects_er_mermaid_markdown() -> None:
    text = """
### Data model

```mermaid
erDiagram
Document ||--o{ Chunk : contains
Collection ||--o{ Document : groups
```
"""
    payloads = AnswerService._extract_diagram_payloads(text)
    assert len(payloads) == 1
    assert payloads[0]["diagram_type"] == "mermaid_er"


def test_extract_diagram_payloads_detects_state_mermaid_markdown() -> None:
    text = """
```mermaid
stateDiagram-v2
[*] --> Uploaded
Uploaded --> Parsing
```
"""
    payloads = AnswerService._extract_diagram_payloads(text)
    assert len(payloads) == 1
    assert payloads[0]["diagram_type"] == "mermaid_state"


def test_extract_diagram_payloads_detects_c4_mermaid_markdown() -> None:
    text = """
```mermaid
C4Context
Person(user, "User")
System(app, "AverQel")
Rel(user, app, "Uses")
```
"""

    payloads = AnswerService._extract_diagram_payloads(text)
    assert len(payloads) == 1
    assert payloads[0]["diagram_type"] == "mermaid_c4"


def test_extract_diagram_payloads_detects_xychart_mermaid_markdown() -> None:
    text = """
```mermaid
xychart-beta
title "Latency"
x-axis [Retrieve, Answer]
bar [120, 340]
```
"""

    payloads = AnswerService._extract_diagram_payloads(text)
    assert len(payloads) == 1
    assert payloads[0]["diagram_type"] == "mermaid_xychart"


def test_progressive_card_payloads_are_not_emitted_from_markdown_sections() -> None:
    service = AnswerService("no-result")
    emitted_payloads: dict[str, dict[str, Any]] = {
        "table": {},
        "chart": {},
        "diagram": {},
        "card": {},
    }

    events = list(
        service._emit_progressive_rich_events(
            full_text="### Key Findings\n- Strong evidence\n\n### Limitations\nOCR is noisy\n",
            emitted_payloads=emitted_payloads,
        )
    )

    assert [event.event for event in events] == []


def test_progressive_table_payload_re_emits_when_rows_expand() -> None:
    service = AnswerService("no-result")
    emitted_payloads: dict[str, dict[str, Any]] = {
        "table": {},
        "chart": {},
        "diagram": {},
        "card": {},
    }

    first = list(
        service._emit_progressive_rich_events(
            full_text="| Stage | Role |\n| --- | --- |\n| Ingest | Parse |\n",
            emitted_payloads=emitted_payloads,
        )
    )
    assert [event.event for event in first] == ["table"]
    assert first[0].data["id"] == "table-1"
    assert len(first[0].data["rows"]) == 1

    second = list(
        service._emit_progressive_rich_events(
            full_text="| Stage | Role |\n| --- | --- |\n| Ingest | Parse |\n| Retrieve | Rank |\n",
            emitted_payloads=emitted_payloads,
        )
    )
    assert [event.event for event in second] == ["table"]
    assert second[0].data["id"] == "table-1"
    assert len(second[0].data["rows"]) == 2


def test_emit_post_stream_events_extracts_markdown_followups() -> None:
    text = """### Summary
The architecture uses a retrieval-first flow.

---suggestions---
What are the bottlenecks?
Show the sequence diagram.
Compare hosted vs local deployment.
"""

    events = list(
        AnswerService("no-result")._emit_post_stream_events(
            text,
            QueryType.SYNTHESIS,
        )
    )

    replace_event = next(event for event in events if event.event == "replace")
    assert "---suggestions---" not in replace_event.data["content"]

    followups_event = next(event for event in events if event.event == "followups")
    assert followups_event.data["items"] == [
        "What are the bottlenecks?",
        "Show the sequence diagram.",
        "Compare hosted vs local deployment.",
    ]


def test_emit_post_stream_events_extracts_malformed_markdown_followups() -> None:
    text = """The document does not support that claim.

*suggestions---
What are the key mechanistic effects?
How does context length change results?
Does it discuss boundary resetting?
"""

    events = list(
        AnswerService("no-result")._emit_post_stream_events(
            text,
            QueryType.SYNTHESIS,
        )
    )

    replace_event = next(event for event in events if event.event == "replace")
    assert "*suggestions---" not in replace_event.data["content"]
    assert replace_event.data["content"] == "The document does not support that claim."

    followups_event = next(event for event in events if event.event == "followups")
    assert followups_event.data["items"] == [
        "What are the key mechanistic effects?",
        "How does context length change results?",
        "Does it discuss boundary resetting?",
    ]


def test_emit_post_stream_events_from_graph_json_diagram() -> None:
    payload = {
        "key_findings": ["Service boundaries are explicit."],
        "detailed_analysis": "### Topology\nThe request moves across three services.",
        "limitations": "",
        "conclusion": "The graph clarifies dependencies.",
        "confidence_score": 0.76,
        "follow_up_suggestions": ["Which service is the bottleneck?"],
        "diagram": {
            "title": "Service Graph",
            "diagram_type": "graph_canvas",
            "source": "graph_json",
            "syntax": "",
            "description": "High-level service dependencies.",
            "graph": {
                "layout": "horizontal",
                "nodes": [
                    {"id": "client", "label": "Client", "category": "edge"},
                    {"id": "api", "label": "API", "category": "service"},
                    {"id": "retriever", "label": "Retriever", "category": "service"},
                ],
                "edges": [
                    {"source": "client", "target": "api", "label": "request"},
                    {"source": "api", "target": "retriever", "label": "search"},
                ],
            },
        },
    }

    events = list(
        AnswerService("no-result")._emit_post_stream_events(
            json.dumps(payload), QueryType.SYNTHESIS
        )
    )
    diagram_event = next(event for event in events if event.event == "diagram")

    assert diagram_event.data["diagram_type"] == "graph_canvas"
    assert diagram_event.data["source"] == "graph_json"
    assert diagram_event.data["graph"]["nodes"][1]["label"] == "API"
