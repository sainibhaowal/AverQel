from __future__ import annotations

import base64
import binascii
import hashlib
import io
import posixpath
import re
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.errors import ApiError
from app.ingestion.services.extractors.router import ExtractorRouter
from app.system.services.storage_service import StorageService

_DATA_URL = re.compile(r"^data:(?P<type>[^;,]+)(?:;[^,]*)?,(?P<data>.*)$", re.DOTALL)
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_ARCHIVE_ENTRY_BYTES = 25 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 250 * 1024 * 1024


@dataclass(slots=True)
class LibraryPayload:
    payload: bytes
    content_type: str
    is_binary: bool


def decode_library_payload(value: str, content_type: str) -> LibraryPayload:
    """Decode the old JSON data-url shape while keeping bytes out of PostgreSQL."""
    if not isinstance(value, str):
        raise ApiError(
            code="VALIDATION_ERROR",
            message="File content must be text or a data URL.",
            status_code=422,
        )
    match = _DATA_URL.fullmatch(value.strip())
    if match:
        declared_type = match.group("type").strip().lower() or content_type
        encoded = match.group("data")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ApiError(
                code="INVALID_UPLOAD_SIGNATURE",
                message="The binary file payload is invalid.",
                status_code=422,
            ) from exc
        return LibraryPayload(payload=payload, content_type=declared_type, is_binary=True)
    # Existing text/code files remain unchanged.
    return LibraryPayload(payload=value.encode("utf-8"), content_type=content_type, is_binary=False)


def safe_archive_entries(payload: bytes) -> list[dict[str, Any]]:
    """List ZIP entries without extracting or executing anything."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ARCHIVE_ENTRIES:
                raise ApiError(
                    code="ARCHIVE_BOMB_DETECTED",
                    message="Archive contains too many entries.",
                    status_code=422,
                )
            total = 0
            entries: list[dict[str, Any]] = []
            for info in infos:
                normalized = posixpath.normpath(info.filename.replace("\\", "/"))
                if (
                    normalized.startswith("../")
                    or normalized in {"..", "."}
                    or normalized.startswith("/")
                ):
                    raise ApiError(
                        code="ZIP_SLIP_DETECTED",
                        message="Archive contains an unsafe path.",
                        status_code=422,
                    )
                if info.file_size > _MAX_ARCHIVE_ENTRY_BYTES:
                    raise ApiError(
                        code="DOC_TOO_LARGE",
                        message="Archive entry exceeds the safe size limit.",
                        status_code=422,
                    )
                total += info.file_size
                if total > _MAX_ARCHIVE_TOTAL_BYTES:
                    raise ApiError(
                        code="ARCHIVE_BOMB_DETECTED",
                        message="Archive expands beyond the safe size limit.",
                        status_code=422,
                    )
                entries.append(
                    {
                        "name": info.filename,
                        "directory": info.is_dir(),
                        "size": info.file_size,
                        "compressed_size": info.compress_size,
                    }
                )
            return entries
    except zipfile.BadZipFile as exc:
        raise ApiError(
            code="CORRUPTED_ARCHIVE", message="The ZIP archive is invalid.", status_code=422
        ) from exc


def read_archive_entry(payload: bytes, entry_name: str) -> bytes:
    entries = safe_archive_entries(payload)
    if not any(entry["name"] == entry_name for entry in entries):
        raise ApiError(code="NOT_FOUND", message="Archive entry not found.", status_code=404)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            info = archive.getinfo(entry_name)
            if info.is_dir():
                return b""
            with archive.open(info) as stream:
                return stream.read(_MAX_ARCHIVE_ENTRY_BYTES + 1)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ApiError(
            code="CORRUPTED_ARCHIVE", message="The ZIP archive is invalid.", status_code=422
        ) from exc


class LibraryStorageService:
    """Binary Library storage plus bounded document extraction."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = StorageService(settings)
        self.extractor = ExtractorRouter(settings)

    def store(
        self,
        *,
        tenant_id: uuid.UUID,
        file_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ):
        if len(payload) > self.settings.upload_max_bytes:
            raise ApiError(
                code="DOC_TOO_LARGE",
                message="The file exceeds the configured upload limit.",
                status_code=413,
            )
        return self.storage.put_bytes(
            tenant_id=tenant_id,
            document_id=file_id,
            filename=filename,
            content_type=content_type,
            payload=payload,
        )

    def extract(
        self, *, filename: str, content_type: str, payload: bytes, tenant_id: uuid.UUID
    ) -> dict[str, Any]:
        try:
            result = self.extractor.extract(
                filename=filename, content_type=content_type, payload=payload, tenant_id=tenant_id
            )
            return {
                "text": result.text,
                "page_count": result.page_count,
                "extraction_method": result.extraction_method,
                "coverage_score": result.coverage_score,
                "warnings": result.warnings,
            }
        except ApiError as exc:
            # Binary storage must remain available even when optional extraction is unavailable.
            return {"text": None, "extraction_error": exc.code, "warnings": [exc.message]}

    @staticmethod
    def checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()
