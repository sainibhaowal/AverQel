"""Safe text extraction for formats without a server-side visual renderer.

Apple iWork packages and several WPS legacy formats are intentionally kept as
downloadable originals.  This module provides a bounded, best-effort text
fallback for indexing when their package/binary payload contains readable
metadata or text.  It never executes or extracts an archive to disk.
"""

from __future__ import annotations

import html
import re
import zipfile
from io import BytesIO

from app.ingestion.services.parser_service import sanitize_document_text

_TEXT_ENTRY_EXTENSIONS = frozenset(
    {".xml", ".plist", ".json", ".txt", ".html", ".htm", ".csv", ".tsv", ".md"}
)
_MEDIA_ENTRY_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".pdf", ".mov", ".mp4"}
)
_PRINTABLE_RUN = re.compile(r"[\x20-\x7e]{4,}")
_XML_TAG = re.compile(r"<[^>]+>")
_MAX_ARCHIVE_ENTRIES = 256
_MAX_ENTRY_BYTES = 8 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def extract_fallback_text(*, filename: str, payload: bytes, max_chars: int) -> str:
    """Return bounded readable text without claiming visual fidelity."""

    if not payload or max_chars <= 0:
        return ""

    sections: list[str] = []
    if zipfile.is_zipfile(BytesIO(payload)):
        sections.extend(_extract_zip_sections(payload=payload, max_chars=max_chars))
    else:
        sections.extend(_printable_text(payload))

    cleaned: list[str] = []
    seen: set[str] = set()
    for section in sections:
        value = _clean_text(section)
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
        if sum(len(item) for item in cleaned) >= max_chars:
            break
    return "\n\n".join(cleaned)[:max_chars].strip()


def _extract_zip_sections(*, payload: bytes, max_chars: int) -> list[str]:
    sections: list[str] = []
    consumed = 0
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            for info in archive.infolist()[:_MAX_ARCHIVE_ENTRIES]:
                if info.is_dir() or info.file_size <= 0:
                    continue
                if consumed >= _MAX_ARCHIVE_BYTES:
                    break
                suffix = (
                    "." + info.filename.rsplit(".", 1)[-1].lower() if "." in info.filename else ""
                )
                if suffix in _MEDIA_ENTRY_EXTENSIONS:
                    continue
                read_size = min(info.file_size, _MAX_ENTRY_BYTES, _MAX_ARCHIVE_BYTES - consumed)
                if read_size <= 0:
                    continue
                with archive.open(info, "r") as entry:
                    content = entry.read(read_size)
                consumed += len(content)
                if suffix in _TEXT_ENTRY_EXTENSIONS:
                    decoded = _decode_text(content)
                    if decoded:
                        sections.append(f"[{info.filename}]\n{decoded[:max_chars]}")
                else:
                    sections.extend(_printable_text(content))
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
        return sections
    return sections


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            decoded = payload.decode(encoding)
        except UnicodeDecodeError:
            continue
        if (
            decoded
            and sum(character.isprintable() or character in "\n\r\t" for character in decoded)
            / len(decoded)
            >= 0.65
        ):
            return decoded
    return ""


def _printable_text(payload: bytes) -> list[str]:
    normalized = payload.replace(b"\x00", b"")
    return _PRINTABLE_RUN.findall(normalized.decode("latin-1", errors="ignore"))


def _clean_text(value: str) -> str:
    value = html.unescape(_XML_TAG.sub(" ", value))
    return sanitize_document_text(value).strip()
