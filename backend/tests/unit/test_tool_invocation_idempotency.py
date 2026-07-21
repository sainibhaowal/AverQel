import pytest

from app.deepspace.execution.agent_permissions import PermissionLevel
from app.deepspace.execution.tool_contracts import infer_tool_contract, redact_tool_payload


@pytest.mark.unit_no_db
def test_external_side_effect_contract_requires_idempotency_and_compensation() -> None:
    contract = infer_tool_contract(name="gmail_send", permission_level=PermissionLevel.TIER2_CONFIRM)
    assert contract.idempotency_support is False
    assert contract.compensation_required is True
    assert contract.approval_requirement == "human"


@pytest.mark.unit_no_db
def test_tool_payload_redaction_is_recursive() -> None:
    payload = {"nested": {"api_key": "secret", "body": "safe"}, "items": [{"password": "secret"}]}
    assert redact_tool_payload(payload) == {
        "nested": {"api_key": "[REDACTED]", "body": "safe"},
        "items": [{"password": "[REDACTED]"}],
    }
