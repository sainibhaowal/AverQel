#!/usr/bin/env bash
set -Eeuo pipefail

# Validate production and isolated compose manifests without starting or
# restarting a service. All values below are disposable placeholders used only
# for interpolation; no repository or operator secret is read.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/averqel-deployment-check.XXXXXX")"
trap 'rm -rf -- "$TEMP_ROOT"' EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to validate compose manifests." >&2
  exit 2
fi
docker compose version >/dev/null

ENV_FILE="$TEMP_ROOT/averqel.env"
cat >"$ENV_FILE" <<'EOF'
AVERQEL_POSTGRES_USER=averqel
AVERQEL_POSTGRES_PASSWORD=deployment-check-postgres
AVERQEL_POSTGRES_DB=knowledge
AVERQEL_REDIS_PASSWORD=deployment-check-redis
AVERQEL_MINIO_ROOT_USER=deploymentcheck
AVERQEL_MINIO_ROOT_PASSWORD=deployment-check-minio-password
AVERQEL_ENV_FILE=__RUNTIME_ENV_FILE__
AVERQEL_IMAGE_TAG=deployment-check
AVERQEL_RELEASE_VERSION=deployment-check
AVERQEL_GIT_SHA=deployment-check
AVERQEL_BUILD_TIMESTAMP=deployment-check
AKS_MINIO_ACCESS_KEY=deploymentcheck
AKS_MINIO_SECRET_KEY=deployment-check-minio-secret
AKS_CORS_ORIGINS=["http://localhost"]
AKS_JWT_SECRET=deployment-check-jwt-secret-with-at-least-32-chars
AKS_REFRESH_TOKEN_HASH_SECRET=deployment-check-refresh-secret-32chars
AKS_PROVIDER_SECRET_ACTIVE_KID=deployment-check
AKS_PROVIDER_SECRET_KEYRING_JSON={"deployment-check":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}
AKS_TOTP_SECRET_ACTIVE_KID=deployment-check
AKS_TOTP_SECRET_KEYRING_JSON={"deployment-check":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}
EOF

# The production compose file references the env file from inside containers.
# It only needs to exist for interpolation validation; compose config does not
# open a container or mount this host path.
RUNTIME_ENV_FILE="$TEMP_ROOT/runtime.env"
touch "$RUNTIME_ENV_FILE"
sed -i "s#__RUNTIME_ENV_FILE__#$RUNTIME_ENV_FILE#" "$ENV_FILE"
trap 'rm -rf -- "$TEMP_ROOT"' EXIT

cd "$BACKEND_DIR"
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml config --quiet
docker compose --env-file /dev/null -f ops/test/compose.yml config --quiet
echo "Compose deployment manifests validated without starting services."
