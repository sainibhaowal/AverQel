from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(extra="forbid")


class DocumentListResponse(BaseModel):
    items: list[DocumentMetadataResponse]

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


class DocumentStatusResponse(BaseModel):
    document_id: UUID
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
    embedded_chunk_count: int = 0

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
