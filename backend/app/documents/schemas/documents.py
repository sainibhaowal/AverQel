from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    status: str
    ingestion_job_id: UUID

    model_config = ConfigDict(extra="forbid")


class DocumentMetadataResponse(BaseModel):
    document_id: UUID
    status: str
    processing_progress: int = 0
    quarantined: bool = False
    information_yield: float | None = None
    extraction_method: str | None = None
    extraction_coverage_score: float | None = None
    extraction_ocr_used: bool = False
    extraction_vision_used: bool = False
    extraction_warnings: list[str] = Field(default_factory=list)
    extraction_confidence_band: str = "low"
    filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    storage_bucket: str
    storage_object_key: str
    version: int = 1
    parent_document_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[dict[str, str]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DocumentListResponse(BaseModel):
    items: list[DocumentMetadataResponse]
    total: int = 0
    skip: int = 0
    limit: int = 100

    model_config = ConfigDict(extra="forbid")


class DuplicateDocumentGroup(BaseModel):
    sha256_hash: str
    size_bytes: int
    documents: list[DocumentMetadataResponse]

    model_config = ConfigDict(extra="forbid")


class DuplicateDocumentResponse(BaseModel):
    groups: list[DuplicateDocumentGroup]
    total_duplicate_documents: int

    model_config = ConfigDict(extra="forbid")


class DocumentVersionHistory(BaseModel):
    document_id: UUID
    version: int
    created_at: datetime
    sha256_hash: str
    status: str

    model_config = ConfigDict(extra="forbid")


class DocumentVersionsResponse(BaseModel):
    root_document_id: UUID
    versions: list[DocumentVersionHistory]

    model_config = ConfigDict(extra="forbid")


class DocumentVersionDiffResponse(BaseModel):
    from_document_id: UUID
    to_document_id: UUID
    from_version: int
    to_version: int
    changed: bool
    unified_diff: str

    model_config = ConfigDict(extra="forbid")


class DocumentAIActionRequest(BaseModel):
    action: Literal["summarize", "extract", "faqs", "compare"]
    instruction: str | None = Field(default=None, max_length=2000)
    compare_document_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class DocumentAIActionResponse(BaseModel):
    action_id: UUID | None = None
    action: str
    answer: Any
    confidence: float
    citations: list[dict[str, Any]]
    trace_id: str

    model_config = ConfigDict(extra="forbid")


class DocumentCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    parent_id: UUID | None = None
    mentions: list[UUID] = Field(default_factory=list, max_length=20)
    model_config = ConfigDict(extra="forbid")


class DocumentCommentUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    mentions: list[UUID] = Field(default_factory=list, max_length=20)
    model_config = ConfigDict(extra="forbid")


class DocumentShareLinkCreate(BaseModel):
    expires_in_seconds: int = Field(default=86_400, ge=300, le=2_592_000)
    model_config = ConfigDict(extra="forbid")


class DocumentShareLinkResponse(BaseModel):
    id: UUID
    document_id: UUID
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    share_token: str | None = None
    model_config = ConfigDict(extra="forbid")


class DocumentShareLinkResolveResponse(BaseModel):
    document_id: UUID
    filename: str
    content_type: str
    expires_at: datetime
    content: str
    model_config = ConfigDict(extra="forbid")


class DocumentCommentResponse(BaseModel):
    id: UUID
    document_id: UUID
    user_id: UUID
    content: str
    mentions: list[UUID] = Field(default_factory=list)
    parent_id: UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(extra="forbid")


class DocumentQualityResponse(BaseModel):
    document_id: UUID
    extraction_method: str | None
    extraction_coverage_score: float | None
    ocr_used: bool
    vision_used: bool
    warnings: list[str]
    total_chunks: int
    low_quality_chunks: int
    page_numbers: list[int]
    missing_page_numbers: list[int]

    model_config = ConfigDict(extra="forbid")


class DocumentStatusResponse(BaseModel):
    document_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    language: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    security_scan_result: str | None = None
    security_scan_reason: str | None = None
    security_scanned_at: datetime | None = None
    security_scan_required: bool = False
    status: str
    processing_progress: int = 0
    active_stage: str = "queued"
    stage_progress: int = 0
    quarantined: bool = False
    information_yield: float | None = None
    extraction_method: str | None = None
    extraction_coverage_score: float | None = None
    extraction_ocr_used: bool = False
    extraction_vision_used: bool = False
    extraction_warnings: list[str] = Field(default_factory=list)
    extraction_confidence_band: str = "low"
    ingestion_job_id: UUID | None
    ingestion_status: str | None
    attempt_count: int | None
    max_attempts: int | None
    last_error_code: str | None
    last_error_message: str | None
    dead_lettered_at: datetime | None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    total_chunk_count: int = 0
    embedded_chunk_count: int = 0
    average_chunk_quality: float | None = None
    recovery_available: bool = False
    recovery_stage: str | None = None
    recovery_reason: str | None = None
    last_checkpoint_at: datetime | None = None
    remaining_chunk_count: int = 0
    resume_count: int = 0

    model_config = ConfigDict(extra="forbid")


class UploadValidationConfig(BaseModel):
    allowed_mime_types: list[str] = Field(default_factory=list)
    allowed_extensions: list[str] = Field(default_factory=list)
    max_bytes: int

    model_config = ConfigDict(extra="forbid")


class SupportedFormatEntry(BaseModel):
    extension: str
    category: str
    extraction_method: str
    needs_conversion: bool = False

    model_config = ConfigDict(extra="forbid")


class SupportedFormatsResponse(BaseModel):
    total_formats: int
    legacy_conversion_enabled: bool
    items: list[SupportedFormatEntry]

    model_config = ConfigDict(extra="forbid")


class DocumentChunkPayload(BaseModel):
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    metadata: dict[str, str | int]

    model_config = ConfigDict(extra="forbid")


class DocumentChunksResponse(BaseModel):
    document_id: UUID
    total_chunks: int
    offset: int
    limit: int
    has_more: bool
    chunks: list[DocumentChunkPayload]

    model_config = ConfigDict(extra="forbid")


class DeleteBatchRequest(BaseModel):
    document_ids: list[UUID]

    model_config = ConfigDict(extra="forbid")


class DeleteBatchResponse(BaseModel):
    deleted_count: int

    model_config = ConfigDict(extra="forbid")


class BulkDocumentActionRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=100)
    tag_id: UUID | None = None
    tag_ids: list[UUID] | None = Field(default=None, max_length=50)
    folder_id: UUID | None = None
    model_config = ConfigDict(extra="forbid")


class BulkDocumentActionResponse(BaseModel):
    requested_count: int
    accepted_ids: list[UUID]
    failed: dict[str, str] = Field(default_factory=dict)
    operation: str
    model_config = ConfigDict(extra="forbid")


class BulkDocumentExportRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class DocumentShareCreate(BaseModel):
    user_id: UUID
    role: Literal["reader"] = "reader"
    model_config = ConfigDict(extra="forbid")


class DocumentShareResponse(BaseModel):
    id: UUID
    document_id: UUID
    user_id: UUID
    role: str
    created_by_user_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class DocumentWebhookCreate(BaseModel):
    endpoint_url: AnyHttpUrl
    event_types: list[Literal["document.status.updated", "document.indexed", "document.failed"]] = (
        Field(default_factory=lambda: ["document.status.updated"], max_length=10)  # type: ignore[arg-type]
    )
    model_config = ConfigDict(extra="forbid")


class DocumentWebhookUpdate(BaseModel):
    endpoint_url: AnyHttpUrl | None = None
    event_types: (
        list[Literal["document.status.updated", "document.indexed", "document.failed"]] | None
    ) = Field(default=None, max_length=10)
    active: bool | None = None
    model_config = ConfigDict(extra="forbid")


class DocumentWebhookResponse(BaseModel):
    id: UUID
    endpoint_url: AnyHttpUrl
    event_types: list[str]
    active: bool
    failure_count: int
    last_error: str | None
    disabled_reason: str | None = None
    secret_rotated_at: datetime | None = None
    created_at: datetime
    secret: str | None = None
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class DocumentWebhookDeliveryResponse(BaseModel):
    id: UUID
    subscription_id: UUID
    event_type: str
    event_id: str | None
    status: str
    attempt_count: int
    response_status: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    next_attempt_at: datetime | None = None
    attempt_history: list[dict[str, Any]] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class DocumentObservabilityResponse(BaseModel):
    status_counts: dict[str, int]
    active_ingestion_jobs: int
    failed_documents: int
    quarantined_documents: int
    total_documents: int
    indexed_documents: int
    storage_bytes: int

    model_config = ConfigDict(extra="forbid")
