from __future__ import annotations

from app.query.services.answer_service import AnswerService


def test_structured_output_salvage_preserves_valid_diagram_sections() -> None:
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
            {"id": "client", "label": "Client"},
            {"id": "api", "label": "API"}
          ],
          "edges": [
            {"source": "client", "target": "api", "label": "request"}
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
    assert structured.diagram.graph.nodes[1].label == "API"
