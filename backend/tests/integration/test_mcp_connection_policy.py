from __future__ import annotations

from tests.integration import test_mcp_phase4_api as phase4_tests


def test_connection_policy_routes_enforce_owner_and_scope_boundaries(
    client, db_session, seed_user
) -> None:
    phase4_tests.test_phase4_policy_tools_and_scoped_overrides_are_tenant_user_owned(
        client, db_session, seed_user
    )


def test_connection_policy_rejects_unknown_scoped_resource(client, db_session, seed_user) -> None:
    phase4_tests.test_phase4_missing_scope_owner_cannot_change_override(
        client, db_session, seed_user
    )
