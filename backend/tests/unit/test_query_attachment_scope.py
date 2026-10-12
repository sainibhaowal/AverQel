from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.query.api.queries import _validate_query_payload
from app.query.schemas.queries import QueryFilters
from app.query.services.query_service import QueryService


class _AccessibleDocuments:
    def __init__(
        self, accessible_ids: set[UUID], documents: dict[UUID, object] | None = None
    ) -> None:
        self.accessible_ids = accessible_ids
        self.documents = documents or {}
        self.last_scope: dict[str, object] | None = None

    def get_accessible_document_ids(self, **scope: object) -> set[UUID]:
        self.last_scope = scope
        return self.accessible_ids

    def list_by_ids(self, *, document_ids: list[UUID], **_scope: object) -> list[object]:
        return [
            SimpleNamespace(id=document_id, **vars(self.documents[document_id]))
            for document_id in document_ids
            if document_id in self.documents
        ]


def _service(accessible_ids: set[UUID]) -> QueryService:
    service = object.__new__(QueryService)
    service.documents = _AccessibleDocuments(accessible_ids)  # type: ignore[attr-defined]
    return service


def test_attached_documents_are_union_of_resolved_scope_and_deduplicated() -> None:
    tenant_id, user_id = uuid4(), uuid4()
    in_scope, attached, duplicate = uuid4(), uuid4(), uuid4()
    documents = _AccessibleDocuments(
        {attached, duplicate},
        {
            attached: SimpleNamespace(status="indexed", quarantined=False),
            duplicate: SimpleNamespace(status="indexed", quarantined=False),
        },
    )
    service = _service({attached, duplicate})
    service.documents = documents  # type: ignore[attr-defined]

    resolved = service._include_attached_documents(
        auth=SimpleNamespace(tenant_id=tenant_id, user_id=user_id),  # type: ignore[arg-type]
        document_ids=[in_scope, duplicate],
        attached_document_ids=[attached, duplicate, attached],
    )

    assert resolved == [in_scope, duplicate, attached]
    assert documents.last_scope == {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "include_quarantined": False,
    }


def test_attached_documents_preserve_unrestricted_query_scope() -> None:
    attached = uuid4()
    service = _service({attached})
    service.documents.documents[attached] = SimpleNamespace(status="indexed", quarantined=False)  # type: ignore[attr-defined]

    resolved = service._include_attached_documents(
        auth=SimpleNamespace(tenant_id=uuid4(), user_id=uuid4()),  # type: ignore[arg-type]
        document_ids=None,
        attached_document_ids=[attached],
    )

    assert resolved is None


def test_inaccessible_or_quarantined_attachment_is_rejected_without_disclosing_ids() -> None:
    inaccessible = uuid4()
    service = _service(set())

    with pytest.raises(ApiError) as error:
        service._include_attached_documents(
            auth=SimpleNamespace(tenant_id=uuid4(), user_id=uuid4()),  # type: ignore[arg-type]
            document_ids=[uuid4()],
            attached_document_ids=[inaccessible],
        )

    assert error.value.status_code == 404
    assert error.value.code == "DOCUMENT_NOT_FOUND"
    assert str(inaccessible) not in error.value.message


@pytest.mark.parametrize(
    ("status", "quarantined", "expected_status"),
    [("queued", False, 409), ("indexed", True, 404)],
)
def test_attachment_must_be_indexed_and_not_quarantined(
    status: str,
    quarantined: bool,
    expected_status: int,
) -> None:
    document_id = uuid4()
    service = _service({document_id})
    service.documents.documents[document_id] = SimpleNamespace(  # type: ignore[attr-defined]
        status=status,
        quarantined=quarantined,
    )

    with pytest.raises(ApiError) as error:
        service._include_attached_documents(
            auth=SimpleNamespace(tenant_id=uuid4(), user_id=uuid4()),  # type: ignore[arg-type]
            document_ids=None,
            attached_document_ids=[document_id],
        )

    assert error.value.status_code == expected_status
    if expected_status == 409:
        assert error.value.code == "DOCUMENT_NOT_INDEXED"


def test_attached_document_filter_is_bounded_to_ten_ids() -> None:
    with pytest.raises(ValidationError):
        QueryFilters(attached_document_ids=[uuid4() for _ in range(11)])

    filters = QueryFilters(attached_document_ids=[UUID(int=1)])
    assert filters.attached_document_ids == [UUID(int=1)]


def test_query_payload_accepts_the_additive_attachment_filter() -> None:
    document_id = uuid4()

    payload = _validate_query_payload(
        {
            "query": "Summarize the attached file",
            "top_k": 5,
            "filters": {"attached_document_ids": [str(document_id)]},
        }
    )

    assert payload.filters.attached_document_ids == [document_id]
