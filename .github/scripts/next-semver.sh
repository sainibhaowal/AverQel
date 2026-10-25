#!/usr/bin/env bash
set -euo pipefail

HEAD_SHA="${1:-HEAD}"
BASE_TAG="${2:-}"

if [[ -n "$BASE_TAG" ]]; then
  [[ "$BASE_TAG" =~ ^v1\.[0-9]+\.[0-9]+$ ]] || {
    echo "Invalid base tag '$BASE_TAG'; AverQel releases are restricted to v1.x.x" >&2
    exit 2
  }
  git rev-parse --verify "$BASE_TAG^{commit}" >/dev/null || {
    echo "Base tag '$BASE_TAG' is not available locally" >&2
    exit 2
  }
  LAST_TAG="$BASE_TAG"
  BASE_VERSION="${LAST_TAG#v}"
  COMMIT_RANGE="$LAST_TAG..$HEAD_SHA"
else
  mapfile -t STABLE_TAGS < <(
    git for-each-ref --format='%(refname:strip=2)' refs/tags \
      | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
      | sort -V
  )

  if ((${#STABLE_TAGS[@]} > 0)); then
    LAST_TAG="${STABLE_TAGS[${#STABLE_TAGS[@]}-1]}"
    [[ "$LAST_TAG" =~ ^v1\.[0-9]+\.[0-9]+$ ]] || {
      echo "Latest stable tag '$LAST_TAG' is outside AverQel's v1.x.x release line" >&2
      exit 2
    }
    BASE_VERSION="${LAST_TAG#v}"
    COMMIT_RANGE="$LAST_TAG..$HEAD_SHA"
  else
    LAST_TAG=""
    BASE_VERSION="1.0.0"
    COMMIT_RANGE="$HEAD_SHA"
  fi
fi

COMMIT_SUBJECTS="$(git log "$COMMIT_RANGE" --format='%s')"
COMMIT_BODIES="$(git log "$COMMIT_RANGE" --format='%b')"
# GitHub squash merges often use a non-Conventional-Commit subject (for
# example, "merge: resolve conflicts") and put the PR's individual commit
# titles in a bulleted body. Include only bullet lines that are themselves
# valid Conventional Commit titles so free-form prose cannot cause a bump.
mapfile -t SQUASH_BODY_SUBJECTS < <(
  sed -nE \
    's/^[[:space:]]*[*-][[:space:]]+([[:alnum:]_-]+(\([^)]*\))?!?:[[:space:]]+.*)$/\1/p' \
    <<< "$COMMIT_BODIES"
)
RELEASE_COMMIT_SUBJECTS="$COMMIT_SUBJECTS"
if ((${#SQUASH_BODY_SUBJECTS[@]} > 0)); then
  RELEASE_COMMIT_SUBJECTS+=$'\n'"$(printf '%s\n' "${SQUASH_BODY_SUBJECTS[@]}")"
fi
IFS=. read -r MAJOR MINOR PATCH <<< "$BASE_VERSION"

if grep -Eq '^[[:alnum:]_-]+(\([^)]*\))?!:[[:space:]]' <<< "$RELEASE_COMMIT_SUBJECTS" \
  || grep -Eq '^[[:space:]]*([-*][[:space:]]+)?BREAKING[ -]CHANGE:' <<< "$COMMIT_BODIES"; then
  # AverQel remains on the v1 release line, including for breaking changes.
  MINOR=$((MINOR + 1))
  PATCH=0
elif grep -Eq '^feat(\([^)]*\))?:[[:space:]]' <<< "$RELEASE_COMMIT_SUBJECTS"; then
  MINOR=$((MINOR + 1))
  PATCH=0
elif grep -Eq '^(fix|perf|revert)(\([^)]*\))?:[[:space:]]' <<< "$RELEASE_COMMIT_SUBJECTS"; then
  PATCH=$((PATCH + 1))
else
  echo "::error::No release-worthy Conventional Commit found in commit subjects or squash-body bullets since ${LAST_TAG:-the start of history}. Use feat:, fix:, perf:, revert:, or a BREAKING CHANGE marker; otherwise provide an explicit release_version." >&2
  exit 1
fi

[[ "$MAJOR" == "1" ]] || {
  echo "Calculated release version escaped AverQel's v1.x.x release line" >&2
  exit 2
}

echo "v${MAJOR}.${MINOR}.${PATCH}"
