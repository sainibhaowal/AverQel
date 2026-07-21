#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AKS_REDIS_URL:-}" ]]; then
  echo "AKS_REDIS_URL is required" >&2
  exit 1
fi

if [[ "${AKS_DEEPSPACE_PROACTIVE_DAEMON_ENABLED:-false}" == "true" ]]; then
  exec python -m app.deepspace.workers.daemon
fi

SCHEDULE_FILE="${AKS_CELERY_BEAT_SCHEDULE_FILE:-/state/backend/cache/celerybeat-schedule}"

SCHEDULE_DIR="$(dirname "${SCHEDULE_FILE}")"
if ! mkdir -p "${SCHEDULE_DIR}" 2>/dev/null || [[ ! -w "${SCHEDULE_DIR}" ]]; then
  SCHEDULE_DIR="/tmp/averqel-celerybeat"
  mkdir -p "${SCHEDULE_DIR}"
  SCHEDULE_FILE="${SCHEDULE_DIR}/celerybeat-schedule"
fi

exec celery -A app.platform.worker.celery_app.celery_app beat --loglevel=INFO --schedule "${SCHEDULE_FILE}"
