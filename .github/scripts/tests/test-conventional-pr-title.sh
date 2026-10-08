#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
script="$repo_root/.github/scripts/validate-conventional-pr-title.sh"

valid_titles=(
  'feat(desktop): add workspace switcher'
  'fix: prevent startup crash'
  'feat(api)!: remove the legacy endpoint'
  'docs(release): explain manual version overrides'
  'fix(NeoSIS runtime): recover local sessions'
)

invalid_titles=(
  ''
  'Update release workflow'
  'Feat: add a feature'
  'fix: '
  'fix(auth) handle expired sessions'
  ': missing type'
)

for title in "${valid_titles[@]}"; do
  if ! bash "$script" "$title" >/dev/null; then
    printf 'Expected valid Conventional Commit PR title: %q\n' "$title" >&2
    exit 1
  fi
done

for title in "${invalid_titles[@]}"; do
  if bash "$script" "$title" >/dev/null 2>&1; then
    printf 'Expected invalid Conventional Commit PR title to fail: %q\n' "$title" >&2
    exit 1
  fi
done

printf 'Conventional Commit PR title checks passed (%d valid, %d invalid).\n' \
  "${#valid_titles[@]}" "${#invalid_titles[@]}"
