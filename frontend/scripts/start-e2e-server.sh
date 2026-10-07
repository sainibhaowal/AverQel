#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/averqel-e2e.XXXXXX")"
PROJECT_DIR="$TEMP_ROOT/frontend"
NEXT_PID=""
TEMP_PARENT="${TEMP_ROOT%/*}"
TEMP_NAME="${TEMP_ROOT##*/}"

# Playwright may force-kill its webServer shell if a run is interrupted. Keep
# a small detached janitor so that even that path kills the private Next
# process group and removes its temporary source snapshot.
setsid env -i PATH="$PATH" /bin/bash -s -- "$$" "$TEMP_PARENT" "$TEMP_NAME" \
  >/dev/null 2>&1 <<'WATCHDOG' &
parent_pid="$1"
temp_parent="$2"
temp_name="$3"
temp_root="$temp_parent/$temp_name"
cd /

while :; do
  parent_state="$(ps -o stat= -p "$parent_pid" 2>/dev/null || true)"
  parent_state="${parent_state//[[:space:]]/}"
  if [[ -z "$parent_state" || "$parent_state" == Z* ]]; then
    break
  fi
  sleep 0.25
done

if [[ -f "$temp_root/server-pgid" ]]; then
  server_pgid="$(cat "$temp_root/server-pgid" 2>/dev/null || true)"
  if [[ "$server_pgid" =~ ^[0-9]+$ ]]; then
    kill -TERM -- "-$server_pgid" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$server_pgid" 2>/dev/null || true
  fi
fi

if [[ "$temp_name" == averqel-e2e.* && -d "$temp_root" ]]; then
  rm -rf -- "$temp_root"
fi
WATCHDOG

process_is_running() {
  local process_state
  process_state="$(ps -o stat= -p "$1" 2>/dev/null || true)"
  process_state="${process_state//[[:space:]]/}"
  [[ -n "$process_state" && "$process_state" != Z* ]]
}

cleanup() {
  local status=$?
  local attempt
  trap - EXIT INT TERM
  if [[ -n "$NEXT_PID" ]]; then
    # Next spawns worker processes. Give it a private process group so a
    # cancelled Playwright run cannot leave those workers holding the temp
    # project open after this launcher exits.
    kill -TERM -- "-$NEXT_PID" 2>/dev/null || true
    for attempt in {1..20}; do
      if ! process_is_running "$NEXT_PID"; then
        break
      fi
      sleep 0.1
    done
    kill -KILL -- "-$NEXT_PID" 2>/dev/null || true
    while process_is_running "$NEXT_PID"; do
      sleep 0.1
    done
    wait "$NEXT_PID" 2>/dev/null || true
  fi
  rm -rf -- "$TEMP_ROOT"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$PROJECT_DIR" "$TEMP_ROOT/home"
tar -C "$FRONTEND_DIR" \
  --exclude='./.git' \
  --exclude='./node_modules' \
  --exclude='./.next' \
  --exclude='./.local' \
  --exclude='./.env*' \
  -cf - . | tar -C "$PROJECT_DIR" -xf -
ln -s "$FRONTEND_DIR/node_modules" "$PROJECT_DIR/node_modules"

cd "$PROJECT_DIR"
set +e
setsid env -i \
  PATH="$PATH" \
  HOME="$TEMP_ROOT/home" \
  NODE_ENV=development \
  NEXT_TELEMETRY_DISABLED=1 \
  PLAYWRIGHT_E2E=1 \
  NEXT_PUBLIC_API_URL=http://127.0.0.1:9/api/v1 \
  node "$PROJECT_DIR/node_modules/next/dist/bin/next" dev \
    --webpack \
    --hostname 127.0.0.1 \
    -p 3103 &
NEXT_PID=$!
printf '%s\n' "$NEXT_PID" > "$TEMP_ROOT/server-pgid"
while process_is_running "$NEXT_PID"; do
  sleep 0.1
done
wait "$NEXT_PID"
status=$?
set -e
exit "$status"
