from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MetricsSummaryResponse(BaseModel):
    api_requests_total: int
    api_errors_total: int
    db_query_count: int
    worker_retries_total: int = 0
    worker_dead_letters_total: int = 0
    deepspace_cache_reads_total: int = 0
    deepspace_cache_writes_total: int = 0
    deepspace_context_compactions_total: int = 0
    deepspace_overflow_prevented_total: int = 0
    deepspace_mcp_result_references_total: int = 0
    deepspace_budget_allocations_total: int = 0
    deepspace_result_reference_events_total: int = 0
    deepspace_execution_batches_total: int = 0
    deepspace_canary_mismatches_total: int = 0
    metrics_scope: Literal["service-wide"] = "service-wide"
    metrics_complete: bool = True
    metrics_started_at: datetime
    snapshot_at: datetime

    model_config = ConfigDict(extra="forbid")
