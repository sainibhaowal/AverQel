#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

DRY_RUN="false"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.vps"
MAX_RETRIES="30"
SLEEP_SECONDS="2"
BUILD_IMAGES="false"
VERIFY_BASE_URL=""

usage() {
  cat <<'EOF'
Usage: scripts/release_verify.sh [options]

Options:
  --dry-run                     Print verification commands only
  --compose-file <file>         Compose file to verify (default: docker-compose.prod.yml)
  --env-file <file>             Environment file to use (default: .env.vps)
  --base-url <url>              Public base URL to verify (default: AVERQEL_PUBLIC_ORIGIN)
  --max-retries <n>             HTTP readiness retries per endpoint (default: 30)
  --sleep-seconds <n>           Sleep between retries (default: 2)
  --build                       Build images during compose up
  -h, --help                    Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --compose-file)
      COMPOSE_FILE="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --base-url)
      VERIFY_BASE_URL="${2:-}"
      shift 2
      ;;
    --max-retries)
      MAX_RETRIES="${2:-}"
      shift 2
      ;;
    --sleep-seconds)
      SLEEP_SECONDS="${2:-}"
      shift 2
      ;;
    --build)
      BUILD_IMAGES="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

run_or_echo() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN: $*"
  else
    eval "$*"
  fi
}

curl_args=()

curl_request() {
  curl "${curl_args[@]}" "$@"
}

wait_for_http_ok() {
  local url="$1"
  local attempt=1
  while [[ "$attempt" -le "$MAX_RETRIES" ]]; do
    if curl_request "$url" >/dev/null; then
      return 0
    fi
    echo "Waiting for $url (attempt $attempt/$MAX_RETRIES)..."
    sleep "$SLEEP_SECONDS"
    attempt=$((attempt + 1))
  done
  echo "Release verify failed: endpoint not ready after retries: $url" >&2
  return 1
}

wait_for_http_code() {
  local url="$1"
  local expected_code="$2"
  local attempt=1
  while [[ "$attempt" -le "$MAX_RETRIES" ]]; do
    local status
    status="$(curl_request -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$status" == "$expected_code" ]]; then
      return 0
    fi
    echo "Waiting for $url to return $expected_code (attempt $attempt/$MAX_RETRIES, got ${status:-none})..."
    sleep "$SLEEP_SECONDS"
    attempt=$((attempt + 1))
  done
  echo "Release verify failed: endpoint did not return $expected_code after retries: $url" >&2
  return 1
}

read_env_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d '=' -f 2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

cd "$BACKEND_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

if [[ -z "$VERIFY_BASE_URL" ]]; then
  VERIFY_BASE_URL="$(read_env_value "AVERQEL_PUBLIC_ORIGIN")"
fi

if [[ -z "$VERIFY_BASE_URL" ]]; then
  VERIFY_BASE_URL="http://localhost"
fi

curl_args=(-fsS)
if [[ "$VERIFY_BASE_URL" == https://localhost* || "$VERIFY_BASE_URL" == https://127.0.0.1* ]]; then
  curl_args=(-k -fsS)
fi

RUFF_BIN="ruff"
BLACK_BIN="black"
PYTEST_BIN="pytest"
BANDIT_BIN="bandit"
PIP_AUDIT_BIN="pip-audit"
PIP_AUDIT_CMD='"$PIP_AUDIT_BIN" -s osv --disable-pip --no-deps -r requirements.txt && "$PIP_AUDIT_BIN" -s osv --disable-pip --no-deps -r requirements-dev.txt'

if [[ -x "$BACKEND_DIR/.venv/bin/ruff" ]]; then
  RUFF_BIN="$BACKEND_DIR/.venv/bin/ruff"
fi
if [[ -x "$BACKEND_DIR/.venv/bin/black" ]]; then
  BLACK_BIN="$BACKEND_DIR/.venv/bin/black"
fi
if [[ -x "$BACKEND_DIR/.venv/bin/pytest" ]]; then
  PYTEST_BIN="$BACKEND_DIR/.venv/bin/pytest"
fi
if [[ -x "$BACKEND_DIR/.venv/bin/bandit" ]]; then
  BANDIT_BIN="$BACKEND_DIR/.venv/bin/bandit"
fi
if [[ -x "$BACKEND_DIR/.venv/bin/pip-audit" ]]; then
  PIP_AUDIT_BIN="$BACKEND_DIR/.venv/bin/pip-audit"
  PIP_AUDIT_CMD='"$PIP_AUDIT_BIN" -s osv --disable-pip --no-deps -r requirements.txt && "$PIP_AUDIT_BIN" -s osv --disable-pip --no-deps -r requirements-dev.txt'
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN: $RUFF_BIN check app tests alembic scripts"
  echo "DRY RUN: $BLACK_BIN --check app tests alembic scripts"
  echo "DRY RUN: $PYTEST_BIN"
  echo "DRY RUN: $BANDIT_BIN -r app -q"
  eval "echo DRY RUN: $PIP_AUDIT_CMD"
else
  echo "Running Quality & Security Gates..."
  run_or_echo "\"$RUFF_BIN\" check app tests alembic scripts"
  run_or_echo "\"$BLACK_BIN\" --check app tests alembic scripts"
  run_or_echo "\"$PYTEST_BIN\""
  run_or_echo "\"$BANDIT_BIN\" -r app -q"
  run_or_echo "$PIP_AUDIT_CMD"
  echo "Gates passed successfully."
fi

if [[ "$BUILD_IMAGES" == "true" ]]; then
  run_or_echo "docker compose --env-file \"$ENV_FILE\" -f \"$COMPOSE_FILE\" up -d --build --remove-orphans"
else
  run_or_echo "docker compose --env-file \"$ENV_FILE\" -f \"$COMPOSE_FILE\" up -d --remove-orphans"
fi
run_or_echo "docker compose --env-file \"$ENV_FILE\" -f \"$COMPOSE_FILE\" ps"
if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN: curl ${curl_args[*]} $VERIFY_BASE_URL/api/v1/health/live"
  echo "DRY RUN: curl ${curl_args[*]} $VERIFY_BASE_URL/api/v1/health/ready"
  echo "DRY RUN: curl ${curl_args[*]} -o /dev/null -w '%{http_code}' $VERIFY_BASE_URL/api/v1/metrics"
else
  wait_for_http_ok "$VERIFY_BASE_URL/api/v1/health/live"
  wait_for_http_ok "$VERIFY_BASE_URL/api/v1/health/ready"
  wait_for_http_code "$VERIFY_BASE_URL/api/v1/metrics" "403"
fi

if [[ "$DRY_RUN" == "false" ]]; then
  login_payload='{"email":"nobody@example.com","password":"invalid"}'
  response="$(curl_request -X POST "$VERIFY_BASE_URL/api/v1/auth/login" -H 'Content-Type: application/json' -d "$login_payload")"
  python3 - <<'PY' "$response"
import json
import sys
payload = json.loads(sys.argv[1])
if "error" not in payload or "trace_id" not in payload:
    raise SystemExit("Release verify failed: standardized error schema missing")
PY
fi

echo "Release verification completed"
