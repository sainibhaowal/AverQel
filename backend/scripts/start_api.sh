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

# The client-owned Tauri workspace proxy is process-local. Keep the default
# local deployment on one worker so the terminal websocket and agent stream
# share the same proxy registry. Deployments that use a distributed proxy can
# opt into multiple workers explicitly with AKS_API_WORKERS.
API_WORKERS="${AKS_API_WORKERS:-1}"
exec uvicorn app.main:app --host 0.0.0.0 --port 1000 --workers "${API_WORKERS}"
