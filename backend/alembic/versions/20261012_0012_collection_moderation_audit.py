"""Add append-only collection moderation history."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0012"
down_revision = "20261012_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_unique_constraint(
        "uq_collection_chat_reports_id_tenant",
        "collection_chat_reports",
        ["id", "tenant_id"],
    )
    op.create_table(
        "collection_moderation_actions",
        sa.Column("id", uuid, nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("report_id", uuid, nullable=False),
        sa.Column("actor_user_id", uuid, nullable=True),
        sa.Column("actor_role", sa.String(length=24), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "tenant_id"],
            ["collection_chat_reports.id", "collection_chat_reports.tenant_id"],
            name="fk_collection_moderation_action_report_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_moderation_actions_report_created",
        "collection_moderation_actions",
        ["report_id", "created_at", "id"],
    )
    op.create_index(
        "ix_collection_moderation_actions_tenant_created",
        "collection_moderation_actions",
        ["tenant_id", "created_at", "id"],
    )
    op.execute("""INSERT INTO collection_moderation_actions
        (id, tenant_id, report_id, actor_user_id, actor_role, action_type,
         previous_status, new_status, note, created_at)
        SELECT gen_random_uuid(), tenant_id, id, NULL, 'system',
               'history_baseline', NULL, status,
               'Audit history starts here; earlier moderation actions were not recorded.', CURRENT_TIMESTAMP
        FROM collection_chat_reports""")
    op.execute("ALTER TABLE collection_moderation_actions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE collection_moderation_actions FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation_collection_moderation_actions
        ON collection_moderation_actions
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)"""
    )
    op.execute("""CREATE FUNCTION reject_collection_moderation_action_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND (current_setting('app.collection_moderation_cleanup', true) = 'on'
               OR pg_trigger_depth() > 1)
             AND OLD.actor_user_id IS NOT NULL
             AND NEW.actor_user_id IS NULL
             AND (to_jsonb(NEW) - 'actor_user_id') = (to_jsonb(OLD) - 'actor_user_id') THEN
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE'
             AND current_setting('app.collection_moderation_cleanup', true) = 'on' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'collection moderation actions are append-only';
        END;
        $$""")
    op.execute("""CREATE TRIGGER collection_moderation_actions_append_only
        BEFORE UPDATE OR DELETE ON collection_moderation_actions
        FOR EACH ROW EXECUTE FUNCTION reject_collection_moderation_action_mutation()""")
    op.execute("""CREATE FUNCTION allow_collection_moderation_cascade()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM set_config('app.collection_moderation_cleanup', 'on', true);
          RETURN OLD;
        END;
        $$""")
    op.execute("""CREATE FUNCTION finish_collection_moderation_cascade()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM set_config('app.collection_moderation_cleanup', 'off', true);
          RETURN NULL;
        END;
        $$""")
    op.execute("""CREATE TRIGGER collection_moderation_cascade_begin
        BEFORE DELETE ON collection_chat_reports
        FOR EACH ROW EXECUTE FUNCTION allow_collection_moderation_cascade()""")
    op.execute("""CREATE TRIGGER collection_moderation_cascade_end
        AFTER DELETE ON collection_chat_reports
        FOR EACH STATEMENT EXECUTE FUNCTION finish_collection_moderation_cascade()""")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS collection_moderation_cascade_end ON collection_chat_reports"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS collection_moderation_cascade_begin ON collection_chat_reports"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS collection_moderation_actions_append_only ON collection_moderation_actions"
    )
    op.execute("DROP FUNCTION IF EXISTS finish_collection_moderation_cascade()")
    op.execute("DROP FUNCTION IF EXISTS allow_collection_moderation_cascade()")
    op.execute("DROP FUNCTION IF EXISTS reject_collection_moderation_action_mutation()")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_collection_moderation_actions ON collection_moderation_actions"
    )
    op.execute("ALTER TABLE collection_moderation_actions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE collection_moderation_actions DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_collection_moderation_actions_tenant_created",
        table_name="collection_moderation_actions",
    )
    op.drop_index(
        "ix_collection_moderation_actions_report_created",
        table_name="collection_moderation_actions",
    )
    op.drop_table("collection_moderation_actions")
    op.drop_constraint(
        "uq_collection_chat_reports_id_tenant",
        "collection_chat_reports",
        type_="unique",
    )
