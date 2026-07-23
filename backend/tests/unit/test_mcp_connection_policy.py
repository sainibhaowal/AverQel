from __future__ import annotations

import pytest

from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy


@pytest.mark.unit_no_db
def test_mcp_connection_policy_has_conservative_fields_and_defaults() -> None:
    columns = MCPConnectionPolicy.__table__.columns
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
        "created_at",
        "updated_at",
    }.issubset(columns.keys())
    assert "true" in str(columns["read_only"].server_default.arg).lower()
    assert "false" in str(columns["default_enabled"].server_default.arg).lower()
    assert "read" in str(columns["risk_ceiling"].server_default.arg)
    assert "needs_approval" in str(columns["approval_rules"].server_default.arg)


@pytest.mark.unit_no_db
def test_mcp_connection_policy_is_one_policy_per_server() -> None:
    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in MCPConnectionPolicy.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("server_id",) in unique_constraints
