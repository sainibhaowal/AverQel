from __future__ import annotations

import json
import logging

import pytest

from app.core.context import bind_request_context, clear_request_context
from app.core.logging import configure_logging


def test_provider_secret_logging_redacts_provider_secret_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    tokens = bind_request_context(
        trace_id="trc_provider_secret_redaction",
        tenant_id="tenant_provider_secret_redaction",
        user_id="user_provider_secret_redaction",
    )
    try:
        logger = logging.getLogger("provider.secret.redaction")
        logger.info(
            "provider secret lifecycle event",
            extra={
                "secret_ciphertext": b"cipher-bytes",
                "oauth_access_token": "access-secret",
                "secret_type": "api_key",
            },
        )
    finally:
        clear_request_context(tokens)

    captured = capsys.readouterr().err.strip().splitlines()
    assert captured
    payload = json.loads(captured[-1])
    encoded = json.dumps(payload)
    assert "cipher-bytes" not in encoded
    assert "access-secret" not in encoded
    assert "[redacted]" in encoded or "[redacted-bytes]" in encoded
