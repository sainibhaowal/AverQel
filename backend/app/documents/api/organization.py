from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.auth.tenancy import require_request_tenant_id
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.organization import (
    DocumentAutomationSchedule,
    DocumentAutomationScheduleRule,
    DocumentAutomationScheduleRun,
    DocumentClassificationApplication,
    DocumentClassificationRule,
    DocumentClassificationRun,
    DocumentFolder,
    DocumentFolderAssignment,
    DocumentSavedView,
    DocumentSmartCollection,
    DocumentSmartCollectionEvaluation,
    DocumentTag,
    DocumentTagAssignment,
)
from app.documents.repositories.documents import DocumentsRepository
from app.documents.services.classification_service import ClassificationService
from app.documents.services.schedule_service import next_schedule_run, validate_schedule_settings
from app.documents.services.smart_collection_service import (
    SmartCollectionValidationError,
    new_evaluation,
    normalize_conditions,
)
from app.documents.services.smart_collection_service import (
    evaluate_smart_collection as evaluate_smart_collection_page,
)
from app.platform.database.session import get_db, set_db_tenant_context

router = APIRouter(prefix="/documents/organization", tags=["documents-organization"])


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = Field(default="emerald", max_length=32)
    model_config = ConfigDict(extra="forbid")


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    model_config = ConfigDict(extra="forbid")


class RenamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    model_config = ConfigDict(extra="forbid")


class TagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = Field(default="emerald", max_length=32)
    model_config = ConfigDict(extra="forbid")


class SavedViewFilters(BaseModel):
    """The durable, API-safe subset of the Documents Hub filter contract."""

    q: str | None = Field(default=None, max_length=256)
    status: str | None = Field(default=None, max_length=32)
    content_type: str | None = Field(default=None, max_length=128)
    ocr_used: bool | None = None
    quarantined: bool | None = None
    tag_id: uuid.UUID | None = None
    created_from: date | None = None
    created_to: date | None = None
    model_config = ConfigDict(extra="forbid")


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    filters: SavedViewFilters = Field(default_factory=SavedViewFilters)
    description: str = Field(default="", max_length=2000)
    model_config = ConfigDict(extra="forbid")


class SavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    filters: SavedViewFilters | None = None
    description: str | None = Field(default=None, max_length=2000)
    model_config = ConfigDict(extra="forbid")


def _saved_view_filters(filters: object) -> SavedViewFilters:
    """Validate persisted JSON too, while keeping old empty records readable."""
    if not isinstance(filters, dict):
        return SavedViewFilters()
    try:
        return SavedViewFilters.model_validate(filters)
    except ValueError as exc:
        raise ApiError(
            code="DOCUMENT_SAVED_VIEW_FILTERS_INVALID",
            message="This saved view contains invalid filters and must be edited before it can run.",
            status_code=422,
        ) from exc


def _saved_view_filter_json(filters: SavedViewFilters) -> dict:
    return filters.model_dump(mode="json", exclude_none=True)


def _validate_classification_targets(
    *,
    tenant_id: uuid.UUID,
    tag_id: uuid.UUID | None,
    folder_id: uuid.UUID | None,
    db: Session,
) -> None:
    if (
        tag_id
        and db.scalar(
            select(DocumentTag.id).where(
                DocumentTag.id == tag_id, DocumentTag.tenant_id == tenant_id
            )
        )
        is None
    ):
        raise ApiError(
            code="DOCUMENT_TAG_NOT_FOUND",
            message="Tag was not found in this organization.",
            status_code=404,
        )
    if (
        folder_id
        and db.scalar(
            select(DocumentFolder.id).where(
                DocumentFolder.id == folder_id, DocumentFolder.tenant_id == tenant_id
            )
        )
        is None
    ):
        raise ApiError(
            code="DOCUMENT_FOLDER_NOT_FOUND",
            message="Folder was not found in this organization.",
            status_code=404,
        )


def _classification_run_response(run: DocumentClassificationRun) -> dict:
    return {
        "id": run.id,
        "rule_id": run.rule_id,
        "actor_user_id": run.actor_user_id,
        "source": run.source,
        "status": run.status,
        "scanned_count": run.scanned_count,
        "matched_count": run.matched_count,
        "applied_count": run.applied_count,
        "failed_count": run.failed_count,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def _classification_rule_response(rule: DocumentClassificationRule, db: Session) -> dict:
    last_run = db.scalar(
        select(DocumentClassificationRun)
        .where(
            DocumentClassificationRun.tenant_id == rule.tenant_id,
            DocumentClassificationRun.rule_id == rule.id,
        )
        .order_by(DocumentClassificationRun.created_at.desc(), DocumentClassificationRun.id.desc())
        .limit(1)
    )
    tag_name = (
        db.scalar(select(DocumentTag.name).where(DocumentTag.id == rule.tag_id))
        if rule.tag_id
        else None
    )
    folder_name = (
        db.scalar(select(DocumentFolder.name).where(DocumentFolder.id == rule.folder_id))
        if rule.folder_id
        else None
    )
    return {
        "id": rule.id,
        "name": rule.name,
        "filename_pattern": rule.filename_pattern,
        "content_type": rule.content_type,
        "tag_id": rule.tag_id,
        "tag_name": tag_name,
        "folder_id": rule.folder_id,
        "folder_name": folder_name,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "last_run": _classification_run_response(last_run) if last_run else None,
    }


class SmartCollectionCondition(BaseModel):
    field: str = Field(
        pattern="^(status|quarantined|ocr_confidence|content_type|filename|tag|folder)$"
    )
    operator: str = Field(
        pattern="^(equals|not_equals|contains|starts_with|greater_than|less_than)$"
    )
    value: str | float | bool
    model_config = ConfigDict(extra="forbid")


class SmartCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    match_mode: str = Field(default="all", pattern="^(all|any)$")
    conditions: list[SmartCollectionCondition] = Field(min_length=1, max_length=12)
    model_config = ConfigDict(extra="forbid")


class SmartCollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    match_mode: str | None = Field(default=None, pattern="^(all|any)$")
    conditions: list[SmartCollectionCondition] | None = Field(
        default=None, min_length=1, max_length=12
    )
    enabled: bool | None = None
    model_config = ConfigDict(extra="forbid")


class ClassificationRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    filename_pattern: str = Field(default="*", min_length=1, max_length=256)
    content_type: str | None = Field(default=None, max_length=128)
    tag_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    priority: int = Field(default=100, ge=0, le=10000)
    enabled: bool = True
    model_config = ConfigDict(extra="forbid")


class ClassificationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    filename_pattern: str | None = Field(default=None, min_length=1, max_length=256)
    content_type: str | None = Field(default=None, max_length=128)
    tag_id: uuid.UUID | None = None
    folder_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    enabled: bool | None = None
    model_config = ConfigDict(extra="forbid")


class AutomationScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    interval_seconds: int = Field(default=3600, ge=60, le=31_536_000)
    cadence: str = Field(default="interval", pattern="^(interval|hourly|daily|weekly)$")
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    run_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekday: int | None = Field(default=None, ge=0, le=6)
    rule_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    enabled: bool = True
    model_config = ConfigDict(extra="forbid")


class AutomationScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    interval_seconds: int | None = Field(default=None, ge=60, le=31_536_000)
    cadence: str | None = Field(default=None, pattern="^(interval|hourly|daily|weekly)$")
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    run_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekday: int | None = Field(default=None, ge=0, le=6)
    rule_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    enabled: bool | None = None
    model_config = ConfigDict(extra="forbid")


def _scope(request_tenant_id: uuid.UUID, auth: AuthContext, db: Session) -> None:
    if request_tenant_id != auth.tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH", message="Tenant scope mismatch.", status_code=403
        )
    set_db_tenant_context(db, auth.tenant_id)


@router.get("/tags", dependencies=[Depends(require_permissions("documents:organization:basic"))])
def list_tags(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    usage_rows = db.execute(
        select(DocumentTagAssignment.tag_id, func.count(DocumentTagAssignment.document_id))
        .where(DocumentTagAssignment.tenant_id == auth.tenant_id)
        .group_by(DocumentTagAssignment.tag_id)
    ).all()
    usage = {tag_id: int(count) for tag_id, count in usage_rows}
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "color": row.color,
                "usage_count": usage.get(row.id, 0),
            }
            for row in db.scalars(
                select(DocumentTag)
                .where(DocumentTag.tenant_id == auth.tenant_id)
                .order_by(DocumentTag.name)
            ).all()
        ]
    }


@router.get(
    "/tags/assignments", dependencies=[Depends(require_permissions("documents:organization:basic"))]
)
def list_tag_assignments(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Return persisted tag assignments for the user's accessible documents."""
    _scope(request_tenant_id, auth, db)
    accessible = DocumentsRepository(db).get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    rows = (
        db.execute(
            select(DocumentTagAssignment.document_id, DocumentTagAssignment.tag_id).where(
                DocumentTagAssignment.tenant_id == auth.tenant_id,
                DocumentTagAssignment.document_id.in_(accessible),
            )
        ).all()
        if accessible
        else []
    )
    assignments: dict[str, list[uuid.UUID]] = {}
    for document_id, tag_id in rows:
        assignments.setdefault(str(document_id), []).append(tag_id)
    return {
        "items": [
            {"document_id": document_id, "tag_ids": tag_ids}
            for document_id, tag_ids in assignments.items()
        ]
    }


@router.post("/tags", dependencies=[Depends(require_permissions("documents:organization:basic"))])
def create_tag(
    payload: TagCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    tag = DocumentTag(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        name=payload.name.strip(),
        color=payload.color.strip() or "emerald",
    )
    db.add(tag)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="DOCUMENT_TAG_EXISTS",
            message="A tag with this name already exists.",
            status_code=409,
        ) from exc
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.patch(
    "/tags/{tag_id}", dependencies=[Depends(require_permissions("documents:organization:basic"))]
)
def rename_tag(
    tag_id: uuid.UUID,
    payload: TagUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    tag = db.scalar(
        select(DocumentTag).where(DocumentTag.id == tag_id, DocumentTag.tenant_id == auth.tenant_id)
    )
    if tag is None:
        raise ApiError(code="DOCUMENT_TAG_NOT_FOUND", message="Tag was not found.", status_code=404)
    tag.name = payload.name.strip()
    tag.color = payload.color.strip() or "emerald"
    db.commit()
    usage_count = (
        db.query(func.count(DocumentTagAssignment.document_id))
        .filter(
            DocumentTagAssignment.tenant_id == auth.tenant_id,
            DocumentTagAssignment.tag_id == tag.id,
        )
        .scalar()
        or 0
    )
    return {"id": tag.id, "name": tag.name, "color": tag.color, "usage_count": int(usage_count)}


@router.delete(
    "/tags/{tag_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:basic"))],
)
def delete_tag(
    tag_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    tag = db.scalar(
        select(DocumentTag).where(DocumentTag.id == tag_id, DocumentTag.tenant_id == auth.tenant_id)
    )
    if tag is None:
        raise ApiError(code="DOCUMENT_TAG_NOT_FOUND", message="Tag was not found.", status_code=404)
    db.delete(tag)
    db.commit()


@router.get("/folders", dependencies=[Depends(require_permissions("documents:organization:basic"))])
def list_folders(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rows = db.scalars(
        select(DocumentFolder)
        .where(DocumentFolder.tenant_id == auth.tenant_id)
        .order_by(DocumentFolder.name)
    ).all()
    return {"items": [{"id": row.id, "name": row.name, "parent_id": row.parent_id} for row in rows]}


@router.post(
    "/folders", dependencies=[Depends(require_permissions("documents:organization:basic"))]
)
def create_folder(
    payload: FolderCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    if (
        payload.parent_id
        and db.scalar(
            select(DocumentFolder.id).where(
                DocumentFolder.id == payload.parent_id, DocumentFolder.tenant_id == auth.tenant_id
            )
        )
        is None
    ):
        raise ApiError(
            code="DOCUMENT_FOLDER_NOT_FOUND",
            message="Parent folder was not found.",
            status_code=404,
        )
    folder = DocumentFolder(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        parent_id=payload.parent_id,
        name=payload.name.strip(),
    )
    db.add(folder)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="DOCUMENT_FOLDER_EXISTS",
            message="A folder with this name already exists here.",
            status_code=409,
        ) from exc
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


@router.patch(
    "/folders/{folder_id}",
    dependencies=[Depends(require_permissions("documents:organization:basic"))],
)
def rename_folder(
    folder_id: uuid.UUID,
    payload: RenamePayload,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    folder = db.scalar(
        select(DocumentFolder).where(
            DocumentFolder.id == folder_id, DocumentFolder.tenant_id == auth.tenant_id
        )
    )
    if folder is None:
        raise ApiError(
            code="DOCUMENT_FOLDER_NOT_FOUND", message="Folder was not found.", status_code=404
        )
    folder.name = payload.name.strip()
    db.commit()
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


@router.delete(
    "/folders/{folder_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:basic"))],
)
def delete_folder(
    folder_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    folder = db.scalar(
        select(DocumentFolder).where(
            DocumentFolder.id == folder_id, DocumentFolder.tenant_id == auth.tenant_id
        )
    )
    if folder is None:
        raise ApiError(
            code="DOCUMENT_FOLDER_NOT_FOUND", message="Folder was not found.", status_code=404
        )
    db.delete(folder)
    db.commit()


@router.get(
    "/folders/{folder_id}/documents",
    dependencies=[Depends(require_permissions("documents:organization:basic"))],
)
def list_folder_documents(
    folder_id: str,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Return accessible files assigned to a folder; null folder_id returns unfiled files."""
    from app.documents.models.document import Document

    _scope(request_tenant_id, auth, db)
    accessible = DocumentsRepository(db).get_accessible_document_ids(
        tenant_id=auth.tenant_id, user_id=auth.user_id, include_quarantined=True
    )
    try:
        requested_folder_id: uuid.UUID | None = (
            None if folder_id == "unfiled" else uuid.UUID(folder_id)
        )
    except ValueError as exc:
        raise ApiError(
            code="DOCUMENT_FOLDER_NOT_FOUND", message="Folder was not found.", status_code=404
        ) from exc
    assignment_query = select(DocumentFolderAssignment.document_id)
    if requested_folder_id is None:
        assignment_query = assignment_query.where(DocumentFolderAssignment.folder_id.is_not(None))
    else:
        if (
            db.scalar(
                select(DocumentFolder.id).where(
                    DocumentFolder.id == requested_folder_id,
                    DocumentFolder.tenant_id == auth.tenant_id,
                )
            )
            is None
        ):
            raise ApiError(
                code="DOCUMENT_FOLDER_NOT_FOUND", message="Folder was not found.", status_code=404
            )
        assignment_query = assignment_query.where(
            DocumentFolderAssignment.folder_id == requested_folder_id
        )
    assigned_ids = set(
        db.scalars(
            assignment_query.where(DocumentFolderAssignment.tenant_id == auth.tenant_id)
        ).all()
    )
    document_ids = (
        accessible & assigned_ids if requested_folder_id is not None else accessible - assigned_ids
    )
    rows = (
        db.scalars(
            select(Document)
            .where(
                Document.tenant_id == auth.tenant_id,
                Document.id.in_(document_ids),
                Document.is_deleted.is_(False),
            )
            .order_by(Document.filename)
        ).all()
        if document_ids
        else []
    )
    return {
        "items": [
            {
                "document_id": row.id,
                "filename": row.filename,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "status": row.status,
                "quarantined": row.quarantined,
                "processing_progress": row.processing_progress,
            }
            for row in rows
        ]
    }


@router.get(
    "/saved-views", dependencies=[Depends(require_permissions("documents:organization:advanced"))]
)
def list_saved_views(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rows = db.scalars(
        select(DocumentSavedView)
        .where(
            DocumentSavedView.tenant_id == auth.tenant_id, DocumentSavedView.user_id == auth.user_id
        )
        .order_by(DocumentSavedView.name)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "filters": _saved_view_filter_json(_saved_view_filters(row.filters)),
                "description": row.description,
            }
            for row in rows
        ]
    }


@router.post(
    "/saved-views", dependencies=[Depends(require_permissions("documents:organization:advanced"))]
)
def create_saved_view(
    payload: SavedViewCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    view = DocumentSavedView(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        name=payload.name.strip(),
        filters=_saved_view_filter_json(payload.filters),
        description=payload.description.strip(),
    )
    db.add(view)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="DOCUMENT_SAVED_VIEW_EXISTS",
            message="A saved view with this name already exists.",
            status_code=409,
        ) from exc
    return {
        "id": view.id,
        "name": view.name,
        "filters": _saved_view_filter_json(_saved_view_filters(view.filters)),
        "description": view.description,
    }


@router.patch(
    "/saved-views/{view_id}",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def update_saved_view(
    view_id: uuid.UUID,
    payload: SavedViewUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    view = db.scalar(
        select(DocumentSavedView).where(
            DocumentSavedView.id == view_id,
            DocumentSavedView.tenant_id == auth.tenant_id,
            DocumentSavedView.user_id == auth.user_id,
        )
    )
    if view is None:
        raise ApiError(
            code="DOCUMENT_SAVED_VIEW_NOT_FOUND",
            message="Saved view was not found.",
            status_code=404,
        )
    if payload.name is not None:
        view.name = payload.name.strip()
    if payload.filters is not None:
        view.filters = _saved_view_filter_json(payload.filters)
    if payload.description is not None:
        view.description = payload.description.strip()
    db.commit()
    return {
        "id": view.id,
        "name": view.name,
        "filters": _saved_view_filter_json(_saved_view_filters(view.filters)),
        "description": view.description,
    }


@router.delete(
    "/saved-views/{view_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def delete_saved_view(
    view_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    view = db.scalar(
        select(DocumentSavedView).where(
            DocumentSavedView.id == view_id,
            DocumentSavedView.tenant_id == auth.tenant_id,
            DocumentSavedView.user_id == auth.user_id,
        )
    )
    if view is None:
        raise ApiError(
            code="DOCUMENT_SAVED_VIEW_NOT_FOUND",
            message="Saved view was not found.",
            status_code=404,
        )
    db.delete(view)
    db.commit()


@router.get(
    "/saved-views/{view_id}/documents",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def evaluate_saved_view(
    view_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Evaluate a saved view against the same tenant/access query used by search."""
    _scope(request_tenant_id, auth, db)
    view = db.scalar(
        select(DocumentSavedView).where(
            DocumentSavedView.id == view_id,
            DocumentSavedView.tenant_id == auth.tenant_id,
            DocumentSavedView.user_id == auth.user_id,
        )
    )
    if view is None:
        raise ApiError(
            code="DOCUMENT_SAVED_VIEW_NOT_FOUND",
            message="Saved view was not found.",
            status_code=404,
        )
    filters = _saved_view_filters(view.filters)
    created_from = (
        datetime.combine(filters.created_from, time.min, tzinfo=UTC)
        if filters.created_from
        else None
    )
    created_to = (
        datetime.combine(filters.created_to, time.max, tzinfo=UTC) if filters.created_to else None
    )
    rows, total = DocumentsRepository(db).search_accessible_for_user(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        query_text=filters.q.strip() if filters.q and filters.q.strip() else None,
        statuses=[filters.status] if filters.status else None,
        content_type=(
            filters.content_type.strip()
            if filters.content_type and filters.content_type.strip()
            else None
        ),
        ocr_used=filters.ocr_used,
        quarantined=filters.quarantined,
        created_from=created_from,
        created_to=created_to,
        tag_ids=[filters.tag_id] if filters.tag_id else None,
        limit=500,
    )
    return {
        "view_id": view.id,
        "name": view.name,
        "description": view.description,
        "filters": _saved_view_filter_json(filters),
        "total": total,
        "items": [
            {
                "document_id": row.id,
                "filename": row.filename,
                "status": row.status,
                "content_type": row.content_type,
                "created_at": row.created_at,
                "processing_progress": row.processing_progress,
                "quarantined": row.quarantined,
            }
            for row in rows
        ],
    }


def _smart_collection_evaluation_response(
    evaluation: DocumentSmartCollectionEvaluation | None,
) -> dict | None:
    if evaluation is None:
        return None
    return {
        "id": evaluation.id,
        "collection_id": evaluation.collection_id,
        "collection_name": evaluation.collection_name,
        "actor_user_id": evaluation.actor_user_id,
        "status": evaluation.status,
        "scanned_count": evaluation.scanned_count,
        "matched_count": evaluation.matched_count,
        "duration_ms": evaluation.duration_ms,
        "error_message": evaluation.error_message,
        "created_at": evaluation.created_at,
        "started_at": evaluation.started_at,
        "completed_at": evaluation.completed_at,
    }


def _smart_collection_response(collection: DocumentSmartCollection, db: Session) -> dict:
    latest = db.scalar(
        select(DocumentSmartCollectionEvaluation)
        .where(
            DocumentSmartCollectionEvaluation.tenant_id == collection.tenant_id,
            DocumentSmartCollectionEvaluation.collection_id == collection.id,
        )
        .order_by(
            DocumentSmartCollectionEvaluation.created_at.desc(),
            DocumentSmartCollectionEvaluation.id.desc(),
        )
        .limit(1)
    )
    return {
        "id": collection.id,
        "name": collection.name,
        "match_mode": collection.match_mode,
        "conditions": collection.conditions,
        "enabled": collection.enabled,
        "match_count": latest.matched_count if latest and latest.status == "completed" else None,
        "match_count_stale": latest is None,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
        "last_evaluation": _smart_collection_evaluation_response(latest),
    }


def _get_smart_collection(
    collection_id: uuid.UUID, auth: AuthContext, db: Session
) -> DocumentSmartCollection:
    row = db.scalar(
        select(DocumentSmartCollection).where(
            DocumentSmartCollection.id == collection_id,
            DocumentSmartCollection.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise ApiError(
            code="SMART_COLLECTION_NOT_FOUND",
            message="Smart collection was not found.",
            status_code=404,
        )
    return row


def _smart_collection_documents_response(
    *,
    collection: DocumentSmartCollection,
    page_result,
    evaluation: DocumentSmartCollectionEvaluation | None,
) -> dict:
    return {
        "collection_id": collection.id,
        "name": collection.name,
        "enabled": collection.enabled,
        "page": page_result.page,
        "page_size": page_result.page_size,
        "total": page_result.total,
        "scanned_count": page_result.scanned_count,
        "duration_ms": page_result.duration_ms,
        "evaluated_at": page_result.evaluated_at,
        "evaluation": _smart_collection_evaluation_response(evaluation),
        "items": [
            {
                "document_id": document.id,
                "filename": document.filename,
                "status": document.status,
                "content_type": document.content_type,
                "quarantined": document.quarantined,
                "extraction_coverage_score": document.extraction_coverage_score,
            }
            for document in page_result.items
        ],
    }


@router.get(
    "/smart-collections",
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def list_smart_collections(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rows = db.scalars(
        select(DocumentSmartCollection)
        .where(DocumentSmartCollection.tenant_id == auth.tenant_id)
        .order_by(DocumentSmartCollection.name)
    ).all()
    return {"items": [_smart_collection_response(row, db) for row in rows]}


@router.post(
    "/smart-collections",
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def create_smart_collection(
    payload: SmartCollectionCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    try:
        conditions = normalize_conditions(
            db,
            tenant_id=auth.tenant_id,
            conditions=[condition.model_dump() for condition in payload.conditions],
        )
    except SmartCollectionValidationError as exc:
        raise ApiError(code="SMART_COLLECTION_INVALID", message=str(exc), status_code=422) from exc
    if not payload.name.strip():
        raise ApiError(
            code="SMART_COLLECTION_NAME_REQUIRED",
            message="Collection name cannot be blank.",
            status_code=422,
        )
    row = DocumentSmartCollection(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        created_by_user_id=auth.user_id,
        name=payload.name.strip(),
        match_mode=payload.match_mode,
        conditions=conditions,
    )
    db.add(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="SMART_COLLECTION_EXISTS",
            message="A smart collection with this name already exists.",
            status_code=409,
        ) from exc
    db.refresh(row)
    return _smart_collection_response(row, db)


@router.patch(
    "/smart-collections/{collection_id}",
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def update_smart_collection(
    collection_id: uuid.UUID,
    payload: SmartCollectionUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_smart_collection(collection_id, auth, db)
    if payload.name is not None:
        if not payload.name.strip():
            raise ApiError(
                code="SMART_COLLECTION_NAME_REQUIRED",
                message="Collection name cannot be blank.",
                status_code=422,
            )
        row.name = payload.name.strip()
    if payload.match_mode is not None:
        row.match_mode = payload.match_mode
    if payload.conditions is not None:
        try:
            row.conditions = normalize_conditions(
                db,
                tenant_id=auth.tenant_id,
                conditions=[condition.model_dump() for condition in payload.conditions],
            )
        except SmartCollectionValidationError as exc:
            raise ApiError(
                code="SMART_COLLECTION_INVALID", message=str(exc), status_code=422
            ) from exc
    if payload.enabled is not None:
        row.enabled = payload.enabled
    row.updated_at = datetime.now(UTC)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="SMART_COLLECTION_EXISTS",
            message="A smart collection with this name already exists.",
            status_code=409,
        ) from exc
    db.refresh(row)
    return _smart_collection_response(row, db)


@router.delete(
    "/smart-collections/{collection_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def delete_smart_collection(
    collection_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_smart_collection(collection_id, auth, db)
    db.delete(row)
    db.commit()


@router.get(
    "/smart-collections/{collection_id}/documents",
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def get_smart_collection_documents(
    collection_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_smart_collection(collection_id, auth, db)
    try:
        result = evaluate_smart_collection_page(
            db,
            collection=row,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            page=page,
            page_size=page_size,
        )
    except SmartCollectionValidationError as exc:
        raise ApiError(code="SMART_COLLECTION_INVALID", message=str(exc), status_code=422) from exc
    return _smart_collection_documents_response(collection=row, page_result=result, evaluation=None)


@router.post(
    "/smart-collections/{collection_id}/evaluate",
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def run_smart_collection_evaluation(
    collection_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_smart_collection(collection_id, auth, db)
    evaluation = new_evaluation(
        collection=row, tenant_id=auth.tenant_id, actor_user_id=auth.user_id
    )
    db.add(evaluation)
    db.commit()
    try:
        result = evaluate_smart_collection_page(
            db,
            collection=row,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            page=page,
            page_size=page_size,
            evaluation=evaluation,
        )
    except SmartCollectionValidationError as exc:
        raise ApiError(code="SMART_COLLECTION_INVALID", message=str(exc), status_code=422) from exc
    return _smart_collection_documents_response(
        collection=row, page_result=result, evaluation=evaluation
    )


@router.get(
    "/smart-collections/{collection_id}/evaluations",
    dependencies=[Depends(require_permissions("documents:organization:admin"))],
)
def list_smart_collection_evaluations(
    collection_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_smart_collection(collection_id, auth, db)
    evaluations = db.scalars(
        select(DocumentSmartCollectionEvaluation)
        .where(
            DocumentSmartCollectionEvaluation.tenant_id == auth.tenant_id,
            DocumentSmartCollectionEvaluation.collection_id == row.id,
        )
        .order_by(
            DocumentSmartCollectionEvaluation.created_at.desc(),
            DocumentSmartCollectionEvaluation.id.desc(),
        )
        .limit(limit)
    ).all()
    return {"items": [_smart_collection_evaluation_response(item) for item in evaluations]}


@router.get(
    "/classification-rules",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def list_classification_rules(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rows = db.scalars(
        select(DocumentClassificationRule)
        .where(DocumentClassificationRule.tenant_id == auth.tenant_id)
        .order_by(DocumentClassificationRule.priority, DocumentClassificationRule.name)
    ).all()
    return {"items": [_classification_rule_response(row, db) for row in rows]}


@router.post(
    "/classification-rules",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def create_classification_rule(
    payload: ClassificationRuleCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    if not payload.name.strip() or not payload.filename_pattern.strip():
        raise ApiError(
            code="CLASSIFICATION_RULE_FIELDS_REQUIRED",
            message="Rule name and filename pattern cannot be blank.",
            status_code=422,
        )
    if payload.tag_id is None and payload.folder_id is None:
        raise ApiError(
            code="CLASSIFICATION_RULE_ACTION_REQUIRED",
            message="Choose a tag or folder action before creating a classification rule.",
            status_code=422,
        )
    _validate_classification_targets(
        tenant_id=auth.tenant_id, tag_id=payload.tag_id, folder_id=payload.folder_id, db=db
    )
    row = DocumentClassificationRule(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        created_by_user_id=auth.user_id,
        name=payload.name.strip(),
        filename_pattern=payload.filename_pattern,
        content_type=payload.content_type,
        tag_id=payload.tag_id,
        folder_id=payload.folder_id,
        priority=payload.priority,
        enabled=payload.enabled,
    )
    db.add(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="CLASSIFICATION_RULE_EXISTS",
            message="A rule with this name already exists.",
            status_code=409,
        ) from exc
    return _classification_rule_response(row, db)


def _get_classification_rule(
    rule_id: uuid.UUID, auth: AuthContext, db: Session
) -> DocumentClassificationRule:
    rule = db.scalar(
        select(DocumentClassificationRule).where(
            DocumentClassificationRule.id == rule_id,
            DocumentClassificationRule.tenant_id == auth.tenant_id,
        )
    )
    if rule is None:
        raise ApiError(
            code="CLASSIFICATION_RULE_NOT_FOUND",
            message="Classification rule was not found.",
            status_code=404,
        )
    return rule


@router.post(
    "/classification-rules/{rule_id}/preview",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def preview_classification_rule(
    rule_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=100),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rule = _get_classification_rule(rule_id, auth, db)
    matched_count, rows = ClassificationService(db).preview_rule(rule=rule, limit=limit)
    return {
        "rule": _classification_rule_response(rule, db),
        "matched_count": matched_count,
        "items": [
            {
                "document_id": row.id,
                "filename": row.filename,
                "content_type": row.content_type,
                "status": row.status,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.post(
    "/classification-rules/{rule_id}/run",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def run_classification_rule(
    rule_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rule = _get_classification_rule(rule_id, auth, db)
    if not rule.enabled:
        raise ApiError(
            code="CLASSIFICATION_RULE_DISABLED",
            message="Enable the rule before running it.",
            status_code=409,
        )
    run = DocumentClassificationRun(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        rule_id=rule.id,
        actor_user_id=auth.user_id,
        source="manual",
        status="queued",
    )
    db.add(run)
    db.commit()
    try:
        from app.documents.workers.tasks_classification import run_classification_rule_task

        run_classification_rule_task.delay(str(run.id), str(auth.tenant_id))
    except Exception as exc:
        run.status = "failed"
        run.error_message = f"Unable to queue classification run: {exc}"[:2000]
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise ApiError(
            code="CLASSIFICATION_RUN_QUEUE_FAILED",
            message="The classification run could not be queued.",
            status_code=503,
        ) from exc
    return _classification_run_response(run)


@router.get(
    "/classification-rules/runs/{run_id}",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def get_classification_run(
    run_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    run = db.scalar(
        select(DocumentClassificationRun).where(
            DocumentClassificationRun.id == run_id,
            DocumentClassificationRun.tenant_id == auth.tenant_id,
        )
    )
    if run is None:
        raise ApiError(
            code="CLASSIFICATION_RUN_NOT_FOUND",
            message="Classification run was not found.",
            status_code=404,
        )
    return _classification_run_response(run)


@router.get(
    "/classification-rules/{rule_id}/runs",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def list_classification_runs(
    rule_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    _get_classification_rule(rule_id, auth, db)
    rows = db.scalars(
        select(DocumentClassificationRun)
        .where(
            DocumentClassificationRun.rule_id == rule_id,
            DocumentClassificationRun.tenant_id == auth.tenant_id,
        )
        .order_by(DocumentClassificationRun.created_at.desc(), DocumentClassificationRun.id.desc())
        .limit(limit)
    ).all()
    return {"items": [_classification_run_response(row) for row in rows]}


@router.get(
    "/classification-rules/documents/{document_id}/history",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def classification_history_for_document(
    document_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    document = DocumentsRepository(db).get_accessible_by_id(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        document_id=document_id,
        include_quarantined=True,
    )
    if document is None:
        raise ApiError(
            code="DOCUMENT_NOT_FOUND", message="Document was not found.", status_code=404
        )
    rows = db.execute(
        select(DocumentClassificationApplication, DocumentClassificationRule.name)
        .outerjoin(
            DocumentClassificationRule,
            DocumentClassificationRule.id == DocumentClassificationApplication.rule_id,
        )
        .where(
            DocumentClassificationApplication.tenant_id == auth.tenant_id,
            DocumentClassificationApplication.document_id == document_id,
        )
        .order_by(DocumentClassificationApplication.created_at.desc())
        .limit(100)
    ).all()
    return {
        "document_id": document_id,
        "items": [
            {
                "id": application.id,
                "rule_id": application.rule_id,
                "rule_name": rule_name or application.rule_name,
                "run_id": application.run_id,
                "source": application.source,
                "status": application.status,
                "actions": application.actions,
                "error_message": application.error_message,
                "created_at": application.created_at,
            }
            for application, rule_name in rows
        ],
    }


@router.patch(
    "/classification-rules/{rule_id}",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def update_classification_rule(
    rule_id: uuid.UUID,
    payload: ClassificationRuleUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = db.scalar(
        select(DocumentClassificationRule).where(
            DocumentClassificationRule.id == rule_id,
            DocumentClassificationRule.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise ApiError(
            code="CLASSIFICATION_RULE_NOT_FOUND",
            message="Classification rule was not found.",
            status_code=404,
        )
    if payload.name is not None:
        if not payload.name.strip():
            raise ApiError(
                code="CLASSIFICATION_RULE_FIELDS_REQUIRED",
                message="Rule name cannot be blank.",
                status_code=422,
            )
        row.name = payload.name.strip()
    if payload.filename_pattern is not None:
        if not payload.filename_pattern.strip():
            raise ApiError(
                code="CLASSIFICATION_RULE_FIELDS_REQUIRED",
                message="Filename pattern cannot be blank.",
                status_code=422,
            )
        row.filename_pattern = payload.filename_pattern.strip()
    if payload.content_type is not None:
        row.content_type = payload.content_type.strip() or None
    next_tag_id = payload.tag_id if "tag_id" in payload.model_fields_set else row.tag_id
    next_folder_id = payload.folder_id if "folder_id" in payload.model_fields_set else row.folder_id
    _validate_classification_targets(
        tenant_id=auth.tenant_id, tag_id=next_tag_id, folder_id=next_folder_id, db=db
    )
    if next_tag_id is None and next_folder_id is None:
        raise ApiError(
            code="CLASSIFICATION_RULE_ACTION_REQUIRED",
            message="Choose a tag or folder action before saving a classification rule.",
            status_code=422,
        )
    if "tag_id" in payload.model_fields_set:
        row.tag_id = payload.tag_id
    if "folder_id" in payload.model_fields_set:
        row.folder_id = payload.folder_id
    if payload.priority is not None:
        row.priority = payload.priority
    if payload.enabled is not None:
        row.enabled = payload.enabled
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="CLASSIFICATION_RULE_EXISTS",
            message="A rule with this name already exists.",
            status_code=409,
        ) from exc
    return _classification_rule_response(row, db)


@router.delete(
    "/classification-rules/{rule_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def delete_classification_rule(
    rule_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = db.scalar(
        select(DocumentClassificationRule).where(
            DocumentClassificationRule.id == rule_id,
            DocumentClassificationRule.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise ApiError(
            code="CLASSIFICATION_RULE_NOT_FOUND",
            message="Classification rule was not found.",
            status_code=404,
        )
    db.delete(row)
    db.commit()


def _automation_schedule_run_response(run: DocumentAutomationScheduleRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "schedule_id": run.schedule_id,
        "schedule_name": run.schedule_name,
        "actor_user_id": run.actor_user_id,
        "source": run.source,
        "status": run.status,
        "scanned_count": run.scanned_count,
        "matched_count": run.matched_count,
        "applied_count": run.applied_count,
        "failed_count": run.failed_count,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def _get_automation_schedule(
    schedule_id: uuid.UUID, auth: AuthContext, db: Session
) -> DocumentAutomationSchedule:
    row = db.scalar(
        select(DocumentAutomationSchedule).where(
            DocumentAutomationSchedule.id == schedule_id,
            DocumentAutomationSchedule.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise ApiError(
            code="AUTOMATION_SCHEDULE_NOT_FOUND",
            message="Automation schedule was not found.",
            status_code=404,
        )
    return row


def _validate_schedule_rules(
    *, tenant_id: uuid.UUID, rule_ids: list[uuid.UUID] | None, db: Session
) -> list[uuid.UUID]:
    unique_ids = list(dict.fromkeys(rule_ids or []))
    if not unique_ids:
        return []
    found = db.scalars(
        select(DocumentClassificationRule.id).where(
            DocumentClassificationRule.tenant_id == tenant_id,
            DocumentClassificationRule.id.in_(unique_ids),
        )
    ).all()
    if len(found) != len(unique_ids):
        raise ApiError(
            code="AUTOMATION_SCHEDULE_RULE_NOT_FOUND",
            message="Every selected rule must belong to this organization.",
            status_code=404,
        )
    return unique_ids


def _replace_schedule_rules(
    *, schedule: DocumentAutomationSchedule, rule_ids: list[uuid.UUID], db: Session
) -> None:
    db.query(DocumentAutomationScheduleRule).filter(
        DocumentAutomationScheduleRule.schedule_id == schedule.id,
        DocumentAutomationScheduleRule.tenant_id == schedule.tenant_id,
    ).delete(synchronize_session=False)
    for rule_id in rule_ids:
        db.add(
            DocumentAutomationScheduleRule(
                id=generate_uuid7_with_fallback(),
                tenant_id=schedule.tenant_id,
                schedule_id=schedule.id,
                rule_id=rule_id,
            )
        )


def _automation_schedule_response(schedule: DocumentAutomationSchedule, db: Session) -> dict:
    rule_rows = db.execute(
        select(DocumentAutomationScheduleRule.rule_id, DocumentClassificationRule.name)
        .outerjoin(
            DocumentClassificationRule,
            (DocumentClassificationRule.id == DocumentAutomationScheduleRule.rule_id)
            & (DocumentClassificationRule.tenant_id == schedule.tenant_id),
        )
        .where(
            DocumentAutomationScheduleRule.schedule_id == schedule.id,
            DocumentAutomationScheduleRule.tenant_id == schedule.tenant_id,
        )
        .order_by(DocumentClassificationRule.priority, DocumentClassificationRule.name)
    ).all()
    latest_run = db.scalar(
        select(DocumentAutomationScheduleRun)
        .where(
            DocumentAutomationScheduleRun.tenant_id == schedule.tenant_id,
            DocumentAutomationScheduleRun.schedule_id == schedule.id,
        )
        .order_by(
            DocumentAutomationScheduleRun.created_at.desc(), DocumentAutomationScheduleRun.id.desc()
        )
        .limit(1)
    )
    return {
        "id": schedule.id,
        "name": schedule.name,
        "interval_seconds": schedule.interval_seconds,
        "cadence": schedule.cadence,
        "timezone": schedule.timezone,
        "run_time": schedule.run_time,
        "weekday": schedule.weekday,
        "enabled": schedule.enabled,
        "rule_ids": [rule_id for rule_id, _ in rule_rows],
        "rule_names": [name for _, name in rule_rows if name],
        "runs_all_enabled_rules": not rule_rows,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at,
        "last_run": _automation_schedule_run_response(latest_run),
    }


@router.get(
    "/automation-schedules",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def list_automation_schedules(
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    rows = db.scalars(
        select(DocumentAutomationSchedule)
        .where(DocumentAutomationSchedule.tenant_id == auth.tenant_id)
        .order_by(DocumentAutomationSchedule.name)
    ).all()
    return {"items": [_automation_schedule_response(row, db) for row in rows]}


@router.post(
    "/automation-schedules",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def create_automation_schedule(
    payload: AutomationScheduleCreate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    if not payload.name.strip():
        raise ApiError(
            code="AUTOMATION_SCHEDULE_NAME_REQUIRED",
            message="Schedule name cannot be blank.",
            status_code=422,
        )
    try:
        validate_schedule_settings(
            cadence=payload.cadence,
            timezone_name=payload.timezone,
            run_time=payload.run_time,
            weekday=payload.weekday,
        )
    except ValueError as exc:
        raise ApiError(
            code="AUTOMATION_SCHEDULE_INVALID", message=str(exc), status_code=422
        ) from exc
    rule_ids = _validate_schedule_rules(tenant_id=auth.tenant_id, rule_ids=payload.rule_ids, db=db)
    row = DocumentAutomationSchedule(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        created_by_user_id=auth.user_id,
        name=payload.name.strip(),
        interval_seconds=payload.interval_seconds,
        cadence=payload.cadence,
        timezone=payload.timezone,
        run_time=payload.run_time,
        weekday=payload.weekday,
        enabled=payload.enabled,
    )
    row.next_run_at = next_schedule_run(row) if row.enabled else None
    db.add(row)
    _replace_schedule_rules(schedule=row, rule_ids=rule_ids, db=db)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="AUTOMATION_SCHEDULE_EXISTS",
            message="A schedule with this name already exists.",
            status_code=409,
        ) from exc
    return _automation_schedule_response(row, db)


@router.post(
    "/automation-schedules/{schedule_id}/run",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def run_automation_schedule(
    schedule_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    schedule = _get_automation_schedule(schedule_id, auth, db)
    run = DocumentAutomationScheduleRun(
        id=generate_uuid7_with_fallback(),
        tenant_id=auth.tenant_id,
        schedule_id=schedule.id,
        schedule_name=schedule.name,
        actor_user_id=auth.user_id,
        source="manual",
        status="queued",
    )
    db.add(run)
    db.commit()
    try:
        from app.documents.workers.tasks_classification import run_automation_schedule_task

        run_automation_schedule_task.delay(str(run.id), str(auth.tenant_id))
    except Exception as exc:
        run.status = "failed"
        run.error_message = f"Unable to queue schedule run: {exc}"[:2000]
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise ApiError(
            code="AUTOMATION_SCHEDULE_QUEUE_FAILED",
            message="The schedule run could not be queued.",
            status_code=503,
        ) from exc
    return _automation_schedule_run_response(run)


@router.get(
    "/automation-schedules/runs/{run_id}",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def get_automation_schedule_run(
    run_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    run = db.scalar(
        select(DocumentAutomationScheduleRun).where(
            DocumentAutomationScheduleRun.id == run_id,
            DocumentAutomationScheduleRun.tenant_id == auth.tenant_id,
        )
    )
    if run is None:
        raise ApiError(
            code="AUTOMATION_SCHEDULE_RUN_NOT_FOUND",
            message="Schedule run was not found.",
            status_code=404,
        )
    return _automation_schedule_run_response(run)


@router.get(
    "/automation-schedules/{schedule_id}/runs",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def list_automation_schedule_runs(
    schedule_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    _get_automation_schedule(schedule_id, auth, db)
    rows = db.scalars(
        select(DocumentAutomationScheduleRun)
        .where(
            DocumentAutomationScheduleRun.schedule_id == schedule_id,
            DocumentAutomationScheduleRun.tenant_id == auth.tenant_id,
        )
        .order_by(
            DocumentAutomationScheduleRun.created_at.desc(), DocumentAutomationScheduleRun.id.desc()
        )
        .limit(limit)
    ).all()
    return {"items": [_automation_schedule_run_response(row) for row in rows]}


@router.patch(
    "/automation-schedules/{schedule_id}",
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def update_automation_schedule(
    schedule_id: uuid.UUID,
    payload: AutomationScheduleUpdate,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_automation_schedule(schedule_id, auth, db)
    if payload.name is not None:
        if not payload.name.strip():
            raise ApiError(
                code="AUTOMATION_SCHEDULE_NAME_REQUIRED",
                message="Schedule name cannot be blank.",
                status_code=422,
            )
        row.name = payload.name.strip()
    if payload.interval_seconds is not None:
        row.interval_seconds = payload.interval_seconds
    if payload.cadence is not None:
        row.cadence = payload.cadence
    if payload.timezone is not None:
        row.timezone = payload.timezone
    if "run_time" in payload.model_fields_set:
        row.run_time = payload.run_time
    if "weekday" in payload.model_fields_set:
        row.weekday = payload.weekday
    if payload.enabled is not None:
        row.enabled = payload.enabled
    try:
        validate_schedule_settings(
            cadence=row.cadence,
            timezone_name=row.timezone,
            run_time=row.run_time,
            weekday=row.weekday,
        )
    except ValueError as exc:
        raise ApiError(
            code="AUTOMATION_SCHEDULE_INVALID", message=str(exc), status_code=422
        ) from exc
    if payload.rule_ids is not None:
        _replace_schedule_rules(
            schedule=row,
            rule_ids=_validate_schedule_rules(
                tenant_id=auth.tenant_id, rule_ids=payload.rule_ids, db=db
            ),
            db=db,
        )
    if any(
        field in payload.model_fields_set
        for field in ("interval_seconds", "cadence", "timezone", "run_time", "weekday", "enabled")
    ):
        row.next_run_at = next_schedule_run(row) if row.enabled else None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ApiError(
            code="AUTOMATION_SCHEDULE_EXISTS",
            message="A schedule with this name already exists.",
            status_code=409,
        ) from exc
    return _automation_schedule_response(row, db)


@router.delete(
    "/automation-schedules/{schedule_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("documents:organization:advanced"))],
)
def delete_automation_schedule(
    schedule_id: uuid.UUID,
    request_tenant_id: uuid.UUID = Depends(require_request_tenant_id),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    _scope(request_tenant_id, auth, db)
    row = _get_automation_schedule(schedule_id, auth, db)
    db.delete(row)
    db.commit()
