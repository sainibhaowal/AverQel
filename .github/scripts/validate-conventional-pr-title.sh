#!/usr/bin/env bash
set -euo pipefail

title="${1:-}"
pattern='^[a-z][a-z0-9-]*(\([^()]+\))?!?:[[:space:]]+[^[:space:]].*$'

if [[ -z "$title" || ! "$title" =~ $pattern ]]; then
  cat >&2 <<'MESSAGE'
::error::PR title must use Conventional Commit format: <type>(optional-scope): <description>.
Examples: feat(desktop): add workspace switcher; fix(auth): handle expired sessions; feat(api)!: remove the legacy endpoint.
MESSAGE
  exit 1
fi

printf 'PR title follows Conventional Commit format: %s\n' "${title%%:*}: …"
