from __future__ import annotations

from app.services.system.audit_service import redact_audit_details


def test_audit_detail_redaction_blocks_secrets_and_private_content() -> None:
    redacted = redact_audit_details(
        {
            "api_key": "sk-secret",
            "oauth_access_token": "oauth-secret",
            "prompt": "private user prompt",
            "answer_content": "private answer",
            "query_text": "who owns this private file",
            "html_content": "<p>private note</p>",
            "storage_object_key": "tenant/doc/private.pdf",
            "reason": "support request",
            "target_user_id": "user-123",
        }
    )

    assert redacted["api_key"] == "[redacted]"
    assert redacted["oauth_access_token"] == "[redacted]"
    assert redacted["prompt"] == "[redacted]"
    assert redacted["answer_content"] == "[redacted]"
    assert redacted["query_text"] == "[redacted]"
    assert redacted["html_content"] == "[redacted]"
    assert redacted["storage_object_key"] == "[redacted]"
    assert redacted["reason"] == "support request"
    assert redacted["target_user_id"] == "user-123"
