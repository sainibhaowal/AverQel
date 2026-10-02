from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.document import Document
from app.documents.models.organization import (
    DocumentFolder,
    DocumentFolderAssignment,
    DocumentSmartCollection,
    DocumentSmartCollectionEvaluation,
    DocumentTag,
    DocumentTagAssignment,
)
from app.documents.repositories.documents import DocumentsRepository

FIELDS = {
    "status",
    "quarantined",
    "ocr_confidence",
    "content_type",
    "filename",
    "tag",
    "folder",
}
STRING_OPERATORS = {"equals", "not_equals", "contains", "starts_with"}
NUMERIC_OPERATORS = {"equals", "not_equals", "greater_than", "less_than"}
BOOLEAN_OPERATORS = {"equals", "not_equals"}
RELATION_OPERATORS = {"equals", "not_equals"}
MAX_CONDITION_VALUE_LENGTH = 512


class SmartCollectionValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SmartCollectionPage:
    items: list[Document]
    total: int
    scanned_count: int
    page: int
    page_size: int
    duration_ms: int
    evaluated_at: datetime


def _string_value(value: Any, *, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise SmartCollectionValidationError(f"{field} conditions require a text value.")
    normalized: str = str(value).strip()
    if not normalized:
        raise SmartCollectionValidationError(f"{field} conditions require a non-empty value.")
    if len(normalized) > MAX_CONDITION_VALUE_LENGTH:
        raise SmartCollectionValidationError("Condition values are too long.")
    return normalized


def _numeric_value(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise SmartCollectionValidationError(f"{field} conditions require a number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise SmartCollectionValidationError(f"{field} conditions require a number.") from exc
    if not math.isfinite(parsed):
        raise SmartCollectionValidationError(f"{field} conditions require a finite number.")
    if field == "ocr_confidence" and not 0 <= parsed <= 1:
        raise SmartCollectionValidationError("OCR confidence must be between 0 and 1.")
    return parsed


def _boolean_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise SmartCollectionValidationError("Quarantine conditions require true or false.")


def normalize_conditions(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not conditions or len(conditions) > 12:
        raise SmartCollectionValidationError("A collection must have between 1 and 12 conditions.")

    normalized: list[dict[str, Any]] = []
    relation_ids: dict[str, set[uuid.UUID]] = {"tag": set(), "folder": set()}
    for condition in conditions:
        field = str(condition.get("field", ""))
        operator = str(condition.get("operator", ""))
        if field not in FIELDS:
            raise SmartCollectionValidationError("This condition field is not supported.")
        if field == "quarantined":
            if operator not in BOOLEAN_OPERATORS:
                raise SmartCollectionValidationError(
                    "Quarantine only supports equals or not_equals."
                )
            value: Any = _boolean_value(condition.get("value"))
        elif field == "ocr_confidence":
            if operator not in NUMERIC_OPERATORS:
                raise SmartCollectionValidationError(
                    "OCR confidence only supports numeric comparisons."
                )
            value = _numeric_value(condition.get("value"), field=field)
        elif field in {"tag", "folder"}:
            if operator not in RELATION_OPERATORS:
                raise SmartCollectionValidationError(
                    "Tag and folder only support equals or not_equals."
                )
            try:
                value = uuid.UUID(str(condition.get("value")))
            except (ValueError, TypeError, AttributeError) as exc:
                raise SmartCollectionValidationError(
                    f"{field.title()} conditions require a valid ID."
                ) from exc
            relation_ids[field].add(value)
        else:
            if operator not in STRING_OPERATORS:
                raise SmartCollectionValidationError(f"{field} only supports text comparisons.")
            value = _string_value(condition.get("value"), field=field)
        normalized.append(
            {
                "field": field,
                "operator": operator,
                "value": str(value) if isinstance(value, uuid.UUID) else value,
            }
        )

    for field, ids in relation_ids.items():
        if not ids:
            continue
        model = DocumentTag if field == "tag" else DocumentFolder
        found = set(
            db.scalars(
                select(model.id).where(model.tenant_id == tenant_id, model.id.in_(ids))
            ).all()
        )
        if found != ids:
            raise SmartCollectionValidationError(
                f"Every {field} condition must reference an item in this organization."
            )
    return normalized


def _condition_matches(
    document: Document,
    condition: dict[str, Any],
    *,
    tag_ids: set[uuid.UUID],
    folder_ids: set[uuid.UUID],
) -> bool:
    field = condition["field"]
    operator = condition["operator"]
    value = condition["value"]
    if field == "tag":
        relation_matches = uuid.UUID(str(value)) in tag_ids
        return relation_matches if operator == "equals" else not relation_matches
    if field == "folder":
        relation_matches = uuid.UUID(str(value)) in folder_ids
        return relation_matches if operator == "equals" else not relation_matches
    actual: Any
    if field == "status":
        actual = document.status
    elif field == "quarantined":
        actual = document.quarantined
    elif field == "ocr_confidence":
        actual = document.extraction_coverage_score
        if actual is None:
            return False
    elif field == "content_type":
        actual = document.content_type
    else:
        actual = document.filename

    if operator == "equals":
        return bool(actual == value)
    if operator == "not_equals":
        return bool(actual != value)
    if operator == "contains":
        return bool(str(value).lower() in str(actual).lower())
    if operator == "starts_with":
        return bool(str(actual).lower().startswith(str(value).lower()))
    if operator == "greater_than":
        return bool(actual is not None and float(actual) > float(value))
    if operator == "less_than":
        return bool(actual is not None and float(actual) < float(value))
    return False


def _load_assignments(
    db: Session, *, tenant_id: uuid.UUID, document_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, set[uuid.UUID]], dict[uuid.UUID, set[uuid.UUID]]]:
    if not document_ids:
        return {}, {}
    tags: dict[uuid.UUID, set[uuid.UUID]] = {}
    folders: dict[uuid.UUID, set[uuid.UUID]] = {}
    for document_id, tag_id in db.execute(
        select(DocumentTagAssignment.document_id, DocumentTagAssignment.tag_id).where(
            DocumentTagAssignment.tenant_id == tenant_id,
            DocumentTagAssignment.document_id.in_(document_ids),
        )
    ):
        tags.setdefault(document_id, set()).add(tag_id)
    for document_id, folder_id in db.execute(
        select(DocumentFolderAssignment.document_id, DocumentFolderAssignment.folder_id).where(
            DocumentFolderAssignment.tenant_id == tenant_id,
            DocumentFolderAssignment.document_id.in_(document_ids),
        )
    ):
        folders.setdefault(document_id, set()).add(folder_id)
    return tags, folders


def evaluate_smart_collection(
    db: Session,
    *,
    collection: DocumentSmartCollection,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    evaluation: DocumentSmartCollectionEvaluation | None = None,
) -> SmartCollectionPage:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    started = time.perf_counter()
    evaluated_at = datetime.now(UTC)
    matched = 0
    scanned = 0
    items: list[Document] = []
    conditions: list[dict[str, Any]] = []
    mode = collection.match_mode
    repository = DocumentsRepository(db)

    try:
        conditions = normalize_conditions(
            db,
            tenant_id=tenant_id,
            conditions=list(collection.conditions or []),
        )
        if collection.enabled:
            offset = 0
            while True:
                batch = repository.list_accessible_for_user(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    skip=offset,
                    limit=250,
                    include_quarantined=True,
                )
                if not batch:
                    break
                document_ids = [document.id for document in batch]
                tags, folders = _load_assignments(
                    db, tenant_id=tenant_id, document_ids=document_ids
                )
                for document in batch:
                    scanned += 1
                    matches = [
                        _condition_matches(
                            document,
                            condition,
                            tag_ids=tags.get(document.id, set()),
                            folder_ids=folders.get(document.id, set()),
                        )
                        for condition in conditions
                    ]
                    matched_condition = all(matches) if mode == "all" else any(matches)
                    if matched_condition:
                        if matched >= (page - 1) * page_size and len(items) < page_size:
                            items.append(document)
                        matched += 1
                if len(batch) < 250:
                    break
                offset += len(batch)

        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = SmartCollectionPage(
            items=items,
            total=matched,
            scanned_count=scanned,
            page=page,
            page_size=page_size,
            duration_ms=duration_ms,
            evaluated_at=evaluated_at,
        )
        if evaluation is not None:
            evaluation.status = "completed"
            evaluation.scanned_count = scanned
            evaluation.matched_count = matched
            evaluation.duration_ms = duration_ms
            evaluation.completed_at = datetime.now(UTC)
            db.commit()
        return result
    except Exception as exc:
        if evaluation is not None:
            db.rollback()
            refreshed = db.get(DocumentSmartCollectionEvaluation, evaluation.id)
            if refreshed is not None:
                refreshed.status = "failed"
                refreshed.error_message = str(exc)[:2000]
                refreshed.duration_ms = max(0, int((time.perf_counter() - started) * 1000))
                refreshed.completed_at = datetime.now(UTC)
                db.commit()
        raise


def new_evaluation(
    *,
    collection: DocumentSmartCollection,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> DocumentSmartCollectionEvaluation:
    return DocumentSmartCollectionEvaluation(
        id=generate_uuid7_with_fallback(),
        tenant_id=tenant_id,
        collection_id=collection.id,
        collection_name=collection.name,
        actor_user_id=actor_user_id,
        status="running",
        started_at=datetime.now(UTC),
    )
