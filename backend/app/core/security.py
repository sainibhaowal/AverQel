from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

DEFAULT_SECURE_TOKEN_BYTES: Final[int] = 32
PASSWORD_MIN_LENGTH: Final[int] = 8

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def generate_secure_token(length: int = DEFAULT_SECURE_TOKEN_BYTES) -> str:
    """
    Generate a cryptographically secure URL-safe token.

    The length parameter is expressed in bytes before URL-safe encoding.
    """
    if length <= 0:
        raise ValueError("length must be a positive integer")
    return secrets.token_urlsafe(length)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2."""
    if not password or not password.strip():
        raise ValueError("password must not be empty")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored Argon2 hash."""
    if not password or not password_hash:
        return False

    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_hash_needs_rehash(password_hash: str) -> bool:
    """Return True if an existing Argon2 hash should be upgraded."""
    if not password_hash:
        return False

    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def hash_refresh_token(raw_token: str, secret: str) -> str:
    """Hash a refresh token using HMAC-SHA256 with an application secret."""
    if not raw_token:
        raise ValueError("raw_token must not be empty")
    if not secret:
        raise ValueError("secret must not be empty")

    digest = hmac.new(
        secret.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()


def validate_password_policy(password: str) -> None:
    if not password or not password.strip():
        raise ValueError("password must not be empty")
