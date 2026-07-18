from __future__ import annotations

import base64
import json

import pytest

from app.core.config import Settings


def test_provider_secret_keyring_requires_active_kid_pairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AKS_PROVIDER_SECRET_ACTIVE_KID", raising=False)
    monkeypatch.delenv("AKS_PROVIDER_SECRET_KEYRING_JSON", raising=False)
    with pytest.raises(ValueError, match="must be set together"):
        Settings(
            _env_file=None,
            provider_secret_active_kid="kid-only",
            provider_secret_keyring_json=None,
        )


def test_provider_secret_keyring_requires_active_kid_to_exist() -> None:
    keyring = json.dumps(
        {"other-kid": base64.urlsafe_b64encode(b"4" * 32).decode("utf-8")}
    )
    with pytest.raises(ValueError, match="must exist in provider_secret_keyring_json"):
        Settings(
            provider_secret_active_kid="kid-active",
            provider_secret_keyring_json=keyring,
        )


def test_provider_secret_keyring_accepts_valid_aesgcm_key() -> None:
    keyring = json.dumps(
        {"kid-active": base64.urlsafe_b64encode(b"5" * 32).decode("utf-8")}
    )
    settings = Settings(
        provider_secret_active_kid="kid-active",
        provider_secret_keyring_json=keyring,
    )

    assert settings.provider_secret_active_kid == "kid-active"


def test_provider_secret_kms_backend_requires_kms_key_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AKS_PROVIDER_SECRET_ACTIVE_KID", raising=False)
    monkeypatch.delenv("AKS_PROVIDER_SECRET_KEYRING_JSON", raising=False)
    with pytest.raises(ValueError, match="provider_secret_aws_kms_key_id"):
        Settings(
            _env_file=None,
            provider_secret_backend="aws_kms",
            provider_secret_aws_kms_key_id=None,
        )


def test_provider_secret_kms_backend_rejects_env_keyring_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AKS_PROVIDER_SECRET_ACTIVE_KID", raising=False)
    monkeypatch.delenv("AKS_PROVIDER_SECRET_KEYRING_JSON", raising=False)
    keyring = json.dumps(
        {"kid-active": base64.urlsafe_b64encode(b"6" * 32).decode("utf-8")}
    )
    with pytest.raises(
        ValueError, match="not used when provider_secret_backend=aws_kms"
    ):
        Settings(
            _env_file=None,
            provider_secret_backend="aws_kms",
            provider_secret_aws_kms_key_id="arn:aws:kms:eu-central-1:123:key/abc",
            provider_secret_active_kid="kid-active",
            provider_secret_keyring_json=keyring,
        )
