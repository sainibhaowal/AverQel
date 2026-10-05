# Linked sessions: production hardening plan and operating guide

## Scope and current behavior

Linked sessions let an account holder review sign-ins and revoke a refresh-token
family for a browser or device. Access tokens carry the session ID, and the auth
dependency rejects a request when that session has been revoked. Password,
TOTP, and OAuth sign-in flows already create linked session records. The account
settings UI already lists sessions and exposes revocation for sessions other
than the current one.

The hardening work closes these gaps:

- Add database row-level tenant isolation for `auth_sessions` and explicitly set
  tenant context around its reads and writes.
- Link eligible, still-valid legacy refresh-token families during migration and
  invalidate older access-token versions so a pre-session access token cannot
  outlive that link unnoticed.
- Keep session state consistent with every refresh-token revocation path.
- Serialize refresh-token rotation to prevent concurrent use of one token from
  issuing multiple descendants.
- Make the API reject revocation of the current session, matching the UI.
- Bound session listing and retain revoked session history for a defined period.
- Give web sign-ins a random, persistent per-browser identifier and a readable
  label without fingerprinting the device.

## Implementation map

| Area | Files and interfaces |
| --- | --- |
| Schema / tenant isolation | `backend/alembic/versions/20261012_0013_linked_session_hardening.py`; `auth_sessions`; existing `refresh_tokens.session_id` and `users.access_token_version` |
| Token lifecycle | `backend/app/auth/repositories/refresh_tokens.py`; `revoke_token`, `revoke_family`, `revoke_all_for_user`, `get_by_hash` |
| Request and route behavior | `backend/app/auth/api.py`; `GET /api/v1/auth/sessions?limit=&offset=`, `DELETE /api/v1/auth/sessions/{session_id}`; `backend/app/auth/dependencies.py`; `backend/app/auth/services/auth_service.py` |
| Retention | `backend/app/core/config.py`; `backend/app/system/workers/tasks_maintenance.py`; existing `maintenance.retention_cleanup` scheduled in `backend/app/platform/worker/celery_app.py` |
| Web sign-in identity | `frontend/lib/auth-session-device.ts`; `frontend/app/auth/login/page.tsx`; password/TOTP payloads and the OAuth session-device handoff in `backend/app/auth/api.py` / `backend/app/auth/services/oauth_login_service.py` |
| Session management UI | `frontend/app/dashboard/settings/sessions/page.tsx`; paginated list, readable device details, safe current-session behavior |
| Verification and user guidance | `backend/tests/integration/test_auth_sessions.py`; `backend/tests/integration/test_retention_jobs.py`; `backend/tests/unit/test_auth_service_unit.py`; `backend/tests/unit/test_oauth_login_service.py`; `backend/tests/unit/test_worker_tasks.py`; `frontend/tests/linked-sessions-page.test.tsx`; `frontend/tests/auth-session-device.test.ts`; `frontend/app/documentation/profile/page.tsx` |

## Configuration and device privacy

`AKS_AUTH_SESSION_RETENTION_DAYS` controls how long revoked session history and
its linked refresh-token records are retained. The default is 90 days; valid
values are 1 through 3650 days. The daily `maintenance.retention_cleanup` job
uses this setting. Both deployment environment examples define the 90-day
default; operators should set and review it according to their retention
requirements.

The browser stores a random opaque device ID in local storage and sends it at
sign-in. The server stores that ID, a browser-derived label, and the user-agent
string. It does not collect a hardware fingerprint or raw IP address. The
label helps distinguish browser profiles; it does not prove which person or
physical device used the session. `last_seen_at` advances when a refresh token
is used, so the UI calls this the last token refresh rather than claiming to
show every request's activity.

## Safe implementation and rollout

1. Deploy application code that applies the authenticated tenant context before
   querying or changing session rows. During a rolling release, wait until old
   application instances that do not set this context have drained.
2. Apply the additive Alembic migration. It links unrevoked, unexpired
   refresh-token families whose tenant/family maps unambiguously to one user.
   If legacy data is inconsistent, it revokes the unlinked family and requires
   a fresh sign-in rather than leave an unmanageable token active. It increments
   affected users' access-token versions so old access tokens are invalidated;
   linked refresh tokens can obtain new session-bound access tokens.
3. Verify migration head, RLS flags and policy, backfill counts, and expected
   session ownership in staging before production rollout.
4. Smoke-test two independent sign-ins, listing and pagination, current-session
   rejection, revoking a different session, rejection of its next authenticated
   request and refresh, logout-all, and user/tenant isolation.
5. Confirm scheduled retention cleanup runs. It expires sessions whose refresh
   credentials are no longer valid and deletes revoked session/token rows only
   after the configured retention period. Old unlinked token records are also
   removed after that window. Audit events remain governed by the separate
   audit retention policy.

## Existing behavior to preserve

- Keep access-token and refresh-cookie formats and all existing login methods.
- Keep the session list as a JSON array and keep the successful revoke response
  as `{"success": true}`. Pagination only bounds rows and uses query parameters.
- Keep tenant and user ownership predicates even with RLS enabled.
- Keep individual revocation limited to another session; the current session
  continues to use the ordinary logout flow.
- Keep logout-all and administrative force-logout invalidating all sessions.
- Do not store raw refresh tokens, IP addresses, or a device fingerprint in
  session metadata.

## Verification evidence and release boundary

Local verification completed on 2026-10-05:

- `pytest -q -n 0 tests/integration/test_auth_sessions.py tests/integration/test_retention_jobs.py tests/unit/test_auth_service_unit.py tests/unit/test_oauth_login_service.py tests/unit/test_worker_tasks.py` — passed (44 tests).
- `pnpm exec vitest run tests/linked-sessions-page.test.tsx tests/auth-session-device.test.ts` — passed (4 tests).
- `pnpm exec tsc --noEmit` — passed.
- Ruff on the changed backend auth, retention, migration, and test files — passed.
- `alembic heads` — `20261012_0013 (head)`. The integration suite applied the migration and verified the backfill, row-level policy, tenant visibility, and token/session behavior.
- `git diff --check` — passed.

`alembic check` was attempted but could not run because this shell did not have
`AKS_DATABASE_URL` configured. The tests use their guarded test database and
did exercise the migration. Staging and production were not accessible during
this implementation, so release sign-off still requires the ordered rollout
and staging smoke checks above, plus an operator review of the backfill and
revocation counts. Do not interpret local verification as evidence that the
migration has been applied to a deployed database or that the application has
been deployed.
