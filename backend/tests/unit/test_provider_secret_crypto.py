from __future__ import annotations

import base64
import json

import pytest

from app.core.config import Settings
from app.providers.services.provider_secret_crypto import (
    ProviderSecretCrypto,
    ProviderSecretCryptoError,
)


def _keyring_json() -> str:
    return json.dumps(
        {"kid-active": base64.urlsafe_b64encode(b"1" * 32).decode("utf-8")}
    )


def test_provider_secret_crypto_roundtrip() -> None:
    settings = Settings(
        provider_secret_active_kid="kid-active",
        provider_secret_keyring_json=_keyring_json(),
    )
    crypto = ProviderSecretCrypto(settings)

    encrypted = crypto.encrypt("super-secret", aad=b"tenant:provider:api_key")
    decrypted = crypto.decrypt(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        kid=encrypted.kid,
        aad=b"tenant:provider:api_key",
    )

    assert decrypted == b"super-secret"
    assert encrypted.kid == "kid-active"


def test_provider_secret_crypto_rejects_missing_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AKS_PROVIDER_SECRET_ACTIVE_KID", raising=False)
    monkeypatch.delenv("AKS_PROVIDER_SECRET_KEYRING_JSON", raising=False)
    settings = Settings(
        _env_file=None,
        provider_secret_active_kid=None,
        provider_secret_keyring_json=None,
    )
    crypto = ProviderSecretCrypto(settings)

    with pytest.raises(ProviderSecretCryptoError):
        crypto.encrypt("secret")


def test_provider_secret_crypto_rejects_wrong_aad() -> None:
    settings = Settings(
        provider_secret_active_kid="kid-active",
        provider_secret_keyring_json=_keyring_json(),
    )
    crypto = ProviderSecretCrypto(settings)
    encrypted = crypto.encrypt("super-secret", aad=b"correct")

    with pytest.raises(ProviderSecretCryptoError):
        crypto.decrypt(
            ciphertext=encrypted.ciphertext,
            nonce=encrypted.nonce,
            kid=encrypted.kid,
            aad=b"wrong",
        )


def test_provider_secret_crypto_supports_aws_kms_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AKS_PROVIDER_SECRET_ACTIVE_KID", raising=False)
    monkeypatch.delenv("AKS_PROVIDER_SECRET_KEYRING_JSON", raising=False)

    class FakeKmsClient:
        def encrypt(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["KeyId"] == "arn:aws:kms:eu-central-1:123:key/abc"
            assert "aad_b64" in kwargs["EncryptionContext"]
            return {
                "CiphertextBlob": b"kms:" + bytes(kwargs["Plaintext"]),
                "KeyId": kwargs["KeyId"],
            }

        def decrypt(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["KeyId"] == "arn:aws:kms:eu-central-1:123:key/abc"
            assert "aad_b64" in kwargs["EncryptionContext"]
            return {"Plaintext": bytes(kwargs["CiphertextBlob"]).removeprefix(b"kms:")}

    monkeypatch.setattr(
        "app.providers.services.provider_secret_crypto.boto3.client",
        lambda *args, **kwargs: FakeKmsClient(),
    )
    settings = Settings(
        _env_file=None,
        provider_secret_backend="aws_kms",
        provider_secret_aws_kms_key_id="arn:aws:kms:eu-central-1:123:key/abc",
    )
    crypto = ProviderSecretCrypto(settings)

    encrypted = crypto.encrypt("super-secret", aad=b"tenant:provider:api_key")
    decrypted = crypto.decrypt(
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        kid=encrypted.kid,
        aad=b"tenant:provider:api_key",
    )

    assert encrypted.nonce == b""
    assert decrypted == b"super-secret"
