from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ALGORITHM = "RSA-OAEP-3072+AES-256-GCM"


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def register_support_key(client: TestClient, headers: dict[str, str], *, scope: str) -> str:
    pair = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public_key = pair.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = hashlib.sha256(public_key).hexdigest()
    registration = {
        "key_id": key_id,
        "public_key": _b64(public_key),
        # API tests verify storage/access controls; browser tests exercise real wrapping.
        "private_key_ciphertext": _b64(b"p" * 128),
        "salt": _b64(b"s" * 16),
        "iv": _b64(b"i" * 12),
    }
    endpoint = (
        "/api/v1/support/encryption/admin-private-key"
        if scope == "platform_admin"
        else "/api/v1/support/encryption/me"
    )
    response = client.put(endpoint, headers=headers, json=registration)
    assert response.status_code == 200, response.text
    return key_id


def create_encrypted_payload(key_ids: list[str], *, value: Any = None) -> str:
    # The API intentionally validates envelope shape/recipient binding only. The
    # browser integration test verifies the actual Web Crypto ciphertext.
    del value
    return json.dumps(
        {
            "v": 1,
            "alg": ALGORITHM,
            "iv": _b64(b"i" * 12),
            "ciphertext": _b64(b"c" * 64),
            "recipients": [
                {"key_id": key_id, "wrapped_key": _b64(b"k" * 384)} for key_id in key_ids
            ],
        }
    )


def create_encrypted_attachment_metadata(key_ids: list[str]) -> str:
    return json.dumps(
        {
            "v": 1,
            "alg": ALGORITHM,
            "file_iv": _b64(b"f" * 12),
            "details_iv": _b64(b"d" * 12),
            "details_ciphertext": _b64(b"x" * 64),
            "recipients": [
                {"key_id": key_id, "wrapped_key": _b64(b"k" * 384)} for key_id in key_ids
            ],
        }
    )
