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

# Keep a bounded queue set: priority controls scheduling and tenants are
# deterministically assigned to bounded shards for fairness.
TENANT_QUEUE_SHARDS="${AKS_DEEPSPACE_DURABLE_TENANT_QUEUE_SHARDS:-8}"
if ! [[ "${TENANT_QUEUE_SHARDS}" =~ ^[1-9][0-9]*$ ]]; then
  TENANT_QUEUE_SHARDS=8
fi
DEEPSPACE_QUEUES="deepspace_runtime.recovery,deepspace_runtime.supervision"
for priority in high normal low; do
  for shard in $(seq 0 $((TENANT_QUEUE_SHARDS - 1))); do
    DEEPSPACE_QUEUES="${DEEPSPACE_QUEUES},deepspace_runtime.${priority}.tenant${shard}"
  done
done

exec celery -A app.worker.celery_app.celery_app worker --loglevel=INFO -Q "ingestion_heavy,ingestion_light,maintenance,${DEEPSPACE_QUEUES}" --concurrency="${AKS_WORKER_CONCURRENCY}"
