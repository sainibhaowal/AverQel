from __future__ import annotations

from app.deepspace.services.context_budget import AdaptiveContextBudget


def test_budget_protects_policy_schema_user_and_output_before_optional_context() -> None:
    budget = AdaptiveContextBudget(safety_margin_tokens=512).allocate(
        context_window=16_000,
        system_tokens=2_000,
        tool_schema_tokens=1_000,
        user_tokens=500,
        prior_tool_result_tokens=100,
        reserved_output_tokens=4_000,
    )

    assert budget.available_dynamic_tokens == 7_988
    assert budget.history_budget_tokens is not None
    assert budget.tool_result_budget_tokens is not None
    assert budget.history_budget_tokens + budget.tool_result_budget_tokens == 7_988
    assert 500 <= budget.mcp_preview_chars <= 12_000


def test_budget_shrinks_optional_capacity_without_dropping_protected_content() -> None:
    budget = AdaptiveContextBudget().allocate(
        context_window=1_000,
        system_tokens=600,
        tool_schema_tokens=300,
        user_tokens=200,
        prior_tool_result_tokens=0,
        reserved_output_tokens=512,
    )

    assert budget.available_dynamic_tokens == 0
    assert budget.history_budget_tokens == 0
    assert budget.tool_result_budget_tokens == 0
    assert budget.mcp_preview_chars == 500


def test_unknown_context_window_preserves_existing_preview_default() -> None:
    budget = AdaptiveContextBudget().allocate(
        context_window=None,
        system_tokens=2_000,
        tool_schema_tokens=1_000,
        user_tokens=100,
        prior_tool_result_tokens=5_000,
        reserved_output_tokens=2_000,
    )

    assert budget.available_dynamic_tokens is None
    assert budget.history_budget_tokens is None
    assert budget.tool_result_budget_tokens is None
    assert budget.mcp_preview_chars == 1_800


def test_workload_tuning_prioritizes_research_evidence_and_chat_history() -> None:
    common = dict(
        context_window=16_000,
        system_tokens=2_000,
        tool_schema_tokens=1_000,
        user_tokens=500,
        prior_tool_result_tokens=100,
        reserved_output_tokens=4_000,
    )

    research = AdaptiveContextBudget().allocate(**common, workload="research")
    conversation = AdaptiveContextBudget().allocate(**common, workload="conversation")

    assert research.tool_result_budget_tokens > conversation.tool_result_budget_tokens
    assert conversation.history_budget_tokens > research.history_budget_tokens
