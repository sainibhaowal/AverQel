from __future__ import annotations

from uuid import UUID

import pytest

from app.auth.dependencies import build_auth_context, create_access_token, decode_access_token
from app.core.config import get_settings
from app.core.errors import ApiError
from app.auth.roles import canonicalize_role_name
from app.auth.security import hash_password, hash_refresh_token, verify_password


def test_password_hash_and_verify_roundtrip() -> None:
    password = "VeryStrongPassword!123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip_claims() -> None:
    settings = get_settings()
    user_id = UUID("11111111-1111-7111-8111-111111111111")
    tenant_id = UUID("22222222-2222-7222-8222-222222222222")
    roles = {"admin", "reader"}

    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        settings=settings,
    )
    claims = decode_access_token(token, settings)

    assert claims["sub"] == str(user_id)
    assert claims["tenant_id"] == str(tenant_id)
    assert set(claims["roles"]) == {canonicalize_role_name(role) for role in roles}
    assert claims["iss"] == settings.jwt_issuer
    assert claims["aud"] == settings.jwt_audience


def test_auth_context_rejects_tenant_header_mismatch() -> None:
    claims = {
        "sub": "11111111-1111-7111-8111-111111111111",
        "tenant_id": "22222222-2222-7222-8222-222222222222",
        "roles": ["admin"],
        "jti": "33333333-3333-7333-8333-333333333333",
    }
    with pytest.raises(ApiError) as exc_info:
        build_auth_context(claims, "44444444-4444-7444-8444-444444444444")

    assert exc_info.value.code == "TENANT_SCOPE_MISMATCH"


def test_refresh_token_hash_is_deterministic_for_same_input() -> None:
    token = "test-token"
    secret = "refresh-secret-with-minimum-32-char-value"
    first = hash_refresh_token(token, secret)
    second = hash_refresh_token(token, secret)
    assert first == second
