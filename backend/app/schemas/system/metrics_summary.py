from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MetricsSummaryResponse(BaseModel):
    api_requests_total: int
    api_errors_total: int
    db_query_count: int

    model_config = ConfigDict(extra="forbid")
