from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QueryVolumePoint(BaseModel):
    date: str
    count: int

    model_config = ConfigDict(extra="forbid")


class ConfidenceDistribution(BaseModel):
    high: int
    medium: int
    low: int

    model_config = ConfigDict(extra="forbid")


class AnalyticsDashboardResponse(BaseModel):
    total_queries: int
    avg_confidence: float
    volume_over_time: list[QueryVolumePoint]
    confidence_distribution: ConfidenceDistribution
    api_latency_p95_ms: float | None = None

    model_config = ConfigDict(extra="forbid")
