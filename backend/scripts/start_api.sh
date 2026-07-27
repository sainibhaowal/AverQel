#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AKS_DATABASE_URL:-}" ]]; then
  echo "AKS_DATABASE_URL is required" >&2
  exit 1
fi

if [[ "${AKS_ENV:-development}" == "production" ]]; then
  if [[ "${AKS_JWT_SECRET:-}" == "change-me-please-use-env-secret-min-32-chars" ]]; then
    echo "Refusing to start with insecure production JWT secret" >&2
    exit 1
  fi
  if [[ "${AKS_REFRESH_TOKEN_HASH_SECRET:-}" == "change-me-refresh-hash-secret-min-32-chars" ]]; then
    echo "Refusing to start with insecure production refresh token hash secret" >&2
    exit 1
  fi
fi

# This checkout carries multiple Alembic heads in the live database state, so
# upgrade all heads explicitly instead of aborting on the ambiguous single-head
# target.
alembic upgrade heads

# Seed the integration catalog on every startup so a rebuilt database does not
# come up empty in the UI.
python scripts/seed_integrations.py

# Seed only code-reviewed, public remote MCP metadata. This does not contact
# vendors and does not create OAuth clients, credentials, or user connections.
python scripts/seed_mcp_catalog.py

# The HTTP API must have more than one process in production: a synchronous
# retrieval/provider path or a slow client stream must not monopolize the only
# event loop. The default compose deployments use two workers; set
# AKS_API_WORKERS=1 only for a local Tauri deployment that actively uses the
# optional process-local client-owned proxy registry. Production can be tuned
# explicitly with AKS_API_WORKERS.
if [[ -n "${AKS_API_WORKERS:-}" ]]; then
  API_WORKERS="${AKS_API_WORKERS}"
elif [[ "${AKS_ENV:-development}" == "production" ]]; then
  API_WORKERS="2"
else
  API_WORKERS="2"
fi

if ! [[ "${API_WORKERS}" =~ ^[1-9][0-9]*$ ]] || (( API_WORKERS > 16 )); then
  echo "AKS_API_WORKERS must be an integer from 1 to 16" >&2
  exit 1
fi

API_LIMIT_CONCURRENCY="${AKS_API_LIMIT_CONCURRENCY:-200}"
if ! [[ "${API_LIMIT_CONCURRENCY}" =~ ^[1-9][0-9]*$ ]]; then
  echo "AKS_API_LIMIT_CONCURRENCY must be a positive integer" >&2
  exit 1
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 1000 \
  --workers "${API_WORKERS}" \
  --limit-concurrency "${API_LIMIT_CONCURRENCY}" \
  --timeout-keep-alive "${AKS_API_KEEP_ALIVE_SECONDS:-5}"
