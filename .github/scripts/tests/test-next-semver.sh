#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
script="$repo_root/.github/scripts/next-semver.sh"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/averqel-semver-test.XXXXXX")"
trap 'rm -rf -- "$temp_root"' EXIT

repo=""

new_repo() {
  local name="$1"
  repo="$temp_root/$name"
  mkdir -p "$repo"
  git -C "$repo" init --quiet
  git -C "$repo" config user.name "AverQel SemVer Test"
  git -C "$repo" config user.email "semver-test@example.invalid"
  printf 'baseline\n' > "$repo/fixture.txt"
  git -C "$repo" add fixture.txt
  git -C "$repo" commit --quiet -m "chore: test baseline"
  git -C "$repo" tag v1.2.13
}

add_commit() {
  local subject="$1"
  local body="${2:-}"
  printf '%s\n%s\n' "$subject" "$(git -C "$repo" rev-parse HEAD)" > "$repo/fixture.txt"
  git -C "$repo" add fixture.txt
  if [[ -n "$body" ]]; then
    git -C "$repo" commit --quiet -m "$subject" -m "$body"
  else
    git -C "$repo" commit --quiet -m "$subject"
  fi
}

expect_version() {
  local expected="$1"
  local actual
  actual="$(cd "$repo" && "$script" HEAD v1.2.13)"
  if [[ "$actual" != "$expected" ]]; then
    echo "Expected $expected, got $actual" >&2
    exit 1
  fi
}

expect_auto_version() {
  local expected="$1"
  local actual
  actual="$(cd "$repo" && "$script" HEAD)"
  if [[ "$actual" != "$expected" ]]; then
    echo "Expected automatic version $expected, got $actual" >&2
    exit 1
  fi
}

new_repo fix
add_commit "fix(auth): handle expired sessions"
expect_version "v1.2.14"

new_repo feature
add_commit "feat(desktop): add workspace switcher"
expect_version "v1.3.0"

new_repo highest_level
add_commit "fix(api): handle missing records"
add_commit "feat(query): add saved filters"
add_commit "feat(desktop): add local workspace support"
expect_version "v1.3.0"

new_repo breaking_header
add_commit "feat(api)!: remove the legacy endpoint"
expect_version "v2.0.0"

new_repo breaking_footer
add_commit "fix(auth): rotate session credentials" $'Preserve compatibility details.\n\nBREAKING CHANGE: old session tokens are no longer accepted.'
expect_version "v2.0.0"

new_repo performance
add_commit "perf(search): reduce query latency"
expect_version "v1.2.14"

new_repo revert
add_commit "revert: restore previous navigation behavior"
expect_version "v1.2.14"

new_repo no_release
add_commit "docs: clarify local setup"
if output="$(cd "$repo" && "$script" HEAD v1.2.13 2>&1)"; then
  echo "Expected docs-only history to require an explicit release version." >&2
  exit 1
fi
if [[ "$output" != *"No release-worthy Conventional Commit"* ]]; then
  echo "Expected a clear no-release message; got: $output" >&2
  exit 1
fi

new_repo automatic_latest_tag
add_commit "feat(query): add saved filters"
expect_auto_version "v1.3.0"

echo "SemVer regression checks passed (9 cases)."
