#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FRONTEND_STATE_DIR="${AVERQEL_FRONTEND_STATE_DIR:-$FRONTEND_DIR/.local}"
RUNTIME_ENV_FILE="$FRONTEND_STATE_DIR/.env.local"

if [[ -f "$RUNTIME_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$RUNTIME_ENV_FILE"
  set +a
fi

exec bash -c "$1"
