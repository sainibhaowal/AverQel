from __future__ import annotations

from tests.integration import test_mcp_phase4_api as phase4_tests


def test_cross_user_server_and_conversation_access_is_rejected(
    client, db_session, seed_user
) -> None:
    phase4_tests.test_phase4_policy_tools_and_scoped_overrides_are_tenant_user_owned(
        client, db_session, seed_user
    )
