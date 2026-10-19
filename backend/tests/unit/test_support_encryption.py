from __future__ import annotations

import base64
import json

import pytest

from app.system.services.support_encryption import (
    ALGORITHM,
    EncryptedPayloadError,
    validate_attachment_metadata,
    validate_payload,
)


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _envelope(key_ids: list[str]) -> str:
    return json.dumps(
        {
            "v": 1,
            "alg": ALGORITHM,
            "iv": _encoded(b"i" * 12),
            "ciphertext": _encoded(b"c" * 32),
            "recipients": [
                {"key_id": key_id, "wrapped_key": _encoded(b"k" * 384)} for key_id in key_ids
            ],
        }
    )


def test_encrypted_payload_requires_exact_conversation_recipients() -> None:
    recipients = ["a" * 64, "b" * 64]

    validate_payload(_envelope(recipients), recipients)

    with pytest.raises(EncryptedPayloadError, match="recipients do not match"):
        validate_payload(_envelope(recipients[:1]), recipients)


def test_encrypted_payload_rejects_duplicate_or_malformed_recipient_keys() -> None:
    with pytest.raises(EncryptedPayloadError, match="key id is invalid"):
        validate_payload(_envelope(["a" * 64, "a" * 64]), ["a" * 64])

    with pytest.raises(EncryptedPayloadError, match="key id is invalid"):
        validate_payload(_envelope(["not-a-fingerprint"]), ["not-a-fingerprint"])


def test_encrypted_payload_rejects_invalid_ciphertext_and_oversized_payload() -> None:
    envelope = json.loads(_envelope(["a" * 64]))
    envelope["ciphertext"] = _encoded(b"short")
    with pytest.raises(EncryptedPayloadError, match="invalid length"):
        validate_payload(json.dumps(envelope), ["a" * 64])

    with pytest.raises(EncryptedPayloadError, match="too large"):
        validate_payload(" " * 150_001, ["a" * 64])


def test_encrypted_attachment_metadata_requires_exact_recipients() -> None:
    key_ids = ["a" * 64, "b" * 64]
    metadata = json.dumps(
        {
            "v": 1,
            "alg": ALGORITHM,
            "file_iv": _encoded(b"f" * 12),
            "details_iv": _encoded(b"d" * 12),
            "details_ciphertext": _encoded(b"x" * 32),
            "recipients": [
                {"key_id": key_id, "wrapped_key": _encoded(b"k" * 384)} for key_id in key_ids
            ],
        }
    )

    validate_attachment_metadata(metadata, key_ids)

    with pytest.raises(EncryptedPayloadError, match="recipients do not match"):
        validate_attachment_metadata(metadata, key_ids[:1])
