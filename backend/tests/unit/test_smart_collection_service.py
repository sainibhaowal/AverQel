from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.documents.models.document import Document
from app.documents.models.organization import DocumentSmartCollection
from app.documents.services import smart_collection_service
from app.documents.services.smart_collection_service import (
    SmartCollectionValidationError,
    _condition_matches,
    normalize_conditions,
)


def _document(**overrides: object) -> Document:
    values = {
        "filename": "Invoice-2026.pdf",
        "content_type": "application/pdf",
        "status": "indexed",
        "quarantined": False,
        "extraction_coverage_score": 0.85,
    }
    values.update(overrides)
    return Document(**values)


def test_normalize_conditions_rejects_invalid_numeric_values() -> None:
    with pytest.raises(SmartCollectionValidationError, match="require a number"):
        normalize_conditions(
            MagicMock(),
            tenant_id=uuid4(),
            conditions=[{"field": "ocr_confidence", "operator": "greater_than", "value": "high"}],
        )


def test_normalize_conditions_rejects_unsupported_operator_for_field() -> None:
    with pytest.raises(SmartCollectionValidationError, match="only supports text"):
        normalize_conditions(
            MagicMock(),
            tenant_id=uuid4(),
            conditions=[{"field": "filename", "operator": "greater_than", "value": "x"}],
        )


def test_condition_matching_handles_numeric_and_boolean_values_safely() -> None:
    document = _document()
    assert _condition_matches(
        document,
        {"field": "ocr_confidence", "operator": "greater_than", "value": 0.8},
        tag_ids=set(),
        folder_ids=set(),
    )
    assert _condition_matches(
        document,
        {"field": "quarantined", "operator": "equals", "value": False},
        tag_ids=set(),
        folder_ids=set(),
    )


def test_relation_conditions_match_only_the_requested_tenant_safe_id() -> None:
    tag_id = uuid4()
    assert _condition_matches(
        _document(),
        {"field": "tag", "operator": "equals", "value": str(tag_id)},
        tag_ids={tag_id},
        folder_ids=set(),
    )
    assert not _condition_matches(
        _document(),
        {"field": "folder", "operator": "equals", "value": str(uuid4())},
        tag_ids=set(),
        folder_ids=set(),
    )


def test_evaluation_scans_in_bounded_batches_and_returns_a_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = [
        _document(filename="indexed.pdf"),
        _document(filename="ignored.txt", status="queued"),
    ]

    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_accessible_for_user(self, **kwargs: object) -> list[Document]:
            return documents if kwargs["skip"] == 0 else []

    monkeypatch.setattr(smart_collection_service, "DocumentsRepository", FakeRepository)
    monkeypatch.setattr(
        smart_collection_service, "_load_assignments", lambda *args, **kwargs: ({}, {})
    )
    collection = DocumentSmartCollection(
        enabled=True,
        match_mode="all",
        conditions=[{"field": "status", "operator": "equals", "value": "indexed"}],
    )

    result = smart_collection_service.evaluate_smart_collection(
        MagicMock(), collection=collection, tenant_id=uuid4(), user_id=uuid4(), page=1, page_size=1
    )

    assert result.scanned_count == 2
    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].filename == "indexed.pdf"
