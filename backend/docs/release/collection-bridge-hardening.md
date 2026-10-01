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
  secret encrypted at rest. Actual VAPID delivery remains disabled until the
  deployment supplies a reviewed Web Push worker/provider.

## Verification

Run from `backend/`:

```bash
.venv/bin/pytest -q \
  tests/unit/test_collection_chat_hardening.py \
  tests/unit/test_collection_security_controls.py \
  tests/integration/test_collection_chat_hardening.py
.venv/bin/ruff check app/documents app/query \
  alembic/versions/20261012_0001_collection_chat_hardening.py \
  alembic/versions/20261012_0002_collection_chat_media_registry.py \
  alembic/versions/20261012_0003_collection_security_controls.py \
  alembic/versions/20261012_0004_collection_security_epoch.py
```

The browser collection, query, and streaming tests and the frontend TypeScript
check must also be run from `frontend/` before deployment.

## Required deployment step

The migrations `20261012_0001_collection_chat_hardening` through
`20261012_0004_collection_security_epoch` must be applied to the
target database before an API or worker using these models is deployed:

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
- true linked-device cryptographic session management and recovery;
- VAPID/Web Push delivery and provider/worker retry telemetry. Subscription
  registration is implemented, but it intentionally does not pretend to send
  push notifications without deployment credentials and a reviewed worker;
- server-side spam scoring, report moderation workflow, and admin case UI.
  Block/report enforcement and audit records are implemented.

The media registry and orphan sweep are implemented, but storage cleanup still
depends on the maintenance worker running.

Until those items are implemented, product and documentation must not claim
zero-knowledge storage, Signal-level security, or WhatsApp-equivalent device
security for collection chat. Collection documents remain server-readable for
preview, OCR, indexing, and RAG.
