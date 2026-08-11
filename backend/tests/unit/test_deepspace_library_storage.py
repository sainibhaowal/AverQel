from __future__ import annotations

import io
import uuid
import zipfile
from types import SimpleNamespace

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


def test_invalid_data_url_is_rejected() -> None:
    with pytest.raises(ApiError, match="binary file payload is invalid"):
        decode_library_payload("data:application/pdf;base64,not-base64!", "application/pdf")


def test_plain_text_payload_is_utf8_and_not_binary() -> None:
    result = decode_library_payload("hello ✓", "text/plain")

    assert result.payload == "hello ✓".encode()
    assert result.content_type == "text/plain"
    assert result.is_binary is False


def test_archive_entry_requires_existing_name() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "hello")

    with pytest.raises(ApiError, match="Archive entry not found"):
        read_archive_entry(buffer.getvalue(), "missing.txt")


def test_archive_entry_directory_is_empty() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("docs/", "")

    assert read_archive_entry(buffer.getvalue(), "docs/") == b""


def test_corrupt_archive_is_reported() -> None:
    with pytest.raises(ApiError, match="ZIP archive is invalid"):
        safe_archive_entries(b"not a zip")


def test_storage_rejects_payload_over_configured_limit() -> None:
    from app.deepspace.services.library_storage import LibraryStorageService

    service = object.__new__(LibraryStorageService)
    service.settings = SimpleNamespace(upload_max_bytes=2)
    service.storage = SimpleNamespace()

    with pytest.raises(ApiError, match="configured upload limit"):
        service.store(
            tenant_id=uuid.uuid4(),
            file_id=uuid.uuid4(),
            filename="large.bin",
            content_type="application/octet-stream",
            payload=b"123",
        )
