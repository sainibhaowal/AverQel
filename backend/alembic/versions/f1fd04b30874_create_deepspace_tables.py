"""create_deepspace_tables

Revision ID: f1fd04b30874
Revises: bb1ef0954cca
Create Date: 2026-05-06 16:23:32.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f1fd04b30874"
down_revision = "bb1ef0954cca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. AgentActivity
    op.create_table(
        "agent_activities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_activities_activity_type"),
        "agent_activities",
        ["activity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_activities_tenant_id"),
        "agent_activities",
        ["tenant_id"],
        unique=False,
    )

    # 2. AgentAuditLog
    op.create_table(
        "agent_audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("tool_args", sa.JSON(), nullable=True),
        sa.Column("tool_result", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_audit_logs_conversation_id"),
        "agent_audit_logs",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_audit_logs_tenant_id"),
        "agent_audit_logs",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_audit_logs_user_id"),
        "agent_audit_logs",
        ["user_id"],
        unique=False,
    )

    # 3. AgentMemory
    op.create_table(
        "agent_memory",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_memory_id"), "agent_memory", ["id"], unique=False)
    op.create_index(op.f("ix_agent_memory_key"), "agent_memory", ["key"], unique=False)
    op.create_index(op.f("ix_agent_memory_scope"), "agent_memory", ["scope"], unique=False)
    op.create_index(op.f("ix_agent_memory_tenant_id"), "agent_memory", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_agent_memory_user_id"), "agent_memory", ["user_id"], unique=False)

    # 4. AgentTodo
    op.create_table(
        "agent_todos",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("active_form", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_todos_id"), "agent_todos", ["id"], unique=False)
    op.create_index(op.f("ix_agent_todos_tenant_id"), "agent_todos", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_agent_todos_thread_id"), "agent_todos", ["thread_id"], unique=False)
    op.create_index(op.f("ix_agent_todos_user_id"), "agent_todos", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("agent_todos")
    op.drop_table("agent_memory")
    op.drop_table("agent_audit_logs")
    op.drop_table("agent_activities")
