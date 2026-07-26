from __future__ import annotations

import os
import subprocess
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = BACKEND_ROOT / "scripts" / "validate_prod_env.sh"


def _write_env_file(
    path: Path,
    *,
    include_public_origin: bool = True,
    include_connector_urls: bool = False,
    include_weak_secrets: bool = False,
) -> None:
    base_values = {
        "AKS_ENV": "production",
        "AKS_DATABASE_URL": "postgresql+psycopg://postgres:postgres@postgres:5432/knowledge",
        "AKS_REDIS_URL": "redis://:redis@redis:6379/0",
        "AKS_JWT_SECRET": "x" * 32,
        "AKS_REFRESH_TOKEN_HASH_SECRET": "y" * 32,
        "AKS_PROVIDER_SECRET_BACKEND": "env_keyring",
        "AKS_ADMIN_BREAK_GLASS_ENABLED": "false",
        "AKS_PROVIDER_SECRET_ACTIVE_KID": "prod-k1",
        "AKS_PROVIDER_SECRET_KEYRING_JSON": '{"prod-k1":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa="}',
        "AKS_PROVIDER_SECRET_AUDIT_READS": "true",
        "AVERQEL_POSTGRES_PASSWORD": "postgres-password-value-strong",
        "AVERQEL_REDIS_PASSWORD": "redis-password-value-strong",
        "AVERQEL_MINIO_ROOT_PASSWORD": "minio-password-value-strong",
    }
    values = dict(base_values)
    if include_public_origin:
        values["AVERQEL_PUBLIC_ORIGIN"] = "https://averqel.localhost"

    if include_connector_urls:
        values["AKS_CONNECTOR_OAUTH_REDIRECT_URI"] = (
            "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
        )
        values["AKS_CONNECTOR_OAUTH_FRONTEND_REDIRECT_URI"] = (
            "https://averqel.localhost/dashboard"
        )

    if include_weak_secrets:
        values["AKS_JWT_SECRET"] = "too-short"

    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def test_validate_prod_env_passes_with_public_origin(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.vps"
    _write_env_file(env_file, include_public_origin=True)
    completed = subprocess.run(
        ["bash", str(VALIDATE_SCRIPT), str(env_file)],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "will be derived from AVERQEL_PUBLIC_ORIGIN" in completed.stdout


def test_validate_prod_env_fails_when_everything_missing(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.vps"
    _write_env_file(env_file, include_public_origin=False, include_connector_urls=False)
    completed = subprocess.run(
        ["bash", str(VALIDATE_SCRIPT), str(env_file)],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert (
        "FAIL: AVERQEL_PUBLIC_ORIGIN or AKS_CONNECTOR_OAUTH_REDIRECT_URI must be configured"
        in completed.stdout
    )


def test_validate_prod_env_fails_with_weak_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.vps"
    _write_env_file(env_file, include_weak_secrets=True)
    completed = subprocess.run(
        ["bash", str(VALIDATE_SCRIPT), str(env_file)],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "FAIL: AKS_JWT_SECRET is weak or default-like" in completed.stdout
