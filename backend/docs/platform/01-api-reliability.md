# 01. API reliability settings

The API process must not be run as a single event loop in a deployment that
serves DeepSpace streams and ordinary dashboard requests at the same time.
The compose files therefore start two Uvicorn workers by default.

Available environment settings:

- `AKS_API_WORKERS`: Uvicorn worker processes, from 1 to 16. Keep this at 2 or
  higher for production. Use 1 only when a local Electron client actively uses
  the process-local client-owned storage proxy.
- `AKS_API_LIMIT_CONCURRENCY`: maximum concurrent connections/tasks accepted
  by each worker. Excess load receives a bounded server response instead of
  waiting without limit. Defaults are 100 for development and 200 for
  production.
- `AKS_API_KEEP_ALIVE_SECONDS`: idle HTTP keep-alive duration. Defaults to 5.
- `AKS_DATABASE_POOL_SIZE` / `AKS_DATABASE_MAX_OVERFLOW`: database connections
  available to each process. Production defaults are 8 + 4, deliberately
  bounded so the API, worker, and scheduler cannot exhaust PostgreSQL's
  connection budget together.
- `AKS_DATABASE_POOL_TIMEOUT_SECONDS`: maximum wait for a database connection.
  Defaults to 4 seconds, so pool exhaustion returns a traceable 503 rather
  than becoming the browser's 30-second timeout.
- Recognized PostgreSQL transaction conflicts (`lock_timeout`, deadlocks, and
  serialization failures) return the same retryable `SERVICE_OVERLOAD` 503
  with `Retry-After`. Other database errors remain server errors and are not
  treated as transient.
- `AKS_DATABASE_STATEMENT_TIMEOUT_SECONDS` / `AKS_DATABASE_LOCK_TIMEOUT_SECONDS`:
  per-request PostgreSQL limits (15 and 3 seconds by default). They prevent a
  blocked statement or row lock from monopolising request workers.

The browser retries `SERVICE_OVERLOAD` at most twice for `GET` and `HEAD`
requests, following a short `Retry-After`. It never automatically replays a
write. Keep read endpoints free of unconditional row locks and recovery writes;
queue recovery checks first for the exact persisted failure state before
locking a conversation.

DeepSpace conversations can use the authenticated client storage proxy. When
the channel is connected, conversation listing and creation use that client,
and note edits and document-text appends use the same store through
`db.chats.update_conversation` and `db.chats.append_conversation_content` (with
`db.chats.get_conversation` used to safely restore older drafts before appends). The
server keeps only its existing metadata mirror; it does not report a note save
from a write to that mirror. A proxy write that times out or fails returns
`STORAGE_UNAVAILABLE` (503), so the editor can retain its local recovery
draft and retry. It must not silently fall back to writing note content to a
different store. If a legacy server-side copy is newer than the client copy,
the conversation list exposes that recovery copy. Before
an append restores it, the client checks that the note has not changed since
the recovery read. The body is removed from the server mirror only after the
client confirms a subsequent write.

DeepSpace message history reads also use the authenticated client storage proxy.
That read has a five-second RPC budget; when the client tab is suspended or
does not answer, the API falls back to the tenant-scoped server history instead
of holding the browser request for the proxy's general 30-second timeout.

`QueryService.execute` is synchronous because it uses the synchronous database
session and retrieval pipeline. The HTTP endpoint dispatches that work to the
framework worker pool so provider/database latency cannot block the async event
loop. Provider model refresh is also guarded per process and fails fast with a
cached-model fallback when another refresh is active. OpenAI-compatible model
listing uses the provider's configured timeout, bounded to 1–30 seconds. If
the provider exceeds that budget, refresh returns HTTP 504 with
`PROVIDER_TEST_FAILED` and leaves the last successfully cached catalog
available. The timeout is reported as a provider refresh failure so callers do
not mistake old cached rows for a successful refresh.

The dashboard's full overview and the query workspace's
`GET /api/v1/dashboard/query-stats` snapshot resolve provider metadata in
read-only audit mode. The query snapshot includes only workspace totals,
document status counts, and the chat/embedding runtime indicators; it skips
recent documents, collections, activity, and trend aggregation. Both dashboard
reads use cached provider metadata and do not refresh provider models or write
selection audit events. Provider selection for actual model requests retains
its audit events. Only the explicit
`POST /providers/{provider_id}/models/refresh` route contacts a provider and
updates its model cache.

The notification bell uses the composite
`collection_notifications(recipient_user_id, created_at DESC, id DESC)` index.
The corresponding Alembic migration creates it concurrently, so applying an
upgrade does not block an existing notification feed.

Long-lived MCP notification leases commit their initial metadata read before
opening the remote session. This keeps the worker from retaining an idle
database transaction during its 110-second network lease.

After changing these settings, validate and restart only the API service:

```bash
cd /opt/averqel/backend
docker compose --env-file .env.vps -f docker-compose.prod.yml config >/dev/null
docker compose --env-file .env.vps -f docker-compose.prod.yml up -d --build --no-deps api
docker compose --env-file .env.vps -f docker-compose.prod.yml ps api
curl -fsS https://averqel.com/api/v1/health/live
```

The public gateway remains independent. Do not start the removed production
Caddy service from `docker-compose.prod.yml`; the gateway owns ports 80 and
443.

## VPS deployment readiness and availability

The manual VPS workflow builds and publishes images for one `main` commit,
rechecks that `main` has not advanced before SSH deployment, and pulls those
images by the same commit SHA. Production Compose waits for the API and
frontend health checks. Orphan service cleanup and unused AverQel image cleanup
run only after internal and public health checks succeed. The workflow does
not run Docker system, builder, image, or volume prune commands; persistent
PostgreSQL, Redis, MinIO, and runtime data are outside image cleanup.

The current app update still uses fixed-name Compose containers and therefore
replaces the old API/frontend before the post-deploy public checks finish. It
can detect failure and attempt image rollback, but it cannot guarantee that
every request avoids interruption. True blue/green deployment requires the
separately managed Caddy gateway to route to a ready second API/frontend slot,
then switch traffic and drain the old slot. Database migrations must also be
backward-compatible while both API versions are running. Do not describe the
current deployment as zero-downtime until both controls are implemented and
verified against the production gateway.

Before SSH deployment, the workflow starts the built frontend image in an
isolated container and requires its homepage to return HTTP 2xx. If production
readiness fails, the workflow reports the frontend container state and recent
health-probe status/error before attempting rollback. It reports rollback
health separately; a failed rollback means the previous service was not
restored and requires operator recovery. These checks improve detection and
diagnosis but do not preserve traffic during the fixed-name container swap.
