"""Remove previously persisted native MCP result and error bodies."""

from __future__ import annotations

from alembic import op

revision = "20260722_0002"
down_revision = "20260722_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep event identity for operational diagnostics, but remove arguments,
    # result content, rendered text, and exception messages from old rows.
    op.execute("""
        UPDATE mcp_events
        SET payload = jsonb_build_object(
            'tool', COALESCE(payload ->> 'tool', ''),
            'privacy_scrubbed', true
        )
        WHERE event_type IN ('tool_call_started', 'tool_call_completed', 'tool_call_failed')
        """)
    op.execute("""
        UPDATE agent_audit_logs
        SET tool_result = '[MCP result removed for privacy]'
        WHERE tool_name LIKE 'mcp_%'
        """)


def downgrade() -> None:
    raise RuntimeError(
        "MCP event and audit result bodies were intentionally scrubbed and cannot be restored."
    )
