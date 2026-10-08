#!/usr/bin/env bash
set -euo pipefail

HEAD_SHA="${1:-HEAD}"
BASE_TAG="${2:-}"

if [[ -n "$BASE_TAG" ]]; then
  [[ "$BASE_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "Invalid base tag '$BASE_TAG'; expected vMAJOR.MINOR.PATCH" >&2
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
    BASE_VERSION="${LAST_TAG#v}"
    COMMIT_RANGE="$LAST_TAG..$HEAD_SHA"
  else
    LAST_TAG=""
    BASE_VERSION="0.0.0"
    COMMIT_RANGE="$HEAD_SHA"
  fi
fi

COMMIT_SUBJECTS="$(git log "$COMMIT_RANGE" --format='%s')"
COMMIT_BODIES="$(git log "$COMMIT_RANGE" --format='%b')"
IFS=. read -r MAJOR MINOR PATCH <<< "$BASE_VERSION"

if grep -Eq '^[[:alnum:]_-]+(\([^)]*\))?!:[[:space:]]' <<< "$COMMIT_SUBJECTS" \
  || grep -Eq '^[[:space:]]*BREAKING[ -]CHANGE:' <<< "$COMMIT_BODIES"; then
  MAJOR=$((MAJOR + 1))
  MINOR=0
  PATCH=0
elif grep -Eq '^feat(\([^)]*\))?:[[:space:]]' <<< "$COMMIT_SUBJECTS"; then
  MINOR=$((MINOR + 1))
  PATCH=0
elif grep -Eq '^(fix|perf|revert)(\([^)]*\))?:[[:space:]]' <<< "$COMMIT_SUBJECTS"; then
  PATCH=$((PATCH + 1))
else
  echo "::error::No release-worthy Conventional Commit found since ${LAST_TAG:-the start of history}. Use feat:, fix:, perf:, revert:, or a BREAKING CHANGE marker; otherwise provide an explicit release_version." >&2
  exit 1
fi

echo "v${MAJOR}.${MINOR}.${PATCH}"
