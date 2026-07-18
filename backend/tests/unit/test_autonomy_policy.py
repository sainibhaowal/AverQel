import pytest

from app.services.deepspace.policy.autonomy_policy import AutonomyPolicy


@pytest.mark.unit_no_db
def test_autonomy_policy_allows_safe_reads_but_requires_approval_for_writes() -> None:
    read = AutonomyPolicy.assess(tool_name="github_search", args={"query": "runtime"}, execution_mode="auto_review")
    write = AutonomyPolicy.assess(tool_name="github_update_file", args={"path": "README.md"}, execution_mode="full_access")
    assert read.disposition == "require_human"  # external capability is never silently auto-approved
    assert write.disposition == "require_human"
    assert write.requires_idempotency is True


@pytest.mark.unit_no_db
def test_autonomy_policy_blocks_privileged_spawn() -> None:
    decision = AutonomyPolicy.assess(tool_name="task", args={}, execution_mode="full_access")
    assert decision.disposition == "block"
    assert decision.risk_class == "privileged"
