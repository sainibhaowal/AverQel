#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKEND_STATE_DIR="${AVERQEL_BACKEND_STATE_DIR:-$BACKEND_DIR/.local}"

OUTPUT_DIR="$BACKEND_STATE_DIR/backups"
ENV_FILE="${1:-$BACKEND_DIR/.env.vps}"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/backup_prod_config.sh [env-file] [options]

Arguments:
  env-file                        Production env file path (default: backend/.env.vps)

Options:
  --output-dir <dir>              Backup output directory (default: ./.local/backups)
  --dry-run                       Print backup commands without executing
  -h, --help                      Show help
EOF
}

POSITIONAL_ENV_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
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
      if [[ -z "$POSITIONAL_ENV_FILE" ]]; then
        POSITIONAL_ENV_FILE="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ -n "$POSITIONAL_ENV_FILE" ]]; then
  ENV_FILE="$POSITIONAL_ENV_FILE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
TS="$(date -u +"%Y%m%d_%H%M%S")"
ARCHIVE_FILE="$OUTPUT_DIR/prod_config_${TS}.tar.gz"
SHA_FILE="$ARCHIVE_FILE.sha256"
META_FILE="$ARCHIVE_FILE.metadata.json"
CERT_DIR="${AVERQEL_TLS_CERTS_DIR:-$BACKEND_STATE_DIR/certs}"

ARCHIVE_INPUTS=(
  "$(realpath "$ENV_FILE")"
  "$BACKEND_DIR/docker-compose.prod.yml"
  "$BACKEND_DIR/ops/caddy/Caddyfile"
)

if [[ -d "$CERT_DIR" ]]; then
  ARCHIVE_INPUTS+=("$CERT_DIR")
fi

if [[ "$DRY_RUN" == "true" ]]; then
  printf 'DRY RUN: tar -czf %q' "$ARCHIVE_FILE"
  for input in "${ARCHIVE_INPUTS[@]}"; do
    printf ' %q' "$input"
  done
  printf '\n'
  echo "DRY RUN: sha256sum '$ARCHIVE_FILE' > '$SHA_FILE'"
  echo "DRY RUN: write metadata to '$META_FILE'"
  exit 0
fi

tar -czf "$ARCHIVE_FILE" "${ARCHIVE_INPUTS[@]}"
chmod 600 "$ARCHIVE_FILE"
sha256sum "$ARCHIVE_FILE" > "$SHA_FILE"
CHECKSUM="$(cut -d ' ' -f1 "$SHA_FILE")"
SIZE_BYTES="$(wc -c < "$ARCHIVE_FILE" | tr -d ' ')"
CREATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "$META_FILE" <<JSON
{
  "created_at_utc": "$CREATED_AT",
  "env_file": "$(basename "$ENV_FILE")",
  "backup_file": "$(basename "$ARCHIVE_FILE")",
  "sha256": "$CHECKSUM",
  "size_bytes": $SIZE_BYTES
}
JSON

echo "Backup created: $ARCHIVE_FILE"
echo "Checksum file: $SHA_FILE"
echo "Metadata file: $META_FILE"
