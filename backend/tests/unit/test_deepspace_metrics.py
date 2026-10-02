from prometheus_client import generate_latest

from app.system.services.metrics_service import (
    DEEPSPACE_BUDGET_ALLOCATIONS_TOTAL,
    DEEPSPACE_CACHE_USAGE_TOTAL,
    DEEPSPACE_CANARY_MISMATCHES_TOTAL,
    DEEPSPACE_CONTEXT_COMPACTIONS_TOTAL,
    DEEPSPACE_CONTEXT_OVERFLOW_PREVENTED_TOTAL,
    DEEPSPACE_EXECUTION_BATCHES_TOTAL,
    DEEPSPACE_MCP_RESULT_REFERENCES_TOTAL,
    DEEPSPACE_RESULT_REFERENCE_EVENTS_TOTAL,
)


def test_deepspace_monitoring_counters_are_registered() -> None:
    DEEPSPACE_CACHE_USAGE_TOTAL.labels(provider="test", status="read").inc()
    DEEPSPACE_CONTEXT_COMPACTIONS_TOTAL.labels(reason="context_fit").inc()
    DEEPSPACE_CONTEXT_OVERFLOW_PREVENTED_TOTAL.labels(action="compaction").inc()
    DEEPSPACE_MCP_RESULT_REFERENCES_TOTAL.inc()
    DEEPSPACE_BUDGET_ALLOCATIONS_TOTAL.labels(workload="balanced", context_tier="large").inc()
    DEEPSPACE_RESULT_REFERENCE_EVENTS_TOTAL.labels(kind="native", status="created").inc()
    DEEPSPACE_EXECUTION_BATCHES_TOTAL.labels(mode="planned").inc()
    DEEPSPACE_CANARY_MISMATCHES_TOTAL.inc(0)

    payload = generate_latest().decode("utf-8")
    assert "aks_deepspace_cache_usage_total" in payload
    assert "aks_deepspace_context_compactions_total" in payload
    assert "aks_deepspace_context_overflow_prevented_total" in payload
    assert "aks_deepspace_mcp_result_references_total" in payload
    assert "aks_deepspace_budget_allocations_total" in payload
    assert "aks_deepspace_result_reference_events_total" in payload
    assert "aks_deepspace_execution_batches_total" in payload
    assert "aks_deepspace_canary_mismatches_total" in payload
