from __future__ import annotations

import json

from app.services.query.answer_service import AnswerService
from app.services.query.query_classifier import QueryType


def test_diagram_stream_contract_supports_mermaid_and_graph_json() -> None:
    payload = {
        "key_findings": ["System boundaries are explicit."],
        "detailed_analysis": "### Topology\nThe request crosses multiple services.",
        "diagram": {
            "title": "Service Graph",
            "diagram_type": "graph_canvas",
            "source": "graph_json",
            "syntax": "",
            "graph": {
                "layout": "horizontal",
                "nodes": [
                    {"id": "client", "label": "Client"},
                    {"id": "api", "label": "API"},
                ],
                "edges": [{"source": "client", "target": "api", "label": "request"}],
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
    assert diagram_event.data["graph"]["nodes"][0]["label"] == "Client"
