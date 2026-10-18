#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
if [[ ! "$VERSION" =~ ^v1\.[0-9]+\.[0-9]+$ ]]; then
  echo "::error::AverQel releases are restricted to v1.x.x (received '${VERSION:-empty}')" >&2
  exit 1
fi

printf '%s\n' "$VERSION"
