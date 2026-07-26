#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AKS_REDIS_URL:-}" ]]; then
  echo "AKS_REDIS_URL is required" >&2
  exit 1
fi

if [[ -z "${AKS_DATABASE_URL:-}" ]]; then
  echo "AKS_DATABASE_URL is required" >&2
  exit 1
fi

AKS_WORKER_CONCURRENCY="${AKS_WORKER_CONCURRENCY:-4}"

exec celery -A app.platform.worker.celery_app.celery_app worker --loglevel=INFO -Q "ingestion_heavy,ingestion_light,maintenance" --concurrency="${AKS_WORKER_CONCURRENCY}"
