from __future__ import annotations

import base64
import binascii
import re

SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_DATA_URL = re.compile(r"^data:(image/[a-z0-9.+-]+);base64,([A-Za-z0-9+/]+={0,2})$")
_BASE64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def parse_image_input(value: str) -> tuple[str, str]:
    """Return a supported image MIME type and its base64 payload.

    Legacy callers may still supply bare base64, which has historically meant
    JPEG. New attachment inputs use MIME-qualified data URLs.
    """
    value = value.strip()
    match = _DATA_URL.fullmatch(value)
    if match:
        mime_type, encoded = match.groups()
        mime_type = mime_type.casefold()
    else:
        mime_type, encoded = "image/jpeg", value
        if not _BASE64.fullmatch(encoded):
            raise ValueError("Image input must be base64 data or a supported image data URL.")
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES or not _BASE64.fullmatch(encoded):
        raise ValueError("Image input uses an unsupported format or invalid base64 data.")
    try:
        base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Image input uses an unsupported format or invalid base64 data.") from exc
    return mime_type, encoded


def image_data_url(value: str) -> str:
    mime_type, encoded = parse_image_input(value)
    return f"data:{mime_type};base64,{encoded}"
