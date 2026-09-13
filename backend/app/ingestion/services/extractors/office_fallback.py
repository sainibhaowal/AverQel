"""Bounded fallback extraction for Office Open XML and mislabeled text files."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from xml.etree import ElementTree

from app.ingestion.services.parser_service import sanitize_document_text

_MAX_ENTRY_BYTES = 25 * 1024 * 1024
_MAX_TOTAL_BYTES = 100 * 1024 * 1024
_TEXT_TAG = re.compile(r"(?:^|})t$")


def _readable_text(payload: bytes, max_text_chars: int) -> str | None:
    """Return text only when a non-archive payload is safely UTF-8 readable."""
    if not payload or b"\x00" in payload:
        return None
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    cleaned = sanitize_document_text(decoded).strip()
    if not cleaned:
        return None
    printable = sum(ch.isprintable() or ch in "\n\r\t" for ch in cleaned)
    if printable / len(cleaned) < 0.85:
        return None
    return cleaned[: max_text_chars + 1]


def extract_openxml_text(
    payload: bytes,
    *,
    prefixes: Iterable[str],
    max_text_chars: int,
) -> tuple[str | None, str | None]:
    """Extract visible ``w:t``/``a:t`` text without writing archive entries to disk.

    The second tuple value identifies whether the result came from XML or a
    readable plain-text fallback. ``None`` means the payload is not recoverable.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (OSError, zipfile.BadZipFile):
        text = _readable_text(payload, max_text_chars)
        return (text, "plain_text_fallback" if text else None)

    selected = tuple(prefixes)
    total = 0
    blocks: list[str] = []
    try:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = info.filename.replace("\\", "/")
            if info.is_dir() or not name.endswith(".xml") or not name.startswith(selected):
                continue
            if info.file_size > _MAX_ENTRY_BYTES:
                continue
            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                break
            try:
                root = ElementTree.fromstring(archive.read(info))
            except (ElementTree.ParseError, RuntimeError, ValueError, zipfile.BadZipFile):
                continue
            values = [
                sanitize_document_text(node.text or "").strip()
                for node in root.iter()
                if _TEXT_TAG.search(node.tag) and (node.text or "").strip()
            ]
            if values:
                blocks.append(" ".join(values))
    finally:
        archive.close()

    text = "\n".join(blocks).strip()[: max_text_chars + 1]
    return (text or None, "xml_fallback" if text else None)
