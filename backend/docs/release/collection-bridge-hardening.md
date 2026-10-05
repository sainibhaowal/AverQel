# Collection Bridge hardening and release boundary

This document is the release checklist for the shared collection chat and
collection-scoped RAG surface. It intentionally distinguishes implemented
controls from controls that require a separate security protocol or deployment
dependency; the latter must not be described as WhatsApp/Signal-equivalent.

## Implemented in this hardening pass

- Collection WebSocket authentication and collection membership authorization
  happen before the socket is registered or presence is published.
- WebSocket message mutations resolve messages by both `collection_id` and
  message ID. Cross-collection mutation tests cover reactions.
- Client message IDs are scoped to `(collection_id, user_id)` and protected by
  a database uniqueness constraint for safe retry/idempotency.
- Message content is capped at 4,096 characters. Collection media is bounded
  by the server upload limit, not only by the browser.
- Collection WebSocket messages are rate limited and per-user connection
  limits are enforced within each API process. Heartbeat frames are supported.
- Media references are checked against the collection tenant prefix. Message,
  expiry, collection-clear, and collection-delete paths enqueue durable storage
  cleanup jobs. New uploads have a server-side ownership/lifecycle record, MIME
  validation, and a scheduled orphan sweep.
- Chat history and collection documents use bounded cursor pagination.
- Collection live events are written to a bounded Redis Stream and can be
  replayed after reconnect; REST history remains the source of truth if the
  stream cursor has expired.
- Browser text messages that cannot be sent are stored in an IndexedDB pending
  queue with exponential retry state.
- Redis-backed connection counters enforce the per-user WebSocket limit across
  API processes, with a local fallback when Redis is unavailable.
- Query requests accept `filters.collection_id`; the backend resolves the
  complete authorized document-ID scope server-side, instead of trusting a
  client-provided list or a first-page-only list.
- Chat receipts now include a device identity, while legacy rows are migrated
  to a safe `legacy` device. Device registration and revocation are exposed
  through authenticated tenant-scoped endpoints.
- Membership changes advance a collection security epoch and create an
  in-app security-change notification for remaining members. This is an
  auditable boundary, not a claim that the legacy shared key was rotated.
- Members can block another collection member and report a message. The
  server rejects new chat messages for blocked participants; the existing
  WebSocket rate limit remains the spam backstop.
- Web Push subscription metadata can be registered with the browser auth
  secret encrypted at rest. Notifications are also written to a durable push
  outbox and drained by the Celery `collections.dispatch_push_outbox` worker
  using `pywebpush` with bounded retries. Delivery remains disabled until the
  deployment supplies VAPID credentials.

## Collection report moderation workflow

The moderation console is restricted in the dashboard layout to admin roles;
the API independently requires `admin:collections:read` or
`admin:collections:write` and filters every report/history query by the
authenticated tenant. Collection members can submit reports, but only tenant
admins receive moderation notifications and can review or change report state.
Notifications contain no report details and link to the specific report.

The reports endpoint keeps its existing JSON array response and adds bounded
`limit`/`offset` pagination with `X-Total-Count`, `X-Has-More`, and
`X-Page-Offset` headers. It also supports `report_id` for notification deep
links. `GET /api/v1/collections/admin/security/reports/{report_id}/history`
returns paginated, append-only report actions. Status updates enforce the
`open`/`reviewing` to terminal (`resolved`/`dismissed`) lifecycle; terminal
reports can only be reopened or left in their current state. Internal notes are
separate audit events and never overwrite the submitter's report details.
The moderation API returns report metadata and an optional message reference;
it does not return the referenced chat message body. This is an API response
boundary, not proof that chat encryption hides content from the server.
Report submission is capped at 10 per user per collection per five minutes by
default (`AKS_COLLECTION_REPORTS_PER_USER_PER_5_MINUTES`), using the existing
Redis-backed limiter and its bounded in-memory fallback.

Migration `20261012_0012_collection_moderation_audit` creates the tenant-scoped
audit table, ties each event to a report with a tenant-matching composite
foreign key, and protects direct updates/deletes with a database trigger. The
trigger permits the database's account-erasure nulling and parent-record
cascades so existing account and collection deletion workflows continue to
work. Existing reports receive a `history_baseline` marker; previous moderator
actions cannot be reconstructed. Message bodies are not included in the
moderation response schema. The current collection encryption design does not
provide a server-blind key boundary; see
[`../library/10-collection-chat-encryption.md`](../library/10-collection-chat-encryption.md).

Run the focused verification from `backend/`:

```bash
.venv/bin/pytest -q tests/integration/test_collection_moderation_admin.py
.venv/bin/ruff check app/documents/api/collection_security.py \
  app/documents/models/collection_security.py \
  app/documents/schemas/collection_security.py \
  app/system/services/user_notifications.py \
  alembic/versions/20261012_0012_collection_moderation_audit.py
.venv/bin/alembic heads
```

The browser page tests live at
`frontend/tests/collection-moderation-page.test.tsx`. Apply migration
`20261012_0012` through the ordered Alembic release procedure before deploying
the backend code; the disposable test database is not evidence that a target
environment has been migrated.

## Added account-session and moderation controls

New access tokens carry a revocable linked-session identifier. Refresh-token
families and access tokens can now be revoked per account session without
revoking every other device. The routes are:

- `GET /api/v1/auth/sessions`
- `DELETE /api/v1/auth/sessions/{session_id}`
- `GET /api/v1/collections/security/push-config`
- `GET /api/v1/collections/admin/security/reports`
- `POST /api/v1/collections/admin/security/reports/{report_id}`
- `GET /api/v1/collections/{collection_id}/security/spam-score/{user_id}`

## Verification

Run from `backend/`:

```bash
.venv/bin/pytest -q \
  tests/unit/test_collection_chat_hardening.py \
  tests/unit/test_collection_security_controls.py \
  tests/integration/test_collection_chat_hardening.py \
  tests/integration/test_auth_flow.py
.venv/bin/ruff check app/documents app/query \
  alembic/versions/20261012_0001_collection_chat_hardening.py \
  alembic/versions/20261012_0002_collection_chat_media_registry.py \
  alembic/versions/20261012_0003_collection_security_controls.py \
  alembic/versions/20261012_0004_collection_security_epoch.py
```

The browser collection, query, and streaming tests and the frontend TypeScript
check must also be run from `frontend/` before deployment.

## Required deployment step

The ordered Alembic chain through `20261012_0012_collection_moderation_audit`
must be applied to the target database before deploying the API or workers
that use these models:

```bash
alembic upgrade head
```

The command requires a reachable production database and the normal production
configuration. Do not source a malformed local environment file in a shell;
inject validated variables through the deployment secret manager.

## Explicit security boundary / remaining work

The current collection chat still uses the existing collection shared-key
client encryption. It is **not** an audited Signal/libsignal protocol and does
not provide per-device forward secrecy. The following are separate release
projects, not silently implied by this pass:

- an audited per-device Signal/libsignal protocol, membership key rotation,
  and forward secrecy. The device registry and security epoch do not replace
  this protocol;
- true linked-device cryptographic session management and recovery. Account
  sessions are now revocable, but that is not cryptographic forward secrecy;
- browser subscription activation and deployment configuration. The durable
  outbox and isolated `collection_push` worker are implemented, but production must
  configure `AKS_WEB_PUSH_VAPID_PRIVATE_KEY`,
  `AKS_WEB_PUSH_VAPID_PUBLIC_KEY`, and `AKS_WEB_PUSH_SUBJECT`, then register
  subscriptions from the frontend. Authenticated browser-provider delivery
  still requires a real browser subscription test in the target deployment;

The media registry and orphan sweep are implemented, but storage cleanup still
depends on the maintenance worker running.

Until those items are implemented, product and documentation must not claim
zero-knowledge storage, Signal-level security, or WhatsApp-equivalent device
security for collection chat. Collection documents remain server-readable for
preview, OCR, indexing, and RAG.
