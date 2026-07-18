#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKEND_STATE_DIR="${AVERQEL_BACKEND_STATE_DIR:-$BACKEND_DIR/.local}"

OUTPUT_DIR="$BACKEND_STATE_DIR/backups"
MINIO_SERVICE="minio"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/backup_minio.sh [options]

Options:
  --output-dir <dir>            Backup output directory (default: ./.local/backups)
  --minio-service <name>        Docker compose service name (default: minio)
  --dry-run                     Print backup commands without executing
  -h, --help                    Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --minio-service)
      MINIO_SERVICE="${2:-}"
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
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

mkdir -p "$OUTPUT_DIR"
TS="$(date -u +"%Y%m%d_%H%M%S")"
BACKUP_FILE="$OUTPUT_DIR/minio_data_${TS}.tar.gz"
SHA_FILE="$BACKUP_FILE.sha256"
META_FILE="$BACKUP_FILE.metadata.json"

cd "$BACKEND_DIR"

BACKUP_CMD="docker compose exec -T $MINIO_SERVICE sh -c 'tar -C /data -czf - .' > '$BACKUP_FILE'"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN: $BACKUP_CMD"
  echo "DRY RUN: sha256sum '$BACKUP_FILE' > '$SHA_FILE'"
  echo "DRY RUN: write metadata to '$META_FILE'"
  exit 0
fi

eval "$BACKUP_CMD"
sha256sum "$BACKUP_FILE" > "$SHA_FILE"
CHECKSUM="$(cut -d ' ' -f1 "$SHA_FILE")"
SIZE_BYTES="$(wc -c < "$BACKUP_FILE" | tr -d ' ')"
CREATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "$META_FILE" <<JSON
{
  "created_at_utc": "$CREATED_AT",
  "minio_service": "$MINIO_SERVICE",
  "backup_file": "$(basename "$BACKUP_FILE")",
  "sha256": "$CHECKSUM",
  "size_bytes": $SIZE_BYTES
}
JSON

echo "Backup created: $BACKUP_FILE"
echo "Checksum file: $SHA_FILE"
echo "Metadata file: $META_FILE"
