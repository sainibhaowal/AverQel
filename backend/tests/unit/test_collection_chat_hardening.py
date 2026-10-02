from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ApiError
from app.documents.api.collections import _validate_media_reference


def test_media_reference_must_stay_under_collection_tenant_prefix() -> None:
    tenant_id = uuid4()
    media_id = uuid4()
    collection = SimpleNamespace(tenant_id=tenant_id)

    parsed_id, object_key = _validate_media_reference(
        collection=collection,
        media_id=str(media_id),
        media_object_key=f"{tenant_id}/{media_id}/encrypted.bin",
    )

    assert parsed_id == media_id
    assert object_key == f"{tenant_id}/{media_id}/encrypted.bin"


def test_media_reference_rejects_cross_tenant_object_key() -> None:
    collection = SimpleNamespace(tenant_id=uuid4())
    media_id = uuid4()

    with pytest.raises(ApiError) as error:
        _validate_media_reference(
            collection=collection,
            media_id=str(media_id),
            media_object_key=f"{uuid4()}/{media_id}/encrypted.bin",
        )

    assert error.value.code == "FORBIDDEN"


def test_media_reference_rejects_path_traversal() -> None:
    tenant_id = uuid4()
    media_id = uuid4()

    with pytest.raises(ApiError) as error:
        _validate_media_reference(
            collection=SimpleNamespace(tenant_id=tenant_id),
            media_id=str(media_id),
            media_object_key=f"{tenant_id}/{media_id}/../other.bin",
        )

    assert error.value.code == "FORBIDDEN"
