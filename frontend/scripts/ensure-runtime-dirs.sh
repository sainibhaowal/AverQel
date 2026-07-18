#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FRONTEND_STATE_DIR="${AVERQEL_FRONTEND_STATE_DIR:-$FRONTEND_DIR/.local}"

mkdir -p \
  "$FRONTEND_STATE_DIR/cache/vite" \
  "$FRONTEND_STATE_DIR/coverage" \
  "$FRONTEND_STATE_DIR/pnpm/store" \
  "$FRONTEND_STATE_DIR/pnpm/virtual-store" \
  "$FRONTEND_STATE_DIR/logs"
