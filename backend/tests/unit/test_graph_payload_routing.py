from __future__ import annotations

import json

from app.services.query.answer_service import AnswerService
from app.services.query.query_classifier import QueryType


def test_graph_payload_routing_emits_diagram_event() -> None:
    payload = {
        "key_findings": ["Topology is node-edge driven."],
        "detailed_analysis": "### Graph\nTyped graph payload.",
        "diagram": {
            "title": "Runtime Graph",
            "diagram_type": "graph_canvas",
            "source": "graph_json",
            "syntax": "",
            "graph": {
                "layout": "vertical",
                "nodes": [
                    {"id": "edge", "label": "Edge"},
                    {"id": "core", "label": "Core"},
                ],
                "edges": [{"source": "edge", "target": "core"}],
            },
        },
    }

    events = list(
        AnswerService("no-result")._emit_post_stream_events(
            json.dumps(payload), QueryType.EXPLORATORY
        )
    )
    diagram = next(event for event in events if event.event == "diagram")
    assert diagram.data["title"] == "Runtime Graph"
    assert diagram.data["graph"]["layout"] == "vertical"
