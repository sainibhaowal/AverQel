from __future__ import annotations

import io
import zipfile

import pytest

from app.core.errors import ApiError
from app.deepspace.services.library_storage import (
    decode_library_payload,
    read_archive_entry,
    safe_archive_entries,
)


def test_data_url_is_decoded_without_storing_binary_text() -> None:
    result = decode_library_payload("data:application/pdf;base64,SGVsbG8=", "application/pdf")

    assert result.payload == b"Hello"
    assert result.content_type == "application/pdf"
    assert result.is_binary is True


def test_zip_listing_and_entry_read_are_bounded_and_safe() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("docs/readme.txt", "hello")

    payload = buffer.getvalue()
    entries = safe_archive_entries(payload)

    assert entries[0]["name"] == "docs/readme.txt"
    assert read_archive_entry(payload, "docs/readme.txt") == b"hello"


def test_zip_path_traversal_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../secret.txt", "no")

    with pytest.raises(ApiError, match="unsafe path"):
        safe_archive_entries(buffer.getvalue())
