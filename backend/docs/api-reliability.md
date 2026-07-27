# API reliability settings

The API process must not be run as a single event loop in a deployment that
serves DeepSpace streams and ordinary dashboard requests at the same time.
The compose files therefore start two Uvicorn workers by default.

Available environment settings:

- `AKS_API_WORKERS`: Uvicorn worker processes, from 1 to 16. Keep this at 2 or
  higher for production. Use 1 only when a local Tauri client actively uses
  the process-local client-owned storage proxy.
- `AKS_API_LIMIT_CONCURRENCY`: maximum concurrent connections/tasks accepted
  by each worker. Excess load receives a bounded server response instead of
  waiting without limit. Defaults are 100 for development and 200 for
  production.
- `AKS_API_KEEP_ALIVE_SECONDS`: idle HTTP keep-alive duration. Defaults to 5.

`QueryService.execute` is synchronous because it uses the synchronous database
session and retrieval pipeline. The HTTP endpoint dispatches that work to the
framework worker pool so provider/database latency cannot block the async event
loop. Provider model refresh is also guarded per process and fails fast with a
cached-model fallback when another refresh is active.

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
