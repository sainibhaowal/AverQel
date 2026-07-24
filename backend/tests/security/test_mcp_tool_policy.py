from __future__ import annotations

from tests.integration import test_mcp_phase5_policy as phase5_tests


def test_tool_policy_is_deny_first_and_requires_approval_for_risk(
    db_session, seed_user
) -> None:
    phase5_tests.test_phase5_policy_matrix_is_deny_first(db_session, seed_user)
