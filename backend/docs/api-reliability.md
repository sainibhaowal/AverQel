# API reliability settings

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
- `AKS_DATABASE_STATEMENT_TIMEOUT_SECONDS` / `AKS_DATABASE_LOCK_TIMEOUT_SECONDS`:
  per-request PostgreSQL limits (15 and 3 seconds by default). They prevent a
  blocked statement or row lock from monopolising request workers.

`QueryService.execute` is synchronous because it uses the synchronous database
session and retrieval pipeline. The HTTP endpoint dispatches that work to the
framework worker pool so provider/database latency cannot block the async event
loop. Provider model refresh is also guarded per process and fails fast with a
cached-model fallback when another refresh is active.

Ordinary provider selection and dashboard capability reads are side-effect free:
they use configured and cached metadata and never refresh provider models or
write the model cache. Only the explicit `POST /providers/{provider_id}/models/refresh`
route contacts the provider and updates that cache. This prevents page loads
from creating row-lock contention.

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
