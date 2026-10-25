from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterable

ALGORITHM = "RSA-OAEP-3072+AES-256-GCM"
_KEY_ID = re.compile(r"^[a-f0-9]{64}$")


class EncryptedPayloadError(ValueError):
    pass


def _decode(value: object, *, minimum: int, maximum: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise EncryptedPayloadError("Encrypted payload fields must be base64 strings")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EncryptedPayloadError("Encrypted payload contains invalid base64") from exc
    if len(decoded) < minimum or (maximum is not None and len(decoded) > maximum):
        raise EncryptedPayloadError("Encrypted payload field has an invalid length")
    return decoded


def _recipients(value: object) -> set[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 2:
        raise EncryptedPayloadError("Encrypted payload must have one or two recipients")
    result: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise EncryptedPayloadError("Encrypted payload recipient is invalid")
        key_id = item.get("key_id")
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id) or key_id in result:
            raise EncryptedPayloadError("Encrypted payload recipient key id is invalid")
        _decode(item.get("wrapped_key"), minimum=384, maximum=384)
        result.add(key_id)
    return result


def validate_payload(value: str, expected_key_ids: Iterable[str]) -> None:
    if len(value) > 150_000:
        raise EncryptedPayloadError("Encrypted payload is too large")
    try:
        envelope = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise EncryptedPayloadError("Encrypted payload must be a JSON envelope") from exc
    if not isinstance(envelope, dict) or envelope.get("v") != 1 or envelope.get("alg") != ALGORITHM:
        raise EncryptedPayloadError("Encrypted payload version or algorithm is unsupported")
    _decode(envelope.get("iv"), minimum=12, maximum=12)
    _decode(envelope.get("ciphertext"), minimum=16, maximum=120_000)
    recipients = _recipients(envelope.get("recipients"))
    expected = set(expected_key_ids)
    if recipients != expected:
        raise EncryptedPayloadError("Encrypted payload recipients do not match this conversation")


def validate_attachment_metadata(value: str, expected_key_ids: Iterable[str]) -> None:
    if len(value) > 12_000:
        raise EncryptedPayloadError("Encrypted attachment metadata is too large")
    try:
        metadata = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise EncryptedPayloadError(
            "Encrypted attachment metadata must be a JSON envelope"
        ) from exc
    if not isinstance(metadata, dict) or metadata.get("v") != 1 or metadata.get("alg") != ALGORITHM:
        raise EncryptedPayloadError("Encrypted attachment version or algorithm is unsupported")
    _decode(metadata.get("file_iv"), minimum=12, maximum=12)
    _decode(metadata.get("details_iv"), minimum=12, maximum=12)
    _decode(metadata.get("details_ciphertext"), minimum=16, maximum=4096)
    recipients = _recipients(metadata.get("recipients"))
    if recipients != set(expected_key_ids):
        raise EncryptedPayloadError(
            "Encrypted attachment recipients do not match this conversation"
        )
