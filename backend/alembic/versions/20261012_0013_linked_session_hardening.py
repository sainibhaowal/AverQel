"""Backfill and tenant-isolate linked authentication sessions."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261012_0013"
down_revision = "20261012_0012"
branch_labels = None
depends_on = None

BACKFILL_SQL = """
WITH family_candidates AS (
    SELECT
        rt.tenant_id,
        rt.token_family_id,
        MIN(rt.user_id::text)::uuid AS user_id,
        MIN(rt.created_at) AS created_at,
        MAX(rt.created_at) AS last_seen_at
    FROM refresh_tokens AS rt
    WHERE rt.session_id IS NULL
      AND rt.revoked_at IS NULL
      AND rt.expires_at > CURRENT_TIMESTAMP
    GROUP BY rt.tenant_id, rt.token_family_id
    HAVING COUNT(DISTINCT rt.user_id) = 1
       AND NOT EXISTS (
           SELECT 1
           FROM auth_sessions AS existing
           WHERE existing.tenant_id = rt.tenant_id
             AND existing.token_family_id = rt.token_family_id
       )
), created_sessions AS (
    INSERT INTO auth_sessions (
        id, tenant_id, user_id, token_family_id, device_id, label,
        user_agent, ip_hash, created_at, last_seen_at
    )
    SELECT
        gen_random_uuid(),
        candidate.tenant_id,
        candidate.user_id,
        candidate.token_family_id,
        'legacy-' || REPLACE(candidate.token_family_id::text, '-', ''),
        'Previously signed-in device',
        NULL,
        NULL,
        candidate.created_at,
        candidate.last_seen_at
    FROM family_candidates AS candidate
    RETURNING tenant_id, user_id, token_family_id, id
), linked_tokens AS (
    UPDATE refresh_tokens AS rt
    SET session_id = created.id
    FROM created_sessions AS created
    WHERE rt.tenant_id = created.tenant_id
      AND rt.user_id = created.user_id
      AND rt.token_family_id = created.token_family_id
      AND rt.session_id IS NULL
      AND rt.revoked_at IS NULL
      AND rt.expires_at > CURRENT_TIMESTAMP
    RETURNING rt.tenant_id, rt.user_id
)
SELECT COUNT(*) FROM linked_tokens
"""

UNLINKED_REFRESH_REVOKE_SQL = """
WITH orphan_rows AS (
    SELECT DISTINCT tenant_id, user_id, token_family_id
    FROM refresh_tokens
    WHERE session_id IS NULL
      AND revoked_at IS NULL
      AND expires_at > CURRENT_TIMESTAMP
), revoked_sessions AS (
    UPDATE auth_sessions AS auth_session
    SET revoked_at = CURRENT_TIMESTAMP,
        revocation_reason = 'legacy_session_unlinked'
    FROM orphan_rows AS orphan
    WHERE auth_session.tenant_id = orphan.tenant_id
      AND auth_session.user_id = orphan.user_id
      AND auth_session.token_family_id = orphan.token_family_id
      AND auth_session.revoked_at IS NULL
    RETURNING auth_session.tenant_id, auth_session.user_id
), revoked_tokens AS (
    UPDATE refresh_tokens AS refresh_token
    SET revoked_at = CURRENT_TIMESTAMP,
        revocation_reason = 'legacy_session_unlinked'
    FROM orphan_rows AS orphan
    WHERE refresh_token.tenant_id = orphan.tenant_id
      AND refresh_token.user_id = orphan.user_id
      AND refresh_token.token_family_id = orphan.token_family_id
      AND refresh_token.session_id IS NULL
      AND refresh_token.revoked_at IS NULL
      AND refresh_token.expires_at > CURRENT_TIMESTAMP
    RETURNING refresh_token.tenant_id, refresh_token.user_id
), affected_users AS (
    SELECT tenant_id, user_id FROM revoked_tokens
    UNION
    SELECT tenant_id, user_id FROM revoked_sessions
    UNION
    SELECT DISTINCT tenant_id, user_id
    FROM auth_sessions
    WHERE device_id LIKE 'legacy-%'
      AND label = 'Previously signed-in device'
)
UPDATE users AS u
SET access_token_version = u.access_token_version + 1
FROM affected_users AS affected
WHERE u.tenant_id = affected.tenant_id
  AND u.id = affected.user_id
"""


def upgrade() -> None:
    # Existing tenant policies protect refresh_tokens and users. Migration
    # backfills intentionally span tenants under the dedicated bypass policy.
    op.execute("SELECT set_config('app.tenant_id', 'bypass', true)")
    # Existing unrevoked refresh families predate session binding. Only link
    # families with one unambiguous owner and an unexpired credential.
    op.execute(sa.text(BACKFILL_SQL))
    # Any eligible token still unlinked is ambiguous or inconsistent. Revoke
    # it and invalidate its owner's access tokens rather than leave an
    # unmanageable legacy session active.
    op.execute(sa.text(UNLINKED_REFRESH_REVOKE_SQL))

    op.create_index(
        "ix_auth_sessions_owner_last_seen",
        "auth_sessions",
        ["tenant_id", "user_id", "last_seen_at", "id"],
    )
    op.execute("ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_sessions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_auth_sessions ON auth_sessions
        USING (
            current_setting('app.tenant_id', true) = 'bypass'
            OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = 'bypass'
            OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid
        )
        """)


def downgrade() -> None:
    # Backfilled links and token-version increments are intentionally retained:
    # undoing either can re-enable a pre-session access token during rollback.
    op.execute("DROP POLICY IF EXISTS tenant_isolation_auth_sessions ON auth_sessions")
    op.execute("ALTER TABLE auth_sessions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_sessions DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_auth_sessions_owner_last_seen", table_name="auth_sessions")
