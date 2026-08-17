from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthContext,
    build_auth_context_from_jwt,
    decode_access_token,
    get_auth_context,
)
from app.auth.rbac import require_permissions, resolve_permissions
from app.auth.tenancy import require_request_tenant_id
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.documents.schemas.documents import (
    DeleteBatchRequest,
    DeleteBatchResponse,
    DocumentChunksResponse,
    DocumentListResponse,
    DocumentMetadataResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    DocumentVersionsResponse,
    SupportedFormatEntry,
    SupportedFormatsResponse,
)
from app.ingestion.models.ingestion_job import IngestionJob
from app.ingestion.services.extraction_quality import confidence_band
from app.ingestion.services.ingestion_service import IngestionService
from app.platform.database.session import get_db
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.services.audit_service import AuditService
from app.system.services.rate_limit_service import RateLimitService
from app.system.services.storage_service import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_FILE_INPUT = File(...)

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

_HEAVY_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".tif",
    ".bmp",
    ".webp",
    ".docx",
    ".pptx",
    ".xlsx",
    ".doc",
    ".ppt",
    ".xls",
}


def _enforce_tenant_scope(request_tenant_id: uuid.UUID, auth: AuthContext) -> None:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Token tenant scope does not match requested tenant.",
            status_code=403,
        )


def _coerce_audit_details(details: dict[str, object] | None) -> dict[str, str] | None:
    if details is None:
        return None
    return {key: str(value) for key, value in details.items()}


def _safe_audit_commit(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    try:
        AuditService(db).write_event(
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_user_id=actor_user_id,
            details=_coerce_audit_details(details) or {},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning(
            "Failed to persist document audit event.",
            extra={
                "tenant_id": str(tenant_id),
                "actor_user_id": str(actor_user_id),
                "action": action,
                "resource_id": resource_id,
            },
            exc_info=True,
        )


def _delete_document_object_or_queue(
    *,
    db: Session,
    settings: Settings,
    document: Document,
) -> None:
    """Delete a document's private blob, with durable retry on storage failure."""
    if not document.storage_bucket or not document.storage_object_key:
        return

    try:
        StorageService(settings).delete_object(
            bucket=document.storage_bucket,
            object_key=document.storage_object_key,
            raise_on_error=True,
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Document blob deletion deferred to durable cleanup.",
            extra={
                "tenant_id": str(document.tenant_id),
                "document_id": str(document.id),
                "bucket": document.storage_bucket,
                "object_key": document.storage_object_key,
            },
            exc_info=exc,
        )
        db.add(
            StorageCleanupJob(
                tenant_id=document.tenant_id,
                owner_user_id=document.uploaded_by_user_id,
                bucket=document.storage_bucket,
                object_key=document.storage_object_key,
            )
        )


def _document_metadata_response(doc: Document) -> DocumentMetadataResponse:
    return DocumentMetadataResponse(
        document_id=doc.id,
        status=doc.status,
        processing_progress=doc.processing_progress,
        quarantined=doc.quarantined,
        information_yield=doc.information_yield,
        extraction_method=doc.extraction_method,
        extraction_coverage_score=doc.extraction_coverage_score,
        extraction_ocr_used=doc.extraction_ocr_used,
        extraction_vision_used=doc.extraction_vision_used,
        extraction_warnings=list(doc.extraction_warnings or []),
        extraction_confidence_band=confidence_band(doc.extraction_coverage_score),
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        sha256_hash=doc.sha256_hash,
        storage_bucket=doc.storage_bucket,
        storage_object_key=doc.storage_object_key,
        version=doc.version,
        parent_document_id=doc.parent_document_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _choose_ingestion_queue(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return "ingestion_heavy" if suffix in _HEAVY_EXTENSIONS else "ingestion_light"


def _inline_content_disposition(filename: str) -> str:
    safe_name = Path(filename).name.replace("\r", "").replace("\n", "") or "document"
    return f"inline; filename*=UTF-8''{quote(safe_name)}"


def _single_chunk_iter(payload: bytes) -> Iterable[bytes]:
    yield payload


def _build_stream_auth_context(
    *,
    token: str,
    db: Session,
    settings: Settings,
) -> AuthContext:
    cleaned = token.strip()
    if not cleaned:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="Access token is required for document event streaming.",
            status_code=401,
        )

    claims = decode_access_token(cleaned, settings)
    auth = build_auth_context_from_jwt(claims=claims, x_tenant_id=None, db=db)
    granted = resolve_permissions(
        roles=frozenset(auth.roles),
        direct_permissions=getattr(auth, "permissions", frozenset()),
    )
    if "documents:read" not in granted:
        raise ApiError(
            code="FORBIDDEN",
            message="Insufficient permissions for document event streaming.",
            status_code=403,
            details={"missing_permissions": ["documents:read"]},
        )
    return auth


def _consume_stream_ticket(*, ticket: str, db: Session, settings: Settings) -> AuthContext:
    cleaned = ticket.strip()
    if not cleaned:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="A document event stream ticket is required.",
            status_code=401,
        )

    service = IngestionService(db=db, settings=settings)
    key = f"document_event_stream_ticket:{cleaned}"
    raw = service.redis.get(key)
    if raw is None:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="The document event stream ticket is invalid or expired.",
            status_code=401,
        )
    service.redis.delete(key)
    try:
        payload = json.loads(raw)
        auth = AuthContext(
            user_id=uuid.UUID(str(payload["user_id"])),
            tenant_id=uuid.UUID(str(payload["tenant_id"])),
            roles=frozenset(str(role) for role in payload.get("roles", [])),
            permissions=frozenset(str(permission) for permission in payload.get("permissions", [])),
            token_id=str(payload.get("token_id") or "document-stream-ticket"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="The document event stream ticket is invalid.",
            status_code=401,
        ) from exc

    granted = resolve_permissions(
        roles=frozenset(auth.roles),
        direct_permissions=getattr(auth, "permissions", frozenset()),
    )
    if "documents:read" not in granted:
        raise ApiError(
            code="FORBIDDEN",
            message="Insufficient permissions for document event streaming.",
            status_code=403,
            details={"missing_permissions": ["documents:read"]},
        )
    return auth


@router.get(
    "/supported-formats",
    response_model=SupportedFormatsResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_supported_formats(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SupportedFormatsResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    items = [
        SupportedFormatEntry(
            extension=item.extension,
            category=item.category,
            extraction_method=item.extraction_method,
            needs_conversion=item.needs_conversion,
        )
        for item in service.extractor_router.describe_supported_formats()
    ]
    return SupportedFormatsResponse(
        total_formats=len(items),
        legacy_conversion_enabled=settings.legacy_conversion_enabled,
        items=items,
    )


@router.get(
    "/{document_id}/full-text",
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_full_text(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Retrieve the full reconstructed text of a document."""
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    doc = service.documents.get_accessible_by_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
        include_quarantined=True,
    )
    if not doc:
        raise ApiError(code="DOCUMENT_NOT_FOUND", message="Document not found", status_code=404)

    # Get all chunks sorted by index
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.tenant_id == auth.tenant_id,
        )
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )

    full_text = "".join([c.content for c in chunks])

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.full_text",
        resource_type="document",
        resource_id=str(document_id),
        actor_user_id=auth.user_id,
    )
    return {"content": full_text, "filename": doc.filename}


def get_storage_service(settings: Settings = Depends(get_settings)) -> StorageService:
    return StorageService(settings)


@router.get(
    "/{document_id}/download",
    dependencies=[Depends(require_permissions("documents:read"))],
)
def download_document(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage_service),
) -> StreamingResponse:
    """Download the original document file."""
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    doc = service.documents.get_accessible_by_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    if not doc:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND",
            message="Document not found.",
            status_code=404,
        )

    if not doc.storage_bucket or not doc.storage_object_key:
        raise ApiError(
            code="STORAGE_MISSING",
            message="This document does not have a raw storage asset.",
            status_code=404,
        )

    # Stream the file from storage
    file_stream = storage.get_stream(bucket=doc.storage_bucket, object_key=doc.storage_object_key)

    return StreamingResponse(
        file_stream,
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": _inline_content_disposition(doc.filename)},
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def list_documents(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    items = service.list_documents(tenant_id=auth.tenant_id, user_id=auth.user_id)
    return DocumentListResponse(items=[_document_metadata_response(doc) for doc in items])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
async def upload_document(
    request: Request,
    file: UploadFile = UPLOAD_FILE_INPUT,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    cleaned_key = (idempotency_key or "").strip()
    if not cleaned_key:
        raise ApiError(
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="Idempotency-Key header is required.",
            status_code=400,
        )
    if len(cleaned_key) > 128:
        raise ApiError(
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency-Key exceeds maximum length.",
            status_code=400,
        )

    RateLimitService(settings).enforce_upload_user_limit(
        request=request,
        user_id=str(auth.user_id),
    )

    payload = await file.read()
    from app.deepspace.integrations.client_proxy import client_proxy_registry

    if client_proxy_registry.is_client_connected(str(auth.tenant_id), str(auth.user_id)):
        import base64

        payload_b64 = base64.b64encode(payload).decode("utf-8")
        result_data = await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id),
            str(auth.user_id),
            "db.documents.upload",
            {
                "idempotency_key": cleaned_key,
                "filename": file.filename or "",
                "content_type": file.content_type or "application/octet-stream",
                "payload_b64": payload_b64,
            },
        )
        return DocumentUploadResponse(
            document_id=uuid.UUID(result_data["document_id"]),
            status=result_data.get("status", "completed"),
            ingestion_job_id=(
                uuid.UUID(result_data["ingestion_job_id"])
                if result_data.get("ingestion_job_id")
                else None
            ),
        )

    service = IngestionService(db=db, settings=settings)
    result = service.upload_document(
        auth=auth,
        idempotency_key=cleaned_key,
        filename=file.filename or "",
        content_type=file.content_type or "application/octet-stream",
        payload=payload,
    )

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.upload",
        resource_type="document",
        resource_id=str(result.document_id),
        actor_user_id=auth.user_id,
        details={"filename": file.filename or ""},
    )

    return DocumentUploadResponse(
        document_id=result.document_id,
        status=result.status,
        ingestion_job_id=result.ingestion_job_id,
    )


@router.get(
    "/events/ticket",
    dependencies=[Depends(require_permissions("documents:read"))],
)
def create_document_event_stream_ticket(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, int | str]:
    service = IngestionService(db=db, settings=settings)
    ticket = secrets.token_urlsafe(32)
    service.redis.setex(
        f"document_event_stream_ticket:{ticket}",
        settings.document_event_stream_ticket_ttl_seconds,
        json.dumps(
            {
                "user_id": str(auth.user_id),
                "tenant_id": str(auth.tenant_id),
                "roles": sorted(auth.roles),
                "permissions": sorted(getattr(auth, "permissions", frozenset())),
                "token_id": auth.token_id,
            }
        ),
    )
    return {"ticket": ticket, "expires_in_seconds": settings.document_event_stream_ticket_ttl_seconds}


@router.get("/events/stream")
async def stream_document_events(
    request: Request,
    token: str | None = Query(default=None, min_length=1),
    ticket: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    if ticket:
        auth = _consume_stream_ticket(ticket=ticket, db=db, settings=settings)
    elif token:
        # Backward-compatible API-key path for existing clients. The web UI
        # uses one-time tickets so bearer tokens never appear in URLs.
        auth = _build_stream_auth_context(token=token, db=db, settings=settings)
    else:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="A document event stream ticket is required.",
            status_code=401,
        )
    service = IngestionService(db=db, settings=settings)
    pubsub = cast(Any, service.redis).pubsub()
    channel = f"document_updates:{auth.tenant_id}:{auth.user_id}"
    pubsub.subscribe(channel)

    async def event_stream() -> AsyncIterator[str]:
        last_heartbeat = time.monotonic()
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break

                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    payload = message["data"]
                    if isinstance(payload, bytes):
                        payload = payload.decode("utf-8")
                    yield f"data: {payload}\n\n"
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= 15:
                    yield ": keep-alive\n\n"
                    last_heartbeat = time.monotonic()

                await asyncio.sleep(0.25)
        finally:
            try:
                pubsub.unsubscribe(channel)
            finally:
                pubsub.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentMetadataResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentMetadataResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    document = service.get_document(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    response = _document_metadata_response(document)

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.read",
        resource_type="document",
        resource_id=str(document_id),
        actor_user_id=auth.user_id,
    )
    return response


@router.get(
    "/{document_id}/view",
    dependencies=[Depends(require_permissions("documents:read"))],
)
def view_document_file(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    document = service.get_document(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    payload = service.storage.get_bytes(
        bucket=document.storage_bucket,
        object_key=document.storage_object_key,
    )

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.view_file",
        resource_type="document",
        resource_id=str(document_id),
        actor_user_id=auth.user_id,
    )

    return StreamingResponse(
        _single_chunk_iter(payload),
        media_type=document.content_type,
        headers={
            "Content-Disposition": _inline_content_disposition(document.filename),
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get(
    "/{document_id}/versions",
    response_model=DocumentVersionsResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_versions(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentVersionsResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    document = service.get_document(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    versions = service.documents.get_version_history(
        tenant_id=auth.tenant_id,
        document_id=document.id,
    )
    accessible_ids = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        include_quarantined=True,
    )
    versions = [version for version in versions if version.id in accessible_ids]

    from app.documents.schemas.documents import DocumentVersionHistory

    root_id = versions[-1].id if versions else document_id
    return DocumentVersionsResponse(
        root_document_id=root_id,
        versions=[
            DocumentVersionHistory(
                document_id=v.id,
                version=v.version,
                created_at=v.created_at,
                sha256_hash=v.sha256_hash,
                status=v.status,
            )
            for v in versions
        ],
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_status(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentStatusResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    status = service.get_document_status(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    response = DocumentStatusResponse(
        document_id=status.document_id,
        status=status.status,
        processing_progress=status.processing_progress,
        active_stage=status.active_stage,
        stage_progress=status.stage_progress,
        quarantined=status.quarantined,
        information_yield=status.information_yield,
        extraction_method=status.extraction_method,
        extraction_coverage_score=status.extraction_coverage_score,
        extraction_ocr_used=status.extraction_ocr_used,
        extraction_vision_used=status.extraction_vision_used,
        extraction_warnings=status.extraction_warnings,
        extraction_confidence_band=status.extraction_confidence_band,
        ingestion_job_id=status.ingestion_job_id,
        ingestion_status=status.ingestion_status,
        attempt_count=status.attempt_count,
        max_attempts=status.max_attempts,
        last_error_code=status.last_error_code,
        last_error_message=status.last_error_message,
        dead_lettered_at=status.dead_lettered_at,
        embedding_provider=status.embedding_provider,
        embedding_model=status.embedding_model,
        embedded_chunk_count=status.embedded_chunk_count,
    )

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.status",
        resource_type="document",
        resource_id=str(document_id),
        actor_user_id=auth.user_id,
    )
    return response


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentChunksResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_chunks(
    document_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentChunksResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    service.get_document(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    chunks = service.chunks.get_by_document_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    total_chunks = service.chunks.count_by_document_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
    )

    from app.documents.schemas.documents import DocumentChunkPayload

    return DocumentChunksResponse(
        document_id=document_id,
        total_chunks=total_chunks,
        offset=offset,
        limit=limit,
        has_more=(offset + len(chunks)) < total_chunks,
        chunks=[
            DocumentChunkPayload(
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                metadata=chunk.chunk_metadata,
            )
            for chunk in chunks
        ],
    )


@router.delete(
    "/{document_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:delete"))],
)
def delete_document(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    doc = service.documents.get_accessible_by_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
        include_quarantined=True,
    )
    if not doc:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND",
            message="Document not found.",
            status_code=404,
        )

    service.documents.soft_delete_batch(tenant_id=auth.tenant_id, document_ids=[document_id])
    service.chunks.delete_by_document_ids(tenant_id=auth.tenant_id, document_ids=[document_id])
    db.commit()
    _delete_document_object_or_queue(db=db, settings=settings, document=doc)
    db.commit()

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.delete",
        resource_type="document",
        resource_id=str(document_id),
        actor_user_id=auth.user_id,
    )
    return Response(status_code=204)


@router.post(
    "/batch/delete",
    response_model=DeleteBatchResponse,
    dependencies=[Depends(require_permissions("documents:delete"))],
)
def batch_delete_documents(
    payload: DeleteBatchRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeleteBatchResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    if not payload.document_ids:
        return DeleteBatchResponse(deleted_count=0)

    service = IngestionService(db=db, settings=settings)
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    to_delete = [doc_id for doc_id in payload.document_ids if doc_id in accessible]
    if not to_delete:
        return DeleteBatchResponse(deleted_count=0)

    documents_to_delete = [
        document
        for document in service.documents.list_by_ids(
            tenant_id=auth.tenant_id,
            document_ids=to_delete,
        )
        if document.id in accessible
    ]
    service.documents.soft_delete_batch(tenant_id=auth.tenant_id, document_ids=to_delete)
    service.chunks.delete_by_document_ids(tenant_id=auth.tenant_id, document_ids=to_delete)
    db.commit()
    for document in documents_to_delete:
        _delete_document_object_or_queue(db=db, settings=settings, document=document)
    db.commit()

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.batch_delete",
        resource_type="document",
        resource_id="batch",
        actor_user_id=auth.user_id,
        details={
            "deleted_count": len(to_delete),
            "document_ids": [str(doc_id) for doc_id in to_delete],
        },
    )
    return DeleteBatchResponse(deleted_count=len(to_delete))


@router.post(
    "/{document_id}/reingest",
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def reingest_document(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    document = service.documents.get_accessible_by_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
        include_quarantined=True,
    )
    if not document:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND",
            message="Document not found.",
            status_code=404,
        )

    document.status = "queued"
    document.processing_progress = 0
    document.quarantined = False
    document.information_yield = None
    document.extraction_coverage_score = None
    document.extraction_ocr_used = False
    document.extraction_vision_used = False
    document.extraction_warnings = []

    service.chunks.delete_by_document_ids(tenant_id=auth.tenant_id, document_ids=[document_id])

    for existing_job in service.jobs.list_by_document_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
    ):
        if existing_job.status in {
            "queued",
            "downloading",
            "parsing",
            "chunking",
            "embedding",
        }:
            service.jobs.set_status(
                tenant_id=auth.tenant_id,
                job=existing_job,
                status="failed",
                error_code="SUPERSEDED_JOB",
                error_message="Superseded by manual document reingest.",
            )

    job = IngestionJob(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        document_id=document.id,
        status="queued",
        attempt_count=0,
        max_attempts=settings.ingestion_max_attempts,
    )
    service.jobs.create(job)
    db.commit()

    service._enqueue_ingestion(
        job_id=job.id,
        tenant_id=auth.tenant_id,
        queue=_choose_ingestion_queue(document.filename),
    )

    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.reingest",
        resource_type="document",
        resource_id=str(document_id),
        actor_user_id=auth.user_id,
    )

    return DocumentUploadResponse(
        document_id=document.id,
        status="queued",
        ingestion_job_id=job.id,
    )
