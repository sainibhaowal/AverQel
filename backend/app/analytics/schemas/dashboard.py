from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DashboardStatsResponse(BaseModel):
    total_documents: int
    total_queries: int
    storage_used_bytes: int
    active_jobs: int

    model_config = ConfigDict(extra="forbid")


class DashboardDocumentBreakdownResponse(BaseModel):
    indexed: int
    processing: int
    failed: int
    queued: int
    quarantined: int

    model_config = ConfigDict(extra="forbid")


class DashboardRecentDocumentResponse(BaseModel):
    document_id: UUID
    filename: str
    status: str
    processing_progress: int
    size_bytes: int
    created_at: datetime
    extraction_method: str | None = None
    collection_names: list[str]

    model_config = ConfigDict(extra="forbid")


class DashboardProviderRuntimeResponse(BaseModel):
    feature_scope: str
    provider_display_name: str
    provider_type: str
    model_name: str
    health_status: str | None = None
    latency_ms: int | None = None

    model_config = ConfigDict(extra="forbid")


class DashboardCollectionSummaryResponse(BaseModel):
    collection_id: UUID
    name: str
    document_count: int
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class DashboardActivityItemResponse(BaseModel):
    id: UUID
    action: str
    status: str
    resource_type: str
    resource_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class DashboardOverviewResponse(BaseModel):
    stats: DashboardStatsResponse
    document_breakdown: DashboardDocumentBreakdownResponse
    recent_documents: list[DashboardRecentDocumentResponse]
    provider_runtimes: list[DashboardProviderRuntimeResponse]
    collections: list[DashboardCollectionSummaryResponse]
    recent_activity: list[DashboardActivityItemResponse]

    model_config = ConfigDict(extra="forbid")
