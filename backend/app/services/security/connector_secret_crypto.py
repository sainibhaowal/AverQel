from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings, get_settings


class ConnectorSecretCryptoError(RuntimeError):
    """Raised when connector-secret encryption or decryption fails."""


@dataclass(frozen=True, slots=True)
class EncryptedConnectorSecret:
    ciphertext: bytes
    nonce: bytes
    kid: str


class ConnectorSecretCrypto:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        # We allow fallback to provider settings if connector-specific ones aren't set
        self._backend = getattr(
            self.settings,
            "connector_secret_backend",
            self.settings.provider_secret_backend,
        )
        self._active_kid = getattr(
            self.settings,
            "connector_secret_active_kid",
            self.settings.provider_secret_active_kid,
        )

        keyring_json = getattr(
            self.settings,
            "connector_secret_keyring_json",
            self.settings.provider_secret_keyring_json,
        )
        self._keyring = (
            self._parse_keyring(keyring_json) if self._backend == "env_keyring" else {}
        )

        self._kms_client = None
        if self._backend == "aws_kms":
            # Fallback to provider AWS settings if needed
            region = getattr(
                self.settings,
                "connector_secret_aws_kms_region",
                self.settings.provider_secret_aws_kms_region,
            )
            endpoint = getattr(
                self.settings,
                "connector_secret_aws_kms_endpoint_url",
                self.settings.provider_secret_aws_kms_endpoint_url,
            )
            self._kms_client = boto3.client(
                "kms",
                region_name=region,
                endpoint_url=endpoint,
            )

    @staticmethod
    def _kms_context(aad: bytes | None) -> dict[str, str]:
        if not aad:
            return {}
        return {"aad_b64": base64.urlsafe_b64encode(aad).decode("utf-8")}

    @staticmethod
    def _parse_keyring(raw: str | None) -> dict[str, bytes]:
        if raw is None:
            return {}

        cleaned = raw.strip()
        if not cleaned:
            return {}

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ConnectorSecretCryptoError(
                "connector secret keyring is not valid JSON"
            ) from exc

        if not isinstance(payload, dict) or not payload:
            raise ConnectorSecretCryptoError(
                "connector secret keyring must be a non-empty JSON object"
            )

        keyring: dict[str, bytes] = {}
        for kid, encoded_key in payload.items():
            if not isinstance(kid, str) or not kid.strip():
                raise ConnectorSecretCryptoError(
                    "connector secret key ids must be non-empty strings"
                )
            if not isinstance(encoded_key, str) or not encoded_key.strip():
                raise ConnectorSecretCryptoError(
                    "connector secret keys must be non-empty base64 strings"
                )
            try:
                key_bytes = base64.urlsafe_b64decode(encoded_key.encode("utf-8"))
            except Exception as exc:
                raise ConnectorSecretCryptoError(
                    f"connector secret key for kid={kid!r} is not valid base64"
                ) from exc
            if len(key_bytes) not in {16, 24, 32}:
                raise ConnectorSecretCryptoError(
                    "connector secret keys must decode to 16, 24, or 32 bytes for AES-GCM"
                )
            keyring[kid.strip()] = key_bytes
        return keyring

    def encrypt(
        self, plaintext: str | bytes, *, aad: bytes | None = None
    ) -> EncryptedConnectorSecret:
        if isinstance(plaintext, str):
            plaintext_bytes = plaintext.encode("utf-8")
        else:
            plaintext_bytes = plaintext

        if not plaintext_bytes:
            raise ConnectorSecretCryptoError(
                "connector secret plaintext must not be empty"
            )

        if self._backend == "aws_kms":
            # Fallback to provider AWS settings if needed
            key_id = getattr(
                self.settings,
                "connector_secret_aws_kms_key_id",
                self.settings.provider_secret_aws_kms_key_id,
            )
            if not key_id or self._kms_client is None:
                raise ConnectorSecretCryptoError(
                    "aws kms connector secret backend is not configured"
                )
            try:
                response = self._kms_client.encrypt(
                    KeyId=key_id,
                    Plaintext=plaintext_bytes,
                    EncryptionContext=self._kms_context(aad),
                )
            except Exception as exc:
                raise ConnectorSecretCryptoError(
                    "connector secret encryption via aws kms failed"
                ) from exc
            ciphertext = response.get("CiphertextBlob")
            if not isinstance(ciphertext, bytes | bytearray):
                raise ConnectorSecretCryptoError(
                    "aws kms did not return a ciphertext blob"
                )
            return EncryptedConnectorSecret(
                ciphertext=bytes(ciphertext),
                nonce=b"",
                kid=str(response.get("KeyId") or key_id),
            )

        if not self._active_kid:
            raise ConnectorSecretCryptoError(
                "no active connector secret key id configured"
            )
        key = self._keyring.get(self._active_kid)
        if key is None:
            raise ConnectorSecretCryptoError(
                "active connector secret key id is not in the keyring"
            )

        cipher = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = cipher.encrypt(nonce, plaintext_bytes, aad)
        return EncryptedConnectorSecret(
            ciphertext=ciphertext, nonce=nonce, kid=self._active_kid
        )

    def decrypt(
        self,
        *,
        ciphertext: bytes,
        nonce: bytes,
        kid: str,
        aad: bytes | None = None,
    ) -> bytes:
        if self._backend == "aws_kms":
            if self._kms_client is None:
                raise ConnectorSecretCryptoError(
                    "aws kms connector secret backend is not configured"
                )
            try:
                # Fallback to provider AWS settings if needed
                fallback_key_id = getattr(
                    self.settings,
                    "connector_secret_aws_kms_key_id",
                    self.settings.provider_secret_aws_kms_key_id,
                )
                response = self._kms_client.decrypt(
                    CiphertextBlob=ciphertext,
                    EncryptionContext=self._kms_context(aad),
                    KeyId=kid or fallback_key_id,
                )
            except Exception as exc:
                raise ConnectorSecretCryptoError(
                    "connector secret decryption via aws kms failed"
                ) from exc
            plaintext = response.get("Plaintext")
            if not isinstance(plaintext, bytes | bytearray):
                raise ConnectorSecretCryptoError("aws kms did not return plaintext")
            return bytes(plaintext)

        key = self._keyring.get(kid)
        if key is None:
            raise ConnectorSecretCryptoError(
                "secret key id is not available for decryption"
            )
        try:
            cipher = AESGCM(key)
            return cipher.decrypt(nonce, ciphertext, aad)
        except Exception as exc:
            raise ConnectorSecretCryptoError(
                "connector secret decryption failed"
            ) from exc
