from __future__ import annotations

from app.services.query.answer_service import AnswerService
from app.services.query.query_classifier import QueryType


def test_prompt_rich_output_routing_prefers_expected_artifacts() -> None:
    comparison = AnswerService._build_structured_output_instruction(
        query="Compare retrieval latency across services in a table",
        query_type=QueryType.COMPARISON,
    )
    trend = AnswerService._build_structured_output_instruction(
        query="Show the latency trend over time as a chart",
        query_type=QueryType.FACTUAL,
    )
    architecture = AnswerService._build_structured_output_instruction(
        query="Show a system dependency graph of client, api, and retriever nodes",
        query_type=QueryType.EXPLORATORY,
    )
    synthesis = AnswerService._build_structured_output_instruction(
        query="Summarize the risks and next steps from these findings",
        query_type=QueryType.SYNTHESIS,
    )

    assert "comparison_table must be filled" in comparison
    assert "chart must be filled" in trend
    assert "graph_json" in architecture and "graph_canvas" in architecture
    assert "follow_up_suggestions" in synthesis
