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
    suppressed: bool
    total_queries: int | None
    avg_confidence: float | None
    volume_over_time: list[QueryVolumePoint]
    confidence_distribution: ConfidenceDistribution | None

    model_config = ConfigDict(extra="forbid")
