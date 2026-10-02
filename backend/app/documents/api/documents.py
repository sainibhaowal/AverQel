from __future__ import annotations

import asyncio
import base64
import binascii
import difflib
import hashlib
import io
import json
import logging
import secrets
import shutil
import time
import uuid
import zipfile
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
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
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthContext,
    build_auth_context_from_jwt,
    decode_access_token,
    get_auth_context,
)
from app.auth.models.user import User
from app.auth.rbac import require_permissions, resolve_permissions
from app.auth.tenancy import require_request_tenant_id
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.documents.models.organization import (
    DocumentAIAction,
    DocumentFolder,
    DocumentFolderAssignment,
    DocumentShare,
    DocumentShareLink,
    DocumentSmartCollection,
    DocumentTag,
    DocumentTagAssignment,
    DocumentWebhookDelivery,
    DocumentWebhookSubscription,
)
from app.documents.schemas.documents import (
    BulkDocumentActionRequest,
    BulkDocumentActionResponse,
    BulkDocumentExportRequest,
    DeleteBatchRequest,
    DeleteBatchResponse,
    DocumentAIActionRequest,
    DocumentAIActionResponse,
    DocumentChunksResponse,
    DocumentCommentCreate,
    DocumentCommentResponse,
    DocumentCommentUpdate,
    DocumentListResponse,
    DocumentMetadataResponse,
    DocumentObservabilityResponse,
    DocumentQualityResponse,
    DocumentShareCreate,
    DocumentShareLinkCreate,
    DocumentShareLinkResolveResponse,
    DocumentShareLinkResponse,
    DocumentShareResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    DocumentVersionDiffResponse,
    DocumentVersionsResponse,
    DocumentWebhookCreate,
    DocumentWebhookDeliveryResponse,
    DocumentWebhookResponse,
    DocumentWebhookUpdate,
    DuplicateDocumentGroup,
    DuplicateDocumentResponse,
    SupportedFormatEntry,
    SupportedFormatsResponse,
)
from app.documents.services.pdf_render_service import PdfRenderService
from app.documents.services.smart_collection_service import evaluate_smart_collection
from app.documents.services.webhook_security import WebhookEndpointError, validate_webhook_endpoint
from app.ingestion.models.ingestion_job import IngestionJob
from app.ingestion.services.conversion_service import ConversionService
from app.ingestion.services.extraction_quality import confidence_band
from app.ingestion.services.ingestion_service import IngestionService
from app.integrations.services.connector_secret_crypto import (
    ConnectorSecretCrypto,
    ConnectorSecretCryptoError,
)
from app.platform.database.session import get_db, set_db_tenant_context
from app.query.models.comment import Comment
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
_MAX_DOCUMENT_EXPORT_BYTES = 50 * 1024 * 1024


def _webhook_response(
    row: DocumentWebhookSubscription, *, secret: str | None = None
) -> DocumentWebhookResponse:
    return DocumentWebhookResponse(
        id=row.id,
        endpoint_url=row.endpoint_url,
        event_types=list(row.event_types or []),
        active=row.active,
        failure_count=row.failure_count,
        last_error=row.last_error,
        disabled_reason=row.disabled_reason,
        secret_rotated_at=row.secret_rotated_at,
        created_at=row.created_at,
        secret=secret,
    )


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


def _attach_document_tags(
    db: Session, tenant_id: uuid.UUID, responses: list[DocumentMetadataResponse]
) -> list[DocumentMetadataResponse]:
    """Add tenant-scoped tag names to list responses without changing visibility."""
    if not responses:
        return responses
    document_ids = [item.document_id for item in responses]
    rows = (
        db.query(
            DocumentTagAssignment.document_id, DocumentTag.id, DocumentTag.name, DocumentTag.color
        )
        .join(DocumentTag, DocumentTag.id == DocumentTagAssignment.tag_id)
        .filter(
            DocumentTagAssignment.tenant_id == tenant_id,
            DocumentTagAssignment.document_id.in_(document_ids),
            DocumentTag.tenant_id == tenant_id,
        )
        .all()
    )
    tags_by_document: dict[uuid.UUID, list[dict[str, str]]] = {}
    for document_id, tag_id, tag_name, tag_color in rows:
        tags_by_document.setdefault(document_id, []).append(
            {"id": str(tag_id), "name": tag_name, "color": tag_color}
        )
    for item in responses:
        item.tags = tags_by_document.get(item.document_id, [])
    return responses


def _choose_ingestion_queue(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return "ingestion_heavy" if suffix in _HEAVY_EXTENSIONS else "ingestion_light"


def _inline_content_disposition(filename: str) -> str:
    safe_name = Path(filename).name.replace("\r", "").replace("\n", "") or "document"
    return f"inline; filename*=UTF-8''{quote(safe_name)}"


def _attachment_content_disposition(filename: str) -> str:
    safe_name = Path(filename).name.replace("\r", "").replace("\n", "") or "document"
    return f"attachment; filename*=UTF-8''{quote(safe_name)}"


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
        payload = json.loads(raw)  # type: ignore[arg-type]
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

    # Chunks may overlap for retrieval quality. A visible boundary keeps OCR
    # lines and neighboring fragments from being merged into made-up words in
    # Reader Mode while retaining the exact persisted chunk text.
    full_text = "\n\n".join(c.content for c in chunks)

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
    q: str | None = Query(default=None, max_length=256),
    status: list[str] | None = Query(default=None),  # noqa: B008
    content_type: str | None = Query(default=None, max_length=128),
    ocr_used: bool | None = Query(default=None),
    quarantined: bool | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    created_from: datetime | None = Query(default=None),  # noqa: B008
    created_to: datetime | None = Query(default=None),  # noqa: B008
    tag_id: list[uuid.UUID] | None = Query(default=None),  # noqa: B008
    smart_collection_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentListResponse:
    _enforce_tenant_scope(request_tenant_id, auth)

    service = IngestionService(db=db, settings=settings)
    if smart_collection_id is not None:
        collection = db.scalar(
            select(DocumentSmartCollection).where(
                DocumentSmartCollection.id == smart_collection_id,
                DocumentSmartCollection.tenant_id == auth.tenant_id,
            )
        )
        if collection is None:
            raise ApiError(
                code="SMART_COLLECTION_NOT_FOUND",
                message="Smart collection was not found.",
                status_code=404,
            )
        result = evaluate_smart_collection(
            db,
            collection=collection,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            page=1,
            page_size=limit,
        )
        return DocumentListResponse(
            items=_attach_document_tags(
                db, auth.tenant_id, [_document_metadata_response(doc) for doc in result.items]
            ),
            total=result.total,
            skip=0,
            limit=limit,
        )
    if any(
        (
            q,
            status,
            content_type,
            ocr_used is not None,
            quarantined is not None,
            owner_id,
            created_from,
            created_to,
            tag_id,
            skip,
            limit != 100,
        )
    ):
        items, total = service.documents.search_accessible_for_user(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            query_text=q,
            statuses=status,
            content_type=content_type,
            ocr_used=ocr_used,
            quarantined=quarantined,
            owner_id=owner_id,
            created_from=created_from,
            created_to=created_to,
            tag_ids=tag_id,
            skip=skip,
            limit=limit,
        )
        return DocumentListResponse(
            items=_attach_document_tags(
                db, auth.tenant_id, [_document_metadata_response(doc) for doc in items]
            ),
            total=total,
            skip=skip,
            limit=limit,
        )
    items = service.list_documents(tenant_id=auth.tenant_id, user_id=auth.user_id)
    return DocumentListResponse(
        items=_attach_document_tags(
            db, auth.tenant_id, [_document_metadata_response(doc) for doc in items]
        ),
        total=len(items),
        skip=0,
        limit=100,
    )


@router.get(
    "/duplicates",
    response_model=DuplicateDocumentResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def list_duplicate_documents(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DuplicateDocumentResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    groups = service.documents.list_accessible_duplicate_groups(
        tenant_id=auth.tenant_id, user_id=auth.user_id
    )
    payload = [
        DuplicateDocumentGroup(
            sha256_hash=group[0].sha256_hash,
            size_bytes=group[0].size_bytes,
            documents=[_document_metadata_response(document) for document in group],
        )
        for group in groups
    ]
    return DuplicateDocumentResponse(
        groups=payload,
        total_duplicate_documents=sum(len(group) for group in groups),
    )


@router.get(
    "/webhooks",
    response_model=list[DocumentWebhookResponse],
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def list_document_webhooks(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DocumentWebhookResponse]:
    _enforce_tenant_scope(request_tenant_id, auth)
    rows = (
        db.query(DocumentWebhookSubscription)
        .filter(DocumentWebhookSubscription.tenant_id == auth.tenant_id)
        .order_by(DocumentWebhookSubscription.created_at.asc())
        .all()
    )
    return [_webhook_response(row) for row in rows]


@router.post(
    "/webhooks",
    response_model=DocumentWebhookResponse,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def create_document_webhook(
    payload: DocumentWebhookCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentWebhookResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    endpoint = str(payload.endpoint_url)
    try:
        validate_webhook_endpoint(endpoint, environment=settings.env)
    except WebhookEndpointError as exc:
        raise ApiError(code="WEBHOOK_ENDPOINT_INVALID", message=str(exc), status_code=422) from exc
    if (
        db.query(DocumentWebhookSubscription.id)
        .filter(
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
            DocumentWebhookSubscription.endpoint_url == endpoint,
        )
        .first()
    ):
        raise ApiError(
            code="WEBHOOK_EXISTS",
            message="A webhook for this endpoint already exists.",
            status_code=409,
        )
    secret = secrets.token_urlsafe(32)
    try:
        encrypted = ConnectorSecretCrypto(settings).encrypt(
            secret, aad=str(auth.tenant_id).encode()
        )
    except ConnectorSecretCryptoError as exc:
        raise ApiError(
            code="WEBHOOK_SECRET_UNAVAILABLE",
            message="Webhook encryption is not configured.",
            status_code=503,
        ) from exc
    row = DocumentWebhookSubscription(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        created_by_user_id=auth.user_id,
        endpoint_url=endpoint,
        event_types=list(dict.fromkeys(payload.event_types)),
        secret_ciphertext=encrypted.ciphertext,
        secret_nonce=encrypted.nonce,
        secret_kid=encrypted.kid,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _webhook_response(row, secret=secret)


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def delete_document_webhook(
    webhook_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(DocumentWebhookSubscription)
        .filter(
            DocumentWebhookSubscription.id == webhook_id,
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="WEBHOOK_NOT_FOUND", message="Webhook subscription was not found.", status_code=404
        )
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.patch(
    "/webhooks/{webhook_id}",
    response_model=DocumentWebhookResponse,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def update_document_webhook(
    webhook_id: uuid.UUID,
    payload: DocumentWebhookUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentWebhookResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(DocumentWebhookSubscription)
        .filter(
            DocumentWebhookSubscription.id == webhook_id,
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="WEBHOOK_NOT_FOUND", message="Webhook subscription was not found.", status_code=404
        )
    if payload.endpoint_url is not None:
        endpoint = str(payload.endpoint_url)
        try:
            validate_webhook_endpoint(endpoint, environment=settings.env)
        except WebhookEndpointError as exc:
            raise ApiError(
                code="WEBHOOK_ENDPOINT_INVALID", message=str(exc), status_code=422
            ) from exc
        duplicate = (
            db.query(DocumentWebhookSubscription.id)
            .filter(
                DocumentWebhookSubscription.tenant_id == auth.tenant_id,
                DocumentWebhookSubscription.endpoint_url == endpoint,
                DocumentWebhookSubscription.id != webhook_id,
            )
            .first()
        )
        if duplicate:
            raise ApiError(
                code="WEBHOOK_EXISTS",
                message="A webhook for this endpoint already exists.",
                status_code=409,
            )
        row.endpoint_url = endpoint
    if payload.event_types is not None:
        row.event_types = list(dict.fromkeys(payload.event_types))
    if payload.active is not None:
        row.active = payload.active
        if payload.active:
            row.disabled_reason = None
    db.commit()
    db.refresh(row)
    return _webhook_response(row)


@router.post(
    "/webhooks/{webhook_id}/rotate-secret",
    response_model=DocumentWebhookResponse,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def rotate_document_webhook_secret(
    webhook_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentWebhookResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(DocumentWebhookSubscription)
        .filter(
            DocumentWebhookSubscription.id == webhook_id,
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="WEBHOOK_NOT_FOUND", message="Webhook subscription was not found.", status_code=404
        )
    secret = secrets.token_urlsafe(32)
    try:
        encrypted = ConnectorSecretCrypto(settings).encrypt(
            secret, aad=str(auth.tenant_id).encode()
        )
    except ConnectorSecretCryptoError as exc:
        raise ApiError(
            code="WEBHOOK_SECRET_UNAVAILABLE",
            message="Webhook encryption is not configured.",
            status_code=503,
        ) from exc
    row.secret_ciphertext = encrypted.ciphertext
    row.secret_nonce = encrypted.nonce
    row.secret_kid = encrypted.kid
    row.secret_rotated_at = datetime.now(UTC)
    row.last_error = None
    row.disabled_reason = None
    row.failure_count = 0
    row.active = True
    db.commit()
    db.refresh(row)
    return _webhook_response(row, secret=secret)


@router.post(
    "/webhooks/{webhook_id}/test",
    status_code=202,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def test_document_webhook(
    webhook_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(DocumentWebhookSubscription)
        .filter(
            DocumentWebhookSubscription.id == webhook_id,
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="WEBHOOK_NOT_FOUND", message="Webhook subscription was not found.", status_code=404
        )
    from app.documents.workers.tasks_webhooks import dispatch_document_webhooks

    event_id = str(uuid.uuid4())
    dispatch_document_webhooks.delay(
        tenant_id=str(auth.tenant_id),
        event={
            "event_id": event_id,
            "type": "document.status.updated",
            "resource": "webhook_test",
            "data": {"test": True, "webhook_id": str(webhook_id), "status": "test"},
        },
    )
    return {"event_id": event_id, "status": "queued"}


@router.get(
    "/webhooks/{webhook_id}/deliveries",
    response_model=list[DocumentWebhookDeliveryResponse],
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def list_document_webhook_deliveries(
    webhook_id: uuid.UUID,
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None, max_length=512),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DocumentWebhookDeliveryResponse]:
    _enforce_tenant_scope(request_tenant_id, auth)
    if (
        db.query(DocumentWebhookSubscription.id)
        .filter(
            DocumentWebhookSubscription.id == webhook_id,
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
        )
        .first()
        is None
    ):
        raise ApiError(
            code="WEBHOOK_NOT_FOUND", message="Webhook subscription was not found.", status_code=404
        )
    query = db.query(DocumentWebhookDelivery).filter(
        DocumentWebhookDelivery.tenant_id == auth.tenant_id,
        DocumentWebhookDelivery.subscription_id == webhook_id,
    )
    if cursor:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor.encode() + b"===").decode())
            cursor_created_at = datetime.fromisoformat(str(decoded["created_at"]))
            cursor_id = uuid.UUID(str(decoded["id"]))
        except (
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            binascii.Error,
        ) as exc:
            raise ApiError(
                code="WEBHOOK_CURSOR_INVALID",
                message="Delivery history cursor is invalid.",
                status_code=422,
            ) from exc
        query = query.filter(
            or_(
                DocumentWebhookDelivery.created_at < cursor_created_at,
                and_(
                    DocumentWebhookDelivery.created_at == cursor_created_at,
                    DocumentWebhookDelivery.id < cursor_id,
                ),
            )
        )
    rows = (
        query.order_by(DocumentWebhookDelivery.created_at.desc(), DocumentWebhookDelivery.id.desc())
        .limit(limit + 1)
        .all()
    )
    if len(rows) > limit:
        next_row = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {"created_at": next_row.created_at.isoformat(), "id": str(next_row.id)},
                separators=(",", ":"),
            ).encode()
        ).decode()
        response.headers["X-Next-Cursor"] = next_cursor
        rows = rows[:limit]
    return [DocumentWebhookDeliveryResponse.model_validate(row) for row in rows]


@router.post(
    "/webhooks/{webhook_id}/deliveries/{delivery_id}/retry",
    status_code=202,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def retry_document_webhook_delivery(
    webhook_id: uuid.UUID,
    delivery_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_tenant_scope(request_tenant_id, auth)
    delivery = (
        db.query(DocumentWebhookDelivery)
        .filter(
            DocumentWebhookDelivery.id == delivery_id,
            DocumentWebhookDelivery.subscription_id == webhook_id,
            DocumentWebhookDelivery.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if delivery is None:
        raise ApiError(
            code="WEBHOOK_DELIVERY_NOT_FOUND", message="Delivery was not found.", status_code=404
        )
    subscription = (
        db.query(DocumentWebhookSubscription)
        .filter(
            DocumentWebhookSubscription.id == webhook_id,
            DocumentWebhookSubscription.tenant_id == auth.tenant_id,
        )
        .first()
    )
    if subscription is None:
        raise ApiError(
            code="WEBHOOK_NOT_FOUND", message="Webhook subscription was not found.", status_code=404
        )
    if not subscription.active:
        raise ApiError(
            code="WEBHOOK_INACTIVE",
            message="Resume the webhook before retrying a delivery.",
            status_code=409,
        )
    if delivery.status == "delivered":
        raise ApiError(
            code="WEBHOOK_DELIVERY_COMPLETE",
            message="This delivery already succeeded.",
            status_code=409,
        )
    delivery.status = "queued"
    delivery.error_message = None
    delivery.completed_at = None
    db.commit()
    from app.documents.workers.tasks_webhooks import deliver_document_webhook

    try:
        deliver_document_webhook.delay(
            subscription_id=str(webhook_id),
            delivery_id=str(delivery_id),
            tenant_id=str(auth.tenant_id),
            event=dict(delivery.payload or {}),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Webhook manual retry remained in the durable outbox")
    return {"id": str(delivery_id), "status": "queued"}


@router.post(
    "/{document_id}/share-links",
    response_model=DocumentShareLinkResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def create_document_share_link(
    document_id: uuid.UUID,
    payload: DocumentShareLinkCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentShareLinkResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    document = IngestionService(db=db, settings=settings).documents.get_by_id(
        tenant_id=auth.tenant_id, document_id=document_id
    )
    if document is None or document.uploaded_by_user_id != auth.user_id:
        raise ApiError(
            code="SHARE_LINK_FORBIDDEN",
            message="Only the document owner can create share links.",
            status_code=403,
        )
    token = secrets.token_urlsafe(32)
    row = DocumentShareLink(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        document_id=document_id,
        created_by_user_id=auth.user_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(seconds=payload.expires_in_seconds),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return DocumentShareLinkResponse(
        id=row.id,
        document_id=row.document_id,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
        share_token=token,
    )


@router.get(
    "/{document_id}/share-links",
    response_model=list[DocumentShareLinkResponse],
    dependencies=[Depends(require_permissions("documents:read"))],
)
def list_document_share_links(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[DocumentShareLinkResponse]:
    _enforce_tenant_scope(request_tenant_id, auth)
    document = IngestionService(db=db, settings=settings).documents.get_accessible_by_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
        include_quarantined=True,
    )
    if document is None:
        raise ApiError(code="DOCUMENT_NOT_FOUND", message="Document not found.", status_code=404)
    rows = (
        db.query(DocumentShareLink)
        .filter(
            DocumentShareLink.tenant_id == auth.tenant_id,
            DocumentShareLink.document_id == document_id,
        )
        .order_by(DocumentShareLink.created_at.desc())
        .all()
    )
    return [
        DocumentShareLinkResponse(
            id=row.id,
            document_id=row.document_id,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete(
    "/share-links/{link_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def revoke_document_share_link(
    link_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(DocumentShareLink)
        .filter(
            DocumentShareLink.id == link_id,
            DocumentShareLink.tenant_id == auth.tenant_id,
            DocumentShareLink.created_by_user_id == auth.user_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="SHARE_LINK_NOT_FOUND", message="Share link was not found.", status_code=404
        )
    row.revoked_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.get(
    "/share-links/{link_id}/resolve",
    response_model=DocumentShareLinkResolveResponse,
)
def resolve_document_share_link(
    link_id: uuid.UUID,
    token: str = Query(..., min_length=20, max_length=256),
    db: Session = Depends(get_db),
) -> DocumentShareLinkResolveResponse:
    # Token hashes are globally unique and the token is the only bearer
    # credential. Bypass is limited to this exact token lookup and document.
    set_db_tenant_context(db, "bypass")
    row = (
        db.query(DocumentShareLink)
        .filter(
            DocumentShareLink.id == link_id,
            DocumentShareLink.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        )
        .first()
    )
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise ApiError(
            code="SHARE_LINK_INVALID",
            message="This share link is invalid or expired.",
            status_code=404,
        )
    document = (
        db.query(Document)
        .filter(
            Document.id == row.document_id,
            Document.tenant_id == row.tenant_id,
            Document.is_deleted.is_(False),
        )
        .first()
    )
    if document is None:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND",
            message="The shared document is no longer available.",
            status_code=404,
        )
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.tenant_id == row.tenant_id, DocumentChunk.document_id == row.document_id
        )
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    return DocumentShareLinkResolveResponse(
        document_id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        expires_at=row.expires_at,
        content="\n\n".join(chunk.content for chunk in chunks),
    )


@router.get("/share-links/{link_id}/download")
def download_shared_document(
    link_id: uuid.UUID,
    token: str = Query(..., min_length=20, max_length=256),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Download the original shared file after validating the bearer token."""
    set_db_tenant_context(db, "bypass")
    row = (
        db.query(DocumentShareLink)
        .filter(
            DocumentShareLink.id == link_id,
            DocumentShareLink.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        )
        .first()
    )
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise ApiError(
            code="SHARE_LINK_INVALID",
            message="This share link is invalid or expired.",
            status_code=404,
        )
    document = (
        db.query(Document)
        .filter(
            Document.id == row.document_id,
            Document.tenant_id == row.tenant_id,
            Document.is_deleted.is_(False),
        )
        .first()
    )
    if document is None:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND",
            message="The shared document is no longer available.",
            status_code=404,
        )
    payload = StorageService(settings).get_bytes(
        bucket=document.storage_bucket,
        object_key=document.storage_object_key,
    )
    return Response(
        content=payload,
        media_type=document.content_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": _attachment_content_disposition(document.filename),
        },
    )


@router.get("/share-links/{link_id}/pages/{page_number}")
def render_shared_document_page(
    link_id: uuid.UUID,
    page_number: int,
    token: str = Query(..., min_length=20, max_length=256),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Render a page through the same visual pipeline as authenticated previews.

    The bearer token is checked before storage access. This endpoint deliberately
    exposes only the rendered page bytes, never the tenant, storage key, or
    authenticated document route.
    """
    if page_number < 1:
        raise ApiError(
            code="INVALID_PAGE_NUMBER", message="Page number must be positive.", status_code=422
        )
    set_db_tenant_context(db, "bypass")
    row = (
        db.query(DocumentShareLink)
        .filter(
            DocumentShareLink.id == link_id,
            DocumentShareLink.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        )
        .first()
    )
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise ApiError(
            code="SHARE_LINK_INVALID",
            message="This share link is invalid or expired.",
            status_code=404,
        )
    document = (
        db.query(Document)
        .filter(
            Document.id == row.document_id,
            Document.tenant_id == row.tenant_id,
            Document.is_deleted.is_(False),
        )
        .first()
    )
    if document is None:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND",
            message="The shared document is no longer available.",
            status_code=404,
        )
    payload = StorageService(settings).get_bytes(
        bucket=document.storage_bucket,
        object_key=document.storage_object_key,
    )
    is_pdf = document.content_type == "application/pdf" or document.filename.lower().endswith(
        ".pdf"
    )
    if is_pdf:
        rendered = PdfRenderService(settings).render_pdf_pages(
            payload=payload, page_numbers=[page_number]
        )
        return Response(
            content=rendered[0].image_bytes,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300", "X-Preview-Mode": "image"},
        )
    conversion = ConversionService(settings)
    if conversion.can_render_pdf(document.filename) and (
        shutil.which("soffice") or shutil.which("libreoffice")
    ):
        office_pdf = conversion.convert_to_pdf(filename=document.filename, payload=payload)
        rendered = PdfRenderService(settings).render_pdf_pages(
            payload=office_pdf, page_numbers=[page_number]
        )
        return Response(
            content=rendered[0].image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=300",
                "X-Preview-Mode": "image",
                "X-Preview-Source": "office-pdf-render",
            },
        )
    if document.content_type.startswith("image/"):
        if page_number != 1:
            raise ApiError(
                code="PAGE_NOT_FOUND",
                message="This image document has one preview page.",
                status_code=404,
            )
        return Response(
            content=payload,
            media_type=document.content_type,
            headers={"Cache-Control": "private, max-age=300", "X-Preview-Mode": "image"},
        )
    raise ApiError(
        code="PREVIEW_NOT_AVAILABLE",
        message="This shared file has no visual page renderer.",
        status_code=422,
    )


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
    return {
        "ticket": ticket,
        "expires_in_seconds": settings.document_event_stream_ticket_ttl_seconds,
    }


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
    "/{document_id}/pages/{page_number}",
    dependencies=[Depends(require_permissions("documents:read"))],
)
def render_document_page(
    document_id: uuid.UUID,
    page_number: int,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)
    if page_number < 1:
        raise ApiError(
            code="INVALID_PAGE_NUMBER", message="Page number must be positive.", status_code=422
        )
    service = IngestionService(db=db, settings=settings)
    document = service.get_document(
        tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id
    )
    payload = service.storage.get_bytes(
        bucket=document.storage_bucket, object_key=document.storage_object_key
    )

    # PDF pages are rendered as images so the existing zoom/thumbnail UI keeps
    # its exact visual behaviour.
    is_pdf = document.content_type == "application/pdf" or document.filename.lower().endswith(
        ".pdf"
    )
    if is_pdf:
        rendered = PdfRenderService(settings).render_pdf_pages(
            payload=payload, page_numbers=[page_number]
        )
        return Response(
            content=rendered[0].image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Preview-Mode": "image",
            },
        )

    conversion = ConversionService(settings)
    if conversion.can_render_pdf(document.filename) and (
        shutil.which("soffice") or shutil.which("libreoffice")
    ):
        office_pdf = conversion.convert_to_pdf(filename=document.filename, payload=payload)
        rendered = PdfRenderService(settings).render_pdf_pages(
            payload=office_pdf, page_numbers=[page_number]
        )
        return Response(
            content=rendered[0].image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=600",
                "X-Preview-Mode": "image",
                "X-Preview-Source": "office-pdf-render",
            },
        )
    # Browser-displayable images are already page-sized visual documents. Do
    # not send them through text extraction or report them as unsupported.
    if document.content_type.startswith("image/"):
        if page_number != 1:
            raise ApiError(
                code="PAGE_NOT_FOUND",
                message="This image document has one preview page.",
                status_code=404,
            )
        return Response(
            content=payload,
            media_type=document.content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Preview-Mode": "image",
            },
        )

    # Office, CSV, Markdown, JSON, email, and source-code files are extracted
    # into persisted chunks. Returning the requested page's chunks makes the
    # same preview surface useful for every format, even when the source has
    # no reliable visual page renderer (for example XLSX sheets or DOCX flow).
    page_chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.tenant_id == auth.tenant_id,
        )
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    exact_page = [
        chunk
        for chunk in page_chunks
        if isinstance(chunk.chunk_metadata, dict)
        and str(chunk.chunk_metadata.get("page_number", "")) == str(page_number)
    ]
    selected_chunks = exact_page or page_chunks
    if not selected_chunks:
        raise ApiError(
            code="PREVIEW_NOT_READY",
            message="Text preview is not available until document extraction completes.",
            status_code=409,
        )
    content = "\n\n".join(chunk.content for chunk in selected_chunks)
    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "Cache-Control": "private, max-age=60",
            "X-Preview-Mode": "text",
            "X-Preview-Page": str(page_number),
            "X-Preview-Page-Exact": "true" if exact_page else "false",
        },
    )


@router.get(
    "/{document_id}/pages/{page_number}/thumbnail",
    dependencies=[Depends(require_permissions("documents:read"))],
)
def render_document_page_thumbnail(
    document_id: uuid.UUID,
    page_number: int,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Render the same authenticated page surface with a cacheable thumbnail contract."""
    response = render_document_page(document_id, page_number, request_tenant_id, auth, db, settings)
    response.headers["X-Preview-Variant"] = "thumbnail"
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


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
    "/{document_id}/versions/diff",
    response_model=DocumentVersionDiffResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def compare_document_versions(
    document_id: uuid.UUID,
    compare_to: uuid.UUID = Query(...),  # noqa: B008
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentVersionDiffResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    left = service.get_document(
        tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id
    )
    right = service.get_document(
        tenant_id=auth.tenant_id, document_id=compare_to, user_id=auth.user_id
    )
    if left.filename != right.filename:
        raise ApiError(
            code="VERSION_LINEAGE_MISMATCH",
            message="Versions must belong to the same filename lineage.",
            status_code=409,
        )

    def content(document_id: uuid.UUID) -> list[str]:
        return [
            chunk.content
            for chunk in db.query(DocumentChunk)
            .filter(
                DocumentChunk.tenant_id == auth.tenant_id, DocumentChunk.document_id == document_id
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        ]

    left_lines, right_lines = content(left.id), content(right.id)
    diff = "".join(
        difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"v{left.version}",
            tofile=f"v{right.version}",
            lineterm="",
        )
    )
    return DocumentVersionDiffResponse(
        from_document_id=left.id,
        to_document_id=right.id,
        from_version=left.version,
        to_version=right.version,
        changed=left.sha256_hash != right.sha256_hash,
        unified_diff=diff[:200_000],
    )


@router.post(
    "/{document_id}/versions/{version_id}/restore",
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def restore_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    current = service.get_document(
        tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id
    )
    source = service.get_document(
        tenant_id=auth.tenant_id, document_id=version_id, user_id=auth.user_id
    )
    if current.filename != source.filename:
        raise ApiError(
            code="VERSION_LINEAGE_MISMATCH",
            message="Version does not belong to this document lineage.",
            status_code=409,
        )
    payload = service.storage.get_bytes(
        bucket=source.storage_bucket, object_key=source.storage_object_key
    )
    result = service.upload_document(
        auth=auth,
        idempotency_key=f"restore:{current.id}:{source.id}:{source.sha256_hash}",
        filename=current.filename,
        content_type=source.content_type,
        payload=payload,
    )
    return DocumentUploadResponse(
        document_id=result.document_id,
        status=result.status,
        ingestion_job_id=result.ingestion_job_id,
    )


@router.post(
    "/{document_id}/actions",
    response_model=DocumentAIActionResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def run_document_ai_action(
    document_id: uuid.UUID,
    payload: DocumentAIActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentAIActionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    service.get_document(tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id)
    target_ids = [document_id]
    if payload.compare_document_id is not None:
        service.get_document(
            tenant_id=auth.tenant_id, document_id=payload.compare_document_id, user_id=auth.user_id
        )
        target_ids.append(payload.compare_document_id)
    action_record = DocumentAIAction(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
        action=payload.action,
        instruction=payload.instruction or "",
        compare_document_id=payload.compare_document_id,
        status="running",
    )
    db.add(action_record)
    db.commit()
    prompts = {
        "summarize": "Provide a concise, grounded summary with key findings, limitations, and important entities.",
        "extract": "Extract the important structured facts, dates, people, organizations, metrics, and actions from the selected document.",
        "faqs": "Generate a useful FAQ with grounded answers from the selected document.",
        "compare": "Compare the selected documents and explain the material similarities, differences, and changes.",
    }
    instruction = payload.instruction.strip() if payload.instruction else ""
    from app.query.services.query_service import QueryService

    try:
        result = QueryService(db=db, settings=settings).execute(
            auth=auth,
            query_text=f"{prompts[payload.action]} {instruction}".strip(),
            top_k=20,
            filters={"document_ids": target_ids},
            document_ids=target_ids,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            conversation_id=None,
            search_mode="hybrid",
        )
    except Exception as exc:  # noqa: BLE001
        action_record.status = "failed"
        action_record.error_message = str(exc)[:4000]
        action_record.completed_at = datetime.now(UTC)
        db.commit()
        raise
    action_record.status = "completed"
    action_record.answer = (
        result.answer if isinstance(result.answer, str) else json.dumps(result.answer)
    )
    action_record.confidence = result.confidence
    action_record.citations = list(result.citations or [])
    action_record.trace_id = result.trace_id
    action_record.completed_at = datetime.now(UTC)
    db.commit()
    return DocumentAIActionResponse(
        action_id=action_record.id,
        action=payload.action,
        answer=result.answer,
        confidence=result.confidence,
        citations=result.citations,
        trace_id=result.trace_id,
    )


@router.get(
    "/actions/{action_id}",
    response_model=DocumentAIActionResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_ai_action(
    action_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DocumentAIActionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(DocumentAIAction)
        .filter(
            DocumentAIAction.id == action_id,
            DocumentAIAction.tenant_id == auth.tenant_id,
            DocumentAIAction.user_id == auth.user_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="AI_ACTION_NOT_FOUND", message="Document action was not found.", status_code=404
        )
    return DocumentAIActionResponse(
        action_id=row.id,
        action=row.action,
        answer=row.answer or "",
        confidence=row.confidence or 0.0,
        citations=list(row.citations or []),
        trace_id=row.trace_id or "",
    )


@router.get(
    "/{document_id}/comments",
    response_model=list[DocumentCommentResponse],
    dependencies=[Depends(require_permissions("documents:read"))],
)
def list_document_comments(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[DocumentCommentResponse]:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    service.get_document(tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id)
    rows = (
        db.query(Comment)
        .filter(
            Comment.tenant_id == auth.tenant_id,
            Comment.target_type == "document",
            Comment.target_id == document_id,
        )
        .order_by(Comment.created_at.asc())
        .all()
    )
    return [
        DocumentCommentResponse(
            id=row.id,
            document_id=document_id,
            user_id=row.user_id,
            content=row.content,
            mentions=[uuid.UUID(value) for value in (row.mentions or [])],
            parent_id=row.parent_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get(
    "/{document_id}/shares",
    response_model=list[DocumentShareResponse],
    dependencies=[Depends(require_permissions("documents:read"))],
)
def list_document_shares(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[DocumentShareResponse]:
    _enforce_tenant_scope(request_tenant_id, auth)
    document = IngestionService(db=db, settings=settings).documents.get_accessible_by_id(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
        include_quarantined=True,
    )
    if document is None:
        raise ApiError(code="DOCUMENT_NOT_FOUND", message="Document not found.", status_code=404)
    rows = (
        db.query(DocumentShare)
        .filter(DocumentShare.tenant_id == auth.tenant_id, DocumentShare.document_id == document_id)
        .order_by(DocumentShare.created_at.asc())
        .all()
    )
    return [DocumentShareResponse.model_validate(row) for row in rows]


@router.post(
    "/{document_id}/shares",
    response_model=DocumentShareResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def share_document(
    document_id: uuid.UUID,
    payload: DocumentShareCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentShareResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    document = IngestionService(db=db, settings=settings).documents.get_by_id(
        tenant_id=auth.tenant_id, document_id=document_id
    )
    if document is None or document.uploaded_by_user_id != auth.user_id:
        raise ApiError(
            code="DOCUMENT_SHARE_FORBIDDEN",
            message="Only the document owner can manage direct shares.",
            status_code=403,
        )
    recipient = (
        db.query(User.id)
        .filter(
            User.id == payload.user_id, User.tenant_id == auth.tenant_id, User.is_active.is_(True)
        )
        .first()
    )
    if recipient is None:
        raise ApiError(
            code="SHARE_RECIPIENT_NOT_FOUND",
            message="The recipient is not an active user in this tenant.",
            status_code=404,
        )
    row = (
        db.query(DocumentShare)
        .filter(
            DocumentShare.tenant_id == auth.tenant_id,
            DocumentShare.document_id == document_id,
            DocumentShare.user_id == payload.user_id,
        )
        .first()
    )
    if row is None:
        row = DocumentShare(
            id=generate_uuid7_with_fallback(),
            tenant_id=auth.tenant_id,
            document_id=document_id,
            user_id=payload.user_id,
            role=payload.role,
            created_by_user_id=auth.user_id,
        )
        db.add(row)
    else:
        row.role = payload.role
    db.commit()
    db.refresh(row)
    return DocumentShareResponse.model_validate(row)


@router.delete(
    "/{document_id}/shares/{share_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def revoke_document_share(
    document_id: uuid.UUID,
    share_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)
    document = IngestionService(db=db, settings=settings).documents.get_by_id(
        tenant_id=auth.tenant_id, document_id=document_id
    )
    if document is None or document.uploaded_by_user_id != auth.user_id:
        raise ApiError(
            code="DOCUMENT_SHARE_FORBIDDEN",
            message="Only the document owner can manage direct shares.",
            status_code=403,
        )
    row = (
        db.query(DocumentShare)
        .filter(
            DocumentShare.id == share_id,
            DocumentShare.tenant_id == auth.tenant_id,
            DocumentShare.document_id == document_id,
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="DOCUMENT_SHARE_NOT_FOUND", message="Share grant was not found.", status_code=404
        )
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.post(
    "/{document_id}/comments",
    response_model=DocumentCommentResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def create_document_comment(
    document_id: uuid.UUID,
    payload: DocumentCommentCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentCommentResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    service.get_document(tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id)
    if (
        payload.parent_id is not None
        and db.query(Comment.id)
        .filter(
            Comment.id == payload.parent_id,
            Comment.tenant_id == auth.tenant_id,
            Comment.target_type == "document",
            Comment.target_id == document_id,
        )
        .first()
        is None
    ):
        raise ApiError(
            code="COMMENT_PARENT_NOT_FOUND",
            message="Parent comment was not found.",
            status_code=404,
        )
    mentioned = list(dict.fromkeys(payload.mentions))
    valid_mentions = {
        user_id
        for (user_id,) in db.query(User.id)
        .filter(User.tenant_id == auth.tenant_id, User.id.in_(mentioned))
        .all()
    }
    if len(valid_mentions) != len(mentioned):
        raise ApiError(
            code="COMMENT_MENTION_FORBIDDEN",
            message="One or more mentioned users are not in this tenant.",
            status_code=422,
        )
    row = Comment(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        target_type="document",
        target_id=document_id,
        parent_id=payload.parent_id,
        content=payload.content.strip(),
        mentions=[str(user_id) for user_id in mentioned],
    )
    db.add(row)
    db.commit()
    return DocumentCommentResponse(
        id=row.id,
        document_id=document_id,
        user_id=row.user_id,
        content=row.content,
        mentions=[uuid.UUID(value) for value in (row.mentions or [])],
        parent_id=row.parent_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch(
    "/comments/{comment_id}",
    response_model=DocumentCommentResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def update_document_comment(
    comment_id: uuid.UUID,
    payload: DocumentCommentUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DocumentCommentResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(Comment)
        .filter(
            Comment.id == comment_id,
            Comment.tenant_id == auth.tenant_id,
            Comment.user_id == auth.user_id,
            Comment.target_type == "document",
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="COMMENT_NOT_FOUND",
            message="Comment not found or not owned by the current user.",
            status_code=404,
        )
    mentioned = list(dict.fromkeys(payload.mentions))
    valid_mentions = {
        user_id
        for (user_id,) in db.query(User.id)
        .filter(User.tenant_id == auth.tenant_id, User.id.in_(mentioned))
        .all()
    }
    if len(valid_mentions) != len(mentioned):
        raise ApiError(
            code="COMMENT_MENTION_FORBIDDEN",
            message="One or more mentioned users are not in this tenant.",
            status_code=422,
        )
    row.content = payload.content.strip()
    row.mentions = [str(user_id) for user_id in mentioned]
    db.commit()
    db.refresh(row)
    return DocumentCommentResponse(
        id=row.id,
        document_id=row.target_id,
        user_id=row.user_id,
        content=row.content,
        mentions=[uuid.UUID(value) for value in (row.mentions or [])],
        parent_id=row.parent_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete(
    "/comments/{comment_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def delete_document_comment(
    comment_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Response:
    _enforce_tenant_scope(request_tenant_id, auth)
    row = (
        db.query(Comment)
        .filter(
            Comment.id == comment_id,
            Comment.tenant_id == auth.tenant_id,
            Comment.user_id == auth.user_id,
            Comment.target_type == "document",
        )
        .first()
    )
    if row is None:
        raise ApiError(
            code="COMMENT_NOT_FOUND",
            message="Comment not found or not owned by the current user.",
            status_code=404,
        )
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get(
    "/{document_id}/quality",
    response_model=DocumentQualityResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_quality(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentQualityResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    document = service.get_document(
        tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id
    )
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.tenant_id == auth.tenant_id, DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    pages = sorted(
        {
            int(chunk.chunk_metadata["page_number"])
            for chunk in chunks
            if isinstance(chunk.chunk_metadata, dict)
            and str(chunk.chunk_metadata.get("page_number", "")).isdigit()
        }
    )
    missing = list(range(pages[0], pages[-1] + 1)) if pages else []
    missing = [page for page in missing if page not in pages]
    return DocumentQualityResponse(
        document_id=document.id,
        extraction_method=document.extraction_method,
        extraction_coverage_score=document.extraction_coverage_score,
        ocr_used=document.extraction_ocr_used,
        vision_used=document.extraction_vision_used,
        warnings=list(document.extraction_warnings or []),
        total_chunks=len(chunks),
        low_quality_chunks=sum(
            1 for chunk in chunks if chunk.quality_score is not None and chunk.quality_score < 0.5
        ),
        page_numbers=pages,
        missing_page_numbers=missing,
    )


@router.post(
    "/bulk/resume",
    response_model=BulkDocumentActionResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def bulk_resume_documents(
    payload: BulkDocumentActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkDocumentActionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    accepted: list[uuid.UUID] = []
    failed: dict[str, str] = {}
    for document_id in dict.fromkeys(payload.document_ids):
        if document_id not in accessible:
            failed[str(document_id)] = "Document is not accessible."
            continue
        try:
            service.resume_document_from_checkpoint(
                tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id
            )
            accepted.append(document_id)
        except ApiError as exc:
            failed[str(document_id)] = exc.message
    return BulkDocumentActionResponse(
        requested_count=len(payload.document_ids),
        accepted_ids=accepted,
        failed=failed,
        operation="resume",
    )


@router.post(
    "/bulk/retry",
    response_model=BulkDocumentActionResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def bulk_retry_documents(
    payload: BulkDocumentActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkDocumentActionResponse:
    """Retry only failed/dead-lettered jobs while preserving checkpointed progress."""
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    accepted: list[uuid.UUID] = []
    failed: dict[str, str] = {}
    for document_id in dict.fromkeys(payload.document_ids):
        if document_id not in accessible:
            failed[str(document_id)] = "Document is not accessible."
            continue
        document = service.documents.get_by_id(tenant_id=auth.tenant_id, document_id=document_id)
        if document is None or document.status not in {
            "failed",
            "dead_lettered",
            "needs_reingestion",
        }:
            failed[str(document_id)] = "Document is not in a retryable state."
            continue
        try:
            service.resume_document_from_checkpoint(
                tenant_id=auth.tenant_id, document_id=document_id, user_id=auth.user_id
            )
            accepted.append(document_id)
        except ApiError as exc:
            failed[str(document_id)] = exc.message
    return BulkDocumentActionResponse(
        requested_count=len(payload.document_ids),
        accepted_ids=accepted,
        failed=failed,
        operation="retry",
    )


@router.post(
    "/bulk/reprocess",
    response_model=BulkDocumentActionResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def bulk_reprocess_documents(
    payload: BulkDocumentActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkDocumentActionResponse:
    """Queue a bounded batch for a clean, explicit reprocessing pass."""
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    accepted: list[uuid.UUID] = []
    failed: dict[str, str] = {}
    for document_id in dict.fromkeys(payload.document_ids):
        if document_id not in accessible:
            failed[str(document_id)] = "Document is not accessible."
            continue
        document = service.documents.get_accessible_by_id(
            tenant_id=auth.tenant_id,
            document_id=document_id,
            user_id=auth.user_id,
            include_quarantined=True,
        )
        if document is None or not document.storage_bucket or not document.storage_object_key:
            failed[str(document_id)] = "Document source is unavailable."
            continue
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
            tenant_id=auth.tenant_id, document_id=document_id
        ):
            if existing_job.status in {"queued", "downloading", "parsing", "chunking", "embedding"}:
                service.jobs.set_status(
                    tenant_id=auth.tenant_id,
                    job=existing_job,
                    status="failed",
                    error_code="SUPERSEDED_JOB",
                    error_message="Superseded by bulk document reprocessing.",
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
        service._enqueue_ingestion(
            job_id=job.id,
            tenant_id=auth.tenant_id,
            queue=_choose_ingestion_queue(document.filename),
        )
        accepted.append(document_id)
    db.commit()
    _safe_audit_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="documents.bulk_reprocess",
        resource_type="document",
        resource_id="batch",
        actor_user_id=auth.user_id,
        details={"accepted_count": len(accepted), "failed_count": len(failed)},
    )
    return BulkDocumentActionResponse(
        requested_count=len(payload.document_ids),
        accepted_ids=accepted,
        failed=failed,
        operation="reprocess",
    )


@router.post(
    "/bulk/export",
    response_model=None,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def bulk_export_documents(
    payload: BulkDocumentExportRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Export accessible source files into a bounded private ZIP archive."""
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    requested_ids = list(dict.fromkeys(payload.document_ids))
    documents = []
    for document_id in requested_ids:
        document = service.documents.get_accessible_by_id(
            tenant_id=auth.tenant_id,
            document_id=document_id,
            user_id=auth.user_id,
            include_quarantined=True,
        )
        if document is None:
            raise ApiError(
                code="DOCUMENT_NOT_FOUND",
                message="One or more documents are not accessible.",
                status_code=404,
            )
        documents.append(document)
    if (
        sum(max(0, int(document.size_bytes or 0)) for document in documents)
        > _MAX_DOCUMENT_EXPORT_BYTES
    ):
        raise ApiError(
            code="EXPORT_TOO_LARGE",
            message="The selected documents exceed the safe export size limit.",
            status_code=413,
        )
    archive = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as output:
        for document in documents:
            if not document.storage_bucket or not document.storage_object_key:
                raise ApiError(
                    code="DOCUMENT_SOURCE_UNAVAILABLE",
                    message="A selected document has no source object.",
                    status_code=409,
                )
            name = Path(document.filename).name or f"document-{document.id}"
            candidate = name
            index = 2
            while candidate in used_names:
                stem, suffix = Path(name).stem, Path(name).suffix
                candidate = f"{stem} ({index}){suffix}"
                index += 1
            used_names.add(candidate)
            output.writestr(
                candidate,
                service.storage.get_bytes(
                    bucket=document.storage_bucket, object_key=document.storage_object_key
                ),
            )
    payload_bytes = archive.getvalue()
    return StreamingResponse(
        iter([payload_bytes]),
        media_type="application/zip",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Length": str(len(payload_bytes)),
            "Content-Disposition": "attachment; filename=documents-export.zip",
        },
    )


@router.post(
    "/bulk/tag",
    response_model=BulkDocumentActionResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def bulk_tag_documents(
    payload: BulkDocumentActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkDocumentActionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    tag_ids = list(dict.fromkeys(payload.tag_ids or ([payload.tag_id] if payload.tag_id else [])))
    if not tag_ids:
        raise ApiError(code="TAG_REQUIRED", message="tag_id is required.", status_code=422)
    service = IngestionService(db=db, settings=settings)
    valid_tag_ids = {
        row[0]
        for row in db.query(DocumentTag.id)
        .filter(DocumentTag.id.in_(tag_ids), DocumentTag.tenant_id == auth.tenant_id)
        .all()
    }
    if len(valid_tag_ids) != len(tag_ids):
        raise ApiError(code="DOCUMENT_TAG_NOT_FOUND", message="Tag was not found.", status_code=404)
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    accepted: list[uuid.UUID] = []
    failed: dict[str, str] = {}
    for document_id in dict.fromkeys(payload.document_ids):
        if document_id not in accessible:
            failed[str(document_id)] = "Document is not accessible."
            continue
        for tag_id in tag_ids:
            exists = (
                db.query(DocumentTagAssignment.id)
                .filter(
                    DocumentTagAssignment.tenant_id == auth.tenant_id,
                    DocumentTagAssignment.document_id == document_id,
                    DocumentTagAssignment.tag_id == tag_id,
                )
                .first()
            )
            if not exists:
                db.add(
                    DocumentTagAssignment(
                        id=generate_uuid7_with_fallback(),
                        tenant_id=auth.tenant_id,
                        document_id=document_id,
                        tag_id=tag_id,
                    )
                )
        accepted.append(document_id)
    db.commit()
    return BulkDocumentActionResponse(
        requested_count=len(payload.document_ids),
        accepted_ids=accepted,
        failed=failed,
        operation="tag",
    )


@router.post(
    "/bulk/untag",
    response_model=BulkDocumentActionResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def bulk_untag_documents(
    payload: BulkDocumentActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkDocumentActionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    tag_ids = list(dict.fromkeys(payload.tag_ids or ([payload.tag_id] if payload.tag_id else [])))
    if not tag_ids:
        raise ApiError(
            code="TAG_REQUIRED", message="At least one tag is required.", status_code=422
        )
    service = IngestionService(db=db, settings=settings)
    valid_tag_ids = {
        row[0]
        for row in db.query(DocumentTag.id)
        .filter(DocumentTag.id.in_(tag_ids), DocumentTag.tenant_id == auth.tenant_id)
        .all()
    }
    if len(valid_tag_ids) != len(tag_ids):
        raise ApiError(code="DOCUMENT_TAG_NOT_FOUND", message="Tag was not found.", status_code=404)
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    accepted: list[uuid.UUID] = []
    failed: dict[str, str] = {}
    for document_id in dict.fromkeys(payload.document_ids):
        if document_id not in accessible:
            failed[str(document_id)] = "Document is not accessible."
            continue
        db.query(DocumentTagAssignment).filter(
            DocumentTagAssignment.tenant_id == auth.tenant_id,
            DocumentTagAssignment.document_id == document_id,
            DocumentTagAssignment.tag_id.in_(tag_ids),
        ).delete(synchronize_session=False)
        accepted.append(document_id)
    db.commit()
    return BulkDocumentActionResponse(
        requested_count=len(payload.document_ids),
        accepted_ids=accepted,
        failed=failed,
        operation="untag",
    )


@router.post(
    "/bulk/move",
    response_model=BulkDocumentActionResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def bulk_move_documents(
    payload: BulkDocumentActionRequest,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BulkDocumentActionResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    if payload.folder_id is None:
        raise ApiError(code="FOLDER_REQUIRED", message="folder_id is required.", status_code=422)
    service = IngestionService(db=db, settings=settings)
    if (
        db.query(DocumentFolder.id)
        .filter(DocumentFolder.id == payload.folder_id, DocumentFolder.tenant_id == auth.tenant_id)
        .first()
        is None
    ):
        raise ApiError(
            code="DOCUMENT_FOLDER_NOT_FOUND", message="Folder was not found.", status_code=404
        )
    accessible = service.documents.get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    accepted: list[uuid.UUID] = []
    failed: dict[str, str] = {}
    for document_id in dict.fromkeys(payload.document_ids):
        if document_id not in accessible:
            failed[str(document_id)] = "Document is not accessible."
            continue
        db.query(DocumentFolderAssignment).filter(
            DocumentFolderAssignment.tenant_id == auth.tenant_id,
            DocumentFolderAssignment.document_id == document_id,
        ).delete(synchronize_session=False)
        db.add(
            DocumentFolderAssignment(
                id=generate_uuid7_with_fallback(),
                tenant_id=auth.tenant_id,
                document_id=document_id,
                folder_id=payload.folder_id,
            )
        )
        accepted.append(document_id)
    db.commit()
    return BulkDocumentActionResponse(
        requested_count=len(payload.document_ids),
        accepted_ids=accepted,
        failed=failed,
        operation="move",
    )


@router.get(
    "/ops/observability",
    response_model=DocumentObservabilityResponse,
    dependencies=[Depends(require_permissions("documents:read"))],
)
def get_document_observability(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentObservabilityResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    service = IngestionService(db=db, settings=settings)
    status_counts = service.documents.status_counts_by_tenant(tenant_id=auth.tenant_id)
    total = service.documents.count_by_tenant(tenant_id=auth.tenant_id)
    return DocumentObservabilityResponse(
        status_counts=status_counts,
        active_ingestion_jobs=service.jobs.count_active_by_tenant(tenant_id=auth.tenant_id),
        failed_documents=service.documents.count_error_by_tenant(tenant_id=auth.tenant_id),
        quarantined_documents=service.documents.count_quarantined_by_tenant(
            tenant_id=auth.tenant_id
        ),
        total_documents=total,
        indexed_documents=status_counts.get("indexed", 0),
        storage_bytes=service.documents.sum_storage_by_tenant(tenant_id=auth.tenant_id),
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
        filename=status.filename,
        content_type=status.content_type,
        size_bytes=status.size_bytes,
        sha256_hash=status.sha256_hash,
        language=status.language,
        version=status.version,
        created_at=status.created_at,
        updated_at=status.updated_at,
        security_scan_result=status.security_scan_result,
        security_scan_reason=status.security_scan_reason,
        security_scanned_at=status.security_scanned_at,
        security_scan_required=status.security_scan_required,
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
        total_chunk_count=status.total_chunk_count,
        embedded_chunk_count=status.embedded_chunk_count,
        average_chunk_quality=status.average_chunk_quality,
        recovery_available=status.recovery_available,
        recovery_stage=status.recovery_stage,
        recovery_reason=status.recovery_reason,
        last_checkpoint_at=status.last_checkpoint_at,
        remaining_chunk_count=status.remaining_chunk_count,
        resume_count=status.resume_count,
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


@router.post(
    "/{document_id}/resume",
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_permissions("documents:upload"))],
)
def resume_document(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    _enforce_tenant_scope(request_tenant_id, auth)
    result = IngestionService(db=db, settings=settings).resume_document_from_checkpoint(
        tenant_id=auth.tenant_id,
        document_id=document_id,
        user_id=auth.user_id,
    )
    return DocumentUploadResponse(
        document_id=result.document_id,
        status=result.status,
        ingestion_job_id=result.ingestion_job_id,
    )


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
