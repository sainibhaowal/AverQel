#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env.vps}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production env file not found. Expected $ROOT_DIR/.env.vps or an explicit env file path as the first argument"
  exit 1
fi

"$ROOT_DIR/scripts/validate_prod_env.sh" "$ENV_FILE"
chmod 600 "$ENV_FILE"
docker compose -f "$ROOT_DIR/docker-compose.prod.yml" --env-file "$ENV_FILE" config >/dev/null

docker compose -f "$ROOT_DIR/docker-compose.prod.yml" --env-file "$ENV_FILE" pull || true
docker compose -f "$ROOT_DIR/docker-compose.prod.yml" --env-file "$ENV_FILE" up -d --build --remove-orphans
docker compose -f "$ROOT_DIR/docker-compose.prod.yml" --env-file "$ENV_FILE" ps
