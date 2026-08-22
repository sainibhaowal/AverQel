#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKEND_STATE_DIR="${AVERQEL_BACKEND_STATE_DIR:-$BACKEND_DIR/.local}"
export DOCKER_BUILDKIT=1

VERSION=""
GIT_SHA=""
IMAGE_PREFIX="aks"
PUSH_IMAGES="false"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/release_build_images.sh --version <version> [options]

Options:
  --version <version>           Required release version tag (e.g. v1.0.0)
  --git-sha <sha>               Optional git sha (defaults to local git or unknown)
  --image-prefix <prefix>       Image prefix (default: aks)
  --push                        Push images after build
  --dry-run                     Print commands without executing
  -h, --help                    Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --git-sha)
      GIT_SHA="${2:-}"
      shift 2
      ;;
    --image-prefix)
      IMAGE_PREFIX="${2:-}"
      shift 2
      ;;
    --push)
      PUSH_IMAGES="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "--version is required" >&2
  usage
  exit 1
fi

if [[ -z "$GIT_SHA" ]]; then
  if command -v git >/dev/null 2>&1 && git -C "$BACKEND_DIR" rev-parse --short HEAD >/dev/null 2>&1; then
    GIT_SHA="$(git -C "$BACKEND_DIR" rev-parse --short HEAD)"
  else
    GIT_SHA="unknown"
  fi
fi

BUILD_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
# Set this in GitHub Actions to enable persistent BuildKit cache storage.
# Local runs keep using the normal Docker builder when it is unset.
DOCKER_CACHE_SCOPE="${AVERQEL_DOCKER_CACHE_SCOPE:-}"
# Use dash naming for GHCR private: ghcr.io/sainibhaowal/averqel-api etc (single repo per service, no nested slash)
API_IMAGE_BASE="${IMAGE_PREFIX}-api"
WORKER_IMAGE_BASE="${IMAGE_PREFIX}-worker"
API_TAG_VERSION="${API_IMAGE_BASE}:${VERSION}"
API_TAG_SHA="${API_IMAGE_BASE}:${GIT_SHA}"
WORKER_TAG_VERSION="${WORKER_IMAGE_BASE}:${VERSION}"
WORKER_TAG_SHA="${WORKER_IMAGE_BASE}:${GIT_SHA}"

mkdir -p "$BACKEND_STATE_DIR/dist"
MANIFEST_PATH="$BACKEND_STATE_DIR/dist/release-manifest-${VERSION}.json"

build_cmd_api=(
  docker build
  -f "$BACKEND_DIR/Dockerfile"
  -t "$API_TAG_VERSION"
  -t "$API_TAG_SHA"
  --build-arg "GIT_VERSION=$VERSION"
  --build-arg "GIT_SHA=$GIT_SHA"
  --build-arg "BUILD_TIMESTAMP=$BUILD_TS"
  --label "org.opencontainers.image.version=$VERSION"
  --label "org.opencontainers.image.revision=$GIT_SHA"
  --label "org.opencontainers.image.created=$BUILD_TS"
  "$BACKEND_DIR"
)

build_cmd_worker=(
  docker build
  -f "$BACKEND_DIR/Dockerfile.worker"
  -t "$WORKER_TAG_VERSION"
  -t "$WORKER_TAG_SHA"
  --build-arg "GIT_VERSION=$VERSION"
  --build-arg "GIT_SHA=$GIT_SHA"
  --build-arg "BUILD_TIMESTAMP=$BUILD_TS"
  --label "org.opencontainers.image.version=$VERSION"
  --label "org.opencontainers.image.revision=$GIT_SHA"
  --label "org.opencontainers.image.created=$BUILD_TS"
  "$BACKEND_DIR"
)

if [[ -n "$DOCKER_CACHE_SCOPE" ]]; then
  build_cmd_api=(
    docker buildx build
    --load
    --cache-from "type=gha,scope=${DOCKER_CACHE_SCOPE}-api"
    --cache-to "type=gha,mode=max,scope=${DOCKER_CACHE_SCOPE}-api"
    "${build_cmd_api[@]:2}"
  )
  build_cmd_worker=(
    docker buildx build
    --load
    --cache-from "type=gha,scope=${DOCKER_CACHE_SCOPE}-worker"
    --cache-to "type=gha,mode=max,scope=${DOCKER_CACHE_SCOPE}-worker"
    "${build_cmd_worker[@]:2}"
  )
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN: ${build_cmd_api[*]}"
  echo "DRY RUN: ${build_cmd_worker[*]}"
  if [[ "$PUSH_IMAGES" == "true" ]]; then
    echo "DRY RUN: docker push $API_TAG_VERSION"
    echo "DRY RUN: docker push $API_TAG_SHA"
    echo "DRY RUN: docker push $WORKER_TAG_VERSION"
    echo "DRY RUN: docker push $WORKER_TAG_SHA"
  fi
else
  "${build_cmd_api[@]}"
  "${build_cmd_worker[@]}"
  if [[ "$PUSH_IMAGES" == "true" ]]; then
    docker push "$API_TAG_VERSION"
    docker push "$API_TAG_SHA"
    docker push "$WORKER_TAG_VERSION"
    docker push "$WORKER_TAG_SHA"
  fi
fi

cat > "$MANIFEST_PATH" <<JSON
{
  "release_version": "$VERSION",
  "git_sha": "$GIT_SHA",
  "build_timestamp_utc": "$BUILD_TS",
  "images": {
    "api": ["$API_TAG_VERSION", "$API_TAG_SHA"],
    "worker": ["$WORKER_TAG_VERSION", "$WORKER_TAG_SHA"]
  },
  "push_images": $([[ "$PUSH_IMAGES" == "true" ]] && echo true || echo false)
}
JSON

echo "Release manifest written: $MANIFEST_PATH"
