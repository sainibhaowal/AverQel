from __future__ import annotations

from tests.integration import test_mcp_phase4_api as phase4_tests


def test_mcp_server_and_scope_reads_are_tenant_isolated(client, db_session, seed_user) -> None:
    phase4_tests.test_phase4_policy_tools_and_scoped_overrides_are_tenant_user_owned(
        client, db_session, seed_user
    )
