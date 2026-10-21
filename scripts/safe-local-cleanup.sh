#!/usr/bin/env bash
# Safely reclaim a small set of regenerable caches and stale test temp files.
# This script deliberately does not use docker system prune or delete app caches.

set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly TMP_ROOT="/tmp"
readonly UID_NUM="$(id -u)"
readonly STALE_MINUTES=$((7 * 24 * 60))

APPLY=0
EMPTY_TRASH=0
TMP_CANDIDATES=()
TMP_SKIPPED=0

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME                  Show disk usage and a dry-run cleanup plan.
  $SCRIPT_NAME --apply          Interactively prune safe, regenerable caches.
  $SCRIPT_NAME --apply --empty-trash
                                Also empty this user's Trash after a second
                                explicit confirmation.

The cleanup is intentionally limited to:
  * pnpm's unreferenced global package-store content;
  * dangling build cache on a local Docker engine, older than 7 days;
  * old, user-owned /tmp/autopsy-* test fixtures, a stale /tmp/.pnpm-store,
    and Compose build metadata files, only when no process appears to use them.

It never removes project files, installed node_modules, Docker images,
containers, networks, volumes, databases, application state, or general
browser/model/system caches. It does not use sudo. Trash is untouched unless
--empty-trash is explicitly supplied.

Pruned package/build cache may need to be downloaded or rebuilt later.

Run from any directory. Review the plan first; --apply requires a terminal
and asks you to type CLEAN. There is no non-interactive confirmation bypass.
EOF
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --apply)
      APPLY=1
      ;;
    --empty-trash)
      EMPTY_TRASH=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1 (use --help)."
      ;;
  esac
  shift
done

if ((EMPTY_TRASH && ! APPLY)); then
  die "--empty-trash requires --apply."
fi
if ((EUID == 0)); then
  die "Run as your regular user, not with sudo or as root."
fi
if ((APPLY)) && [[ ! -t 0 || ! -t 1 ]]; then
  die "--apply requires an interactive terminal; review the dry run first."
fi

human_size() {
  du -sh -- "$1" 2>/dev/null | awk 'NR == 1 { print $1 }'
}

is_cwd_below() {
  local candidate="$1" proc cwd
  for proc in /proc/[0-9]*/cwd; do
    [[ -e "$proc" ]] || continue
    cwd="$(readlink -- "$proc" 2>/dev/null || true)"
    [[ "$cwd" == "$candidate" || "$cwd" == "$candidate/"* ]] && return 0
  done
  return 1
}

is_open() {
  local candidate="$1"
  if is_cwd_below "$candidate"; then
    return 0
  fi
  if [[ -d "$candidate" ]]; then
    if command -v lsof >/dev/null 2>&1; then
      lsof +D "$candidate" >/dev/null 2>&1 && return 0
      return 1
    fi
    # If recursive open-file inspection is unavailable, do not delete a dir.
    return 0
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -s -- "$candidate" 2>/dev/null
    return $?
  fi
  # If open-file inspection is unavailable, preserve the candidate.
  return 0
}

has_nested_mount() {
  local candidate="$1" target
  # Without findmnt, do not recursively remove a temp directory.
  command -v findmnt >/dev/null 2>&1 || return 0
  while IFS= read -r target; do
    [[ "$target" == "$candidate" || "$target" == "$candidate/"* ]] && return 0
  done < <(findmnt -rn -o TARGET 2>/dev/null)
  return 1
}

docker_is_local() {
  local context endpoint
  if [[ -n "${DOCKER_CONTEXT:-}" ]]; then
    context="$DOCKER_CONTEXT"
  elif [[ -n "${DOCKER_HOST:-}" ]]; then
    [[ "$DOCKER_HOST" == unix://* ]]
    return $?
  else
    context="$(docker context show 2>/dev/null || true)"
  fi
  [[ -n "$context" ]] || return 1
  endpoint="$(docker context inspect "$context" \
    --format '{{(index .Endpoints "docker").Host}}' 2>/dev/null || true)"
  [[ "$endpoint" == unix://* ]]
}

is_safe_temp_candidate() {
  local candidate="$1" canonical owner
  [[ -e "$candidate" && ! -L "$candidate" ]] || return 1
  canonical="$(realpath -e -- "$candidate" 2>/dev/null || true)"
  owner="$(stat -c '%u' -- "$candidate" 2>/dev/null || true)"
  [[ "$owner" == "$UID_NUM" ]] || return 1
  case "$canonical" in
    /tmp/.tmp-compose-build-metadataFile-*) [[ -f "$candidate" ]] || return 1 ;;
    /tmp/autopsy-*|/tmp/.pnpm-store) [[ -d "$candidate" ]] || return 1 ;;
    *) return 1 ;;
  esac
  find "$candidate" -maxdepth 0 -mmin "+$STALE_MINUTES" \
    -print -quit 2>/dev/null | grep -q . || return 1
  if [[ -d "$candidate" ]]; then
    # Do not recursively remove mixed-owner, symlinked, mounted, or fresh trees.
    find "$candidate" -xdev \( ! -user "$UID_NUM" -o -type l \) \
      -print -quit 2>/dev/null | grep -q . && return 1
    find "$candidate" -xdev -type f -mmin "-$STALE_MINUTES" \
      -print -quit 2>/dev/null | grep -q . && return 1
    has_nested_mount "$candidate" && return 1
  fi
  is_open "$candidate" && return 1
  return 0
}

discover_tmp_candidates() {
  local candidate
  local -a found=()

  while IFS= read -r -d '' candidate; do
    found+=("$candidate")
  done < <(
    find "$TMP_ROOT" -mindepth 1 -maxdepth 1 -type f \
      -user "$UID_NUM" -mmin "+$STALE_MINUTES" \
      -name '.tmp-compose-build-metadataFile-*' -print0 2>/dev/null
    find "$TMP_ROOT" -mindepth 1 -maxdepth 1 -type d \
      -user "$UID_NUM" -mmin "+$STALE_MINUTES" \
      \( -name 'autopsy-*' -o -name '.pnpm-store' \) -print0 2>/dev/null
  )

  for candidate in "${found[@]}"; do
    if ! is_safe_temp_candidate "$candidate"; then
      ((TMP_SKIPPED += 1))
      continue
    fi
    TMP_CANDIDATES+=("$candidate")
  done
}

process_running() {
  local pattern="$1" proc pid command_line
  for proc in /proc/[0-9]*/cmdline; do
    pid="${proc#/proc/}"
    pid="${pid%/cmdline}"
    [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
    [[ -r "$proc" ]] || continue
    command_line="$(tr '\0' ' ' < "$proc" 2>/dev/null || true)"
    [[ "$command_line" == *"$SCRIPT_NAME"* ]] && continue
    [[ "$command_line" =~ $pattern ]] || continue
    return 0
  done
  return 1
}

show_status() {
  printf '\nDisk space:\n'
  df -h / "$HOME"

  if command -v docker >/dev/null 2>&1; then
    if docker_is_local; then
      printf '\nLocal Docker storage summary (read-only):\n'
      docker system df 2>&1 || printf 'Docker storage summary unavailable.\n'
    else
      printf '\nDocker cleanup skipped in the report: the configured context is not a local Unix socket.\n'
    fi
  else
    printf '\nDocker CLI not found; Docker cleanup will be skipped.\n'
  fi

  if command -v pnpm >/dev/null 2>&1; then
    local store
    store="$(pnpm store path 2>/dev/null || true)"
    if [[ -n "$store" && -d "$store" ]]; then
      printf '\npnpm store: %s (%s)\n' "$store" "$(human_size "$store")"
    else
      printf '\npnpm store path unavailable.\n'
    fi
  else
    printf '\npnpm not found; pnpm store cleanup will be skipped.\n'
  fi

  printf '\nOld known temporary artifacts eligible for cleanup: %s\n' "${#TMP_CANDIDATES[@]}"
  local item shown=0
  for item in "${TMP_CANDIDATES[@]}"; do
    if ((shown < 20)); then
      printf '  %s  %s\n' "$(human_size "$item")" "$item"
    fi
    ((shown += 1))
  done
  if ((shown > 20)); then
    printf '  ... and %d more matching paths\n' "$((shown - 20))"
  fi
  if ((TMP_SKIPPED)); then
    printf 'Skipped %d matching temp path(s): recent, open, mixed-owner, or not safely inspectable.\n' "$TMP_SKIPPED"
  fi

  if ((EMPTY_TRASH)); then
    printf "\nTrash: gio will empty the current user's Trash only after a second confirmation.\n"
  else
    printf '\nTrash: unchanged. Add --empty-trash to include it.\n'
  fi
}

discover_tmp_candidates
show_status

if ((!APPLY)); then
  printf '\nDry run only. No files or caches were changed.\n'
  printf 'To apply the listed safe cleanup, run: %s --apply\n' "$SCRIPT_NAME"
  exit 0
fi

printf '\nThis will prune only the regenerable caches and exact old temp paths listed above.\n'
printf 'It will not remove project data, app data, Docker images/containers/volumes, or databases.\n'
read -r -p 'Type CLEAN to continue: ' confirmation
[[ "$confirmation" == CLEAN ]] || { printf 'Cancelled; nothing changed.\n'; exit 0; }

if command -v pnpm >/dev/null 2>&1; then
  if process_running '(^|/)(pnpm|npm|yarn)([^[:space:]]*)[[:space:]]'; then
    printf '\nSkipping pnpm store prune: a package-manager process appears to be running.\n'
  else
    printf '\nPruning only unreferenced packages from the pnpm store...\n'
    pnpm store prune
  fi
fi

if command -v docker >/dev/null 2>&1; then
  if ! docker_is_local; then
    printf '\nSkipping Docker build-cache prune: the configured context is not a local Unix socket.\n'
  elif process_running '(^|/)(docker|docker-compose)[[:space:]].*(build|compose.*build)'; then
    printf '\nSkipping Docker build-cache prune: a Docker build appears to be running.\n'
  else
    printf '\nPruning dangling Docker build cache older than 7 days...\n'
    docker builder prune --filter 'until=168h' --force
  fi
fi

if ((${#TMP_CANDIDATES[@]})); then
  printf '\nRemoving %d stale, user-owned, known test/Compose temp path(s)...\n' "${#TMP_CANDIDATES[@]}"
  local_item=''
  for local_item in "${TMP_CANDIDATES[@]}"; do
    # Re-check immediately before removal to avoid racing a newly started process.
    if ! is_safe_temp_candidate "$local_item"; then
      printf '  Preserved now-in-use path: %s\n' "$local_item"
      continue
    fi
    rm -rf -- "$local_item"
  done
fi

if ((EMPTY_TRASH)); then
  printf '\nEmptying Trash is irreversible. This is separate from the cache cleanup.\n'
  read -r -p "Type EMPTY TRASH to permanently empty this user's Trash: " trash_confirmation
  if [[ "$trash_confirmation" == 'EMPTY TRASH' ]]; then
    if command -v gio >/dev/null 2>&1; then
      gio trash --empty
      printf 'Trash emptied.\n'
    else
      printf 'gio is unavailable; Trash was not changed.\n'
    fi
  else
    printf 'Trash preserved.\n'
  fi
fi

printf '\nFinal disk space:\n'
df -h / "$HOME"
if command -v docker >/dev/null 2>&1 && docker_is_local; then
  printf '\nFinal Docker storage summary:\n'
  docker system df 2>&1 || true
fi
printf '\nCleanup complete. Project files and running containers were not targeted.\n'
