from __future__ import annotations

from app.system.schemas.errors import (
    WEEK2_ERROR_CODES,
    Week2ErrorCode,
    is_week2_error_code,
)


def test_week2_error_code_catalog_contains_required_contract_examples() -> None:
    required = {
        "TENANT_REQUIRED",
        "INVALID_UPLOAD_TYPE",
        "DOC_TOO_LARGE",
        "IDEMPOTENCY_CONFLICT",
        "MALWARE_SCAN_FAILED",
        "CONNECTOR_OAUTH_UNSUPPORTED",
        "CONNECTOR_OAUTH_INVALID",
        "CONNECTOR_OAUTH_TOKEN_EXCHANGE_FAILED",
    }
    assert required.issubset(WEEK2_ERROR_CODES)


def test_week2_error_code_enum_and_predicate_are_consistent() -> None:
    enum_values = {entry.value for entry in Week2ErrorCode}
    assert enum_values == set(WEEK2_ERROR_CODES)

    for code in enum_values:
        assert is_week2_error_code(code) is True

    assert is_week2_error_code("NOT_A_REAL_WEEK2_CODE") is False
