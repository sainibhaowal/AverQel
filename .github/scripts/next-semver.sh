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
  COMMITS="$(git log "$LAST_TAG..$HEAD_SHA" --format='%s%n%b')"
else
  mapfile -t STABLE_TAGS < <(
    git for-each-ref --format='%(refname:strip=2)' refs/tags \
      | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
      | sort -V
  )

  if ((${#STABLE_TAGS[@]} > 0)); then
    LAST_TAG="${STABLE_TAGS[${#STABLE_TAGS[@]}-1]}"
    BASE_VERSION="${LAST_TAG#v}"
    COMMITS="$(git log "$LAST_TAG..$HEAD_SHA" --format='%s%n%b')"
  else
    LAST_TAG=""
    BASE_VERSION="0.0.0"
    COMMITS="$(git log "$HEAD_SHA" --format='%s%n%b')"
  fi
fi

IFS=. read -r MAJOR MINOR PATCH <<< "$BASE_VERSION"

if grep -Eq '(^|[[:space:]])BREAKING CHANGE:|^[[:alnum:]_-]+(\([^)]*\))?!:' <<< "$COMMITS"; then
  MAJOR=$((MAJOR + 1))
  MINOR=0
  PATCH=0
elif grep -Eq '^feat(\([^)]*\))?!?:' <<< "$COMMITS"; then
  MINOR=$((MINOR + 1))
  PATCH=0
else
  PATCH=$((PATCH + 1))
fi

echo "v${MAJOR}.${MINOR}.${PATCH}"
