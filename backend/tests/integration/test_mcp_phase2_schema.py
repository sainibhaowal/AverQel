from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


def test_mcp_phase2_schema_has_identity_metadata_and_rls(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())

    registry_columns = {column["name"] for column in inspector.get_columns("mcp_registry_entries")}
    server_columns = {column["name"] for column in inspector.get_columns("mcp_servers")}
    token_columns = {column["name"] for column in inspector.get_columns("mcp_oauth_tokens")}
    policy_columns = {column["name"] for column in inspector.get_columns("mcp_connection_policies")}

    assert {
        "provider_slug",
        "publisher_type",
        "version",
        "documentation_url",
        "health_status",
        "health_checked_at",
        "requested_scopes",
        "supported_products",
        "risk_policy",
        "oauth_profile",
        "author_website_url",
        "support_url",
        "privacy_policy_url",
        "catalog_badges",
        "trusted_logo_key",
        "tool_categories",
        "tool_risk_summary",
    }.issubset(registry_columns)
    assert {
        "registry_entry_id",
        "provider_slug",
        "account_identity",
        "connection_policy_id",
        "catalog_revision",
    }.issubset(server_columns)
    assert {"user_id", "registry_entry_id", "provider_slug", "granted_scopes"}.issubset(
        token_columns
    )
    assert {
        "tenant_id",
        "user_id",
        "server_id",
        "allowed_tools",
        "denied_tools",
        "read_only",
        "risk_ceiling",
        "approval_rules",
        "tool_modes",
        "default_enabled",
        "deepspace_overrides",
        "conversation_overrides",
    }.issubset(policy_columns)

    rls_enabled, rls_forced = db_session.execute(text("""
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE oid = 'mcp_connection_policies'::regclass
            """)).one()
    assert rls_enabled is True
    assert rls_forced is True
    policy_name = db_session.execute(
        text("SELECT policyname FROM pg_policies " "WHERE tablename = 'mcp_connection_policies'")
    ).scalar_one()
    assert policy_name == "tenant_isolation_mcp_connection_policies"

    token_nullable = {
        column["name"]: column["nullable"] for column in inspector.get_columns("mcp_oauth_tokens")
    }
    assert token_nullable["user_id"] is False
    assert token_nullable["secret_ciphertext"] is False
    assert token_nullable["secret_nonce"] is False
    assert token_nullable["secret_kid"] is False
