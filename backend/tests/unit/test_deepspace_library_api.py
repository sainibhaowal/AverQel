from __future__ import annotations

import inspect
import io
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from app.core.errors import ApiError
from app.deepspace.api.library import (
    _EXTRACTABLE_LIBRARY_TYPES,
    _LIBRARY_RASTER_PREVIEW_EXTENSIONS,
    _LIBRARY_RASTER_PREVIEW_TYPES,
    _queue_missing_library_extraction,
    _render_library_visual_preview,
    get_workspace_file,
    list_workspace_entries,
    read_workspace_archive_entry,
    read_workspace_csv_page,
    render_workspace_file_preview,
    stream_workspace_file_content,
)
from app.ingestion.services.extractors.image_ocr_extractor import ImageOcrExtractor

pytestmark = pytest.mark.unit_no_db


def test_library_preview_handlers_keep_blocking_io_off_the_event_loop() -> None:
    preview_handlers = (
        get_workspace_file,
        list_workspace_entries,
        render_workspace_file_preview,
        stream_workspace_file_content,
        read_workspace_csv_page,
        read_workspace_archive_entry,
    )

    assert all(not inspect.iscoroutinefunction(handler) for handler in preview_handlers)


@pytest.mark.parametrize(
    ("filename", "content_type", "source_format", "preview_type"),
    [
        ("scan.bmp", "image/bmp", "BMP", "image/jpeg"),
        ("scan.png", "image/png", "PNG", "image/png"),
        ("scan.jpg", "image/jpeg", "JPEG", "image/jpeg"),
        ("scan.gif", "image/gif", "GIF", "image/jpeg"),
        ("scan.tif", "image/tiff", "TIFF", "image/jpeg"),
        ("scan.webp", "image/webp", "WEBP", "image/jpeg"),
    ],
)
def test_library_visual_preview_normalizes_supported_raster_formats(
    filename: str, content_type: str, source_format: str, preview_type: str
) -> None:
    source = io.BytesIO()
    Image.new("RGB", (8, 6), color=(30, 120, 210)).save(source, format=source_format)

    payload, rendered_type, rendered_name = _render_library_visual_preview(
        filename=filename,
        content_type=content_type,
        payload=source.getvalue(),
        settings=SimpleNamespace(),
    )

    assert rendered_type == preview_type
    assert rendered_name == filename
    with Image.open(io.BytesIO(payload)) as rendered:
        assert rendered.format == preview_type.split("/", 1)[1].upper().replace("JPEG", "JPEG")
        assert rendered.size == (8, 6)


def test_library_visual_preview_preserves_transparent_png() -> None:
    source = io.BytesIO()
    Image.new("RGBA", (2, 2), color=(30, 120, 210, 80)).save(source, format="PNG")

    payload, rendered_type, _ = _render_library_visual_preview(
        filename="transparent.png",
        content_type="image/png",
        payload=source.getvalue(),
        settings=SimpleNamespace(),
    )

    assert rendered_type == "image/png"
    with Image.open(io.BytesIO(payload)) as rendered:
        assert rendered.mode == "RGBA"


def test_library_image_ocr_and_visual_preview_formats_are_wired_together() -> None:
    expected_extensions = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp", ".gif"}
    expected_mime_types = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
        "image/webp",
        "image/bmp",
        "image/gif",
    }

    assert ImageOcrExtractor.supported_extensions == expected_extensions
    assert expected_mime_types <= _EXTRACTABLE_LIBRARY_TYPES
    assert expected_mime_types <= _LIBRARY_RASTER_PREVIEW_TYPES
    assert expected_extensions <= {
        f".{extension}" for extension in _LIBRARY_RASTER_PREVIEW_EXTENSIONS
    }


def test_library_visual_preview_rejects_invalid_raster_payload() -> None:
    with pytest.raises(ApiError, match="image could not be decoded"):
        _render_library_visual_preview(
            filename="broken.bmp",
            content_type="image/bmp",
            payload=b"not an image",
            settings=SimpleNamespace(),
        )


def test_library_visual_preview_uses_libreoffice_conversion_for_odt(monkeypatch) -> None:
    convert = Mock(return_value=b"%PDF-preview")
    monkeypatch.setattr("app.deepspace.api.library.ConversionService.convert_to_pdf", convert)

    payload, content_type, filename = _render_library_visual_preview(
        filename="notes.odt",
        content_type="application/vnd.oasis.opendocument.text",
        payload=b"odt-source",
        settings=SimpleNamespace(),
    )

    assert payload == b"%PDF-preview"
    assert content_type == "application/pdf"
    assert filename == "notes.pdf"
    convert.assert_called_once_with(filename="notes.odt", payload=b"odt-source")


def test_library_preview_route_returns_private_normalized_image(monkeypatch) -> None:
    source = io.BytesIO()
    Image.new("RGB", (4, 3), color=(40, 80, 120)).save(source, format="BMP")
    file_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    file = SimpleNamespace(
        id=file_id,
        conversation_id=conversation_id,
        name="scan.bmp",
        content_type="image/bmp",
        size_bytes=len(source.getvalue()),
        is_binary=True,
    )
    monkeypatch.setattr("app.deepspace.api.library._conversation", lambda **_: None)
    monkeypatch.setattr("app.deepspace.api.library._owned_file", lambda **_: file)
    monkeypatch.setattr(
        "app.deepspace.api.library._library_file_payload", lambda **_: source.getvalue()
    )

    response = render_workspace_file_preview(
        conversation_id=conversation_id,
        file_id=file_id,
        auth=SimpleNamespace(),
        db=Mock(),
        settings=SimpleNamespace(),
    )

    assert response.media_type == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(response.body)) as preview:
        assert preview.format == "JPEG"
        assert preview.size == (4, 3)


def test_library_preview_route_rejects_files_over_the_safe_limit_before_storage_read(
    monkeypatch,
) -> None:
    file_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    file = SimpleNamespace(
        id=file_id,
        conversation_id=conversation_id,
        name="large.pdf",
        content_type="application/pdf",
        size_bytes=100 * 1024 * 1024 + 1,
        is_binary=True,
    )
    read_payload = Mock(side_effect=AssertionError("oversized files must not be read"))
    monkeypatch.setattr("app.deepspace.api.library._conversation", lambda **_: None)
    monkeypatch.setattr("app.deepspace.api.library._owned_file", lambda **_: file)
    monkeypatch.setattr("app.deepspace.api.library._library_file_payload", read_payload)

    with pytest.raises(ApiError) as error:
        render_workspace_file_preview(
            conversation_id=conversation_id,
            file_id=file_id,
            auth=SimpleNamespace(),
            db=Mock(),
            settings=SimpleNamespace(),
        )

    assert error.value.status_code == 413
    read_payload.assert_not_called()


def test_opening_legacy_image_queues_extraction_instead_of_running_ocr(monkeypatch) -> None:
    file = SimpleNamespace(
        id=uuid.uuid4(),
        name="scan.png",
        content_type="image/png",
        is_binary=True,
        storage_bucket="private",
        storage_key="tenant/file",
        extracted_text=None,
    )
    enqueue = Mock()
    monkeypatch.setattr("app.deepspace.api.library._conversation", lambda **_: None)
    monkeypatch.setattr("app.deepspace.api.library._owned_file", lambda **_: file)
    monkeypatch.setattr("app.deepspace.api.library._queue_missing_library_extraction", enqueue)
    monkeypatch.setattr(
        "app.deepspace.api.library._serialize_file", lambda current, include_content: current
    )

    response = get_workspace_file(
        conversation_id=uuid.uuid4(),
        file_id=file.id,
        auth=SimpleNamespace(),
        db=Mock(),
        settings=SimpleNamespace(),
    )

    assert response is file
    enqueue.assert_called_once()


def test_legacy_library_extraction_is_queued_once(monkeypatch) -> None:
    file = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        is_binary=True,
        content_type="image/bmp",
        storage_bucket="private",
        storage_key="tenant/file",
        extracted_text=None,
        metadata_json={},
    )

    class Result:
        def scalar_one_or_none(self):
            return file

    db = Mock()
    db.execute.return_value = Result()
    auth = SimpleNamespace(tenant_id=file.tenant_id, user_id=file.user_id)
    enqueue = Mock()
    monkeypatch.setattr("app.deepspace.api.library.extract_library_file.delay", enqueue)

    _queue_missing_library_extraction(db=db, file=file, auth=auth)
    _queue_missing_library_extraction(db=db, file=file, auth=auth)

    assert file.metadata_json["extraction_status"]["state"] == "processing"
    assert db.commit.call_count == 1
    enqueue.assert_called_once_with(file_id=str(file.id), tenant_id=str(file.tenant_id))
