#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
script="$repo_root/.github/scripts/next-semver.sh"
validator="$repo_root/.github/scripts/validate-release-version.sh"
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
  actual="$(cd "$repo" && "$script" HEAD "${2:-v1.2.13}")"
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
expect_version "v1.3.0"

new_repo breaking_footer
add_commit "fix(auth): rotate session credentials" $'Preserve compatibility details.\n\nBREAKING CHANGE: old session tokens are no longer accepted.'
expect_version "v1.3.0"

new_repo minor_limit
git -C "$repo" tag v1.99.99
add_commit "fix(api): preserve the v1 release line"
expect_version "v1.99.100" "v1.99.99"

new_repo breaking_minor_limit
git -C "$repo" tag v1.99.99
add_commit "fix(api)!: evolve the v1 contract"
expect_version "v1.100.0" "v1.99.99"

new_repo unsupported_major_tag
git -C "$repo" tag v2.0.0
if output="$(cd "$repo" && "$script" HEAD 2>&1)"; then
  echo "Expected a stable v2 tag to be rejected." >&2
  exit 1
fi
if [[ "$output" != *"outside AverQel's v1.x.x release line"* ]]; then
  echo "Expected a clear v1 release-line error; got: $output" >&2
  exit 1
fi

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

for version in v1.0.0 v1.100.1; do
  actual="$(bash "$validator" "$version")"
  [[ "$actual" == "$version" ]]
done

for version in v2.0.0 v0.9.4 v1.2 v01.2.3; do
  if bash "$validator" "$version" >/dev/null 2>&1; then
    echo "Expected non-v1 release version to be rejected: $version" >&2
    exit 1
  fi
done

echo "SemVer regression checks passed (18 cases)."
