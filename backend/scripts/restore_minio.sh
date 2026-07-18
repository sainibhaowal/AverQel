#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

BACKUP_FILE=""
MINIO_SERVICE="minio"
DROP_EXISTING="false"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/restore_minio.sh --backup-file <path> [options]

Options:
  --backup-file <path>          Required MinIO backup file path (.tar.gz)
  --minio-service <name>        Docker compose service name (default: minio)
  --drop-existing               Remove current /data contents before restore
  --dry-run                     Print restore commands without executing
  -h, --help                    Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-file)
      BACKUP_FILE="${2:-}"
      shift 2
      ;;
    --minio-service)
      MINIO_SERVICE="${2:-}"
      shift 2
      ;;
    --drop-existing)
      DROP_EXISTING="true"
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

if [[ -z "$BACKUP_FILE" ]]; then
  echo "--backup-file is required" >&2
  usage
  exit 1
fi

if [[ "$DRY_RUN" == "false" && ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

SHA_FILE="$BACKUP_FILE.sha256"

cd "$BACKEND_DIR"

if [[ "$DRY_RUN" == "false" && -f "$SHA_FILE" ]]; then
  sha256sum -c "$SHA_FILE"
fi

if [[ "$DRY_RUN" == "true" ]]; then
  if [[ "$DROP_EXISTING" == "true" ]]; then
    echo "DRY RUN: docker compose exec -T $MINIO_SERVICE sh -c 'rm -rf /data/*'"
  fi
  echo "DRY RUN: cat '$BACKUP_FILE' | docker compose exec -T $MINIO_SERVICE sh -c 'tar -C /data -xzf -'"
  exit 0
fi

if [[ "$DROP_EXISTING" == "true" ]]; then
  docker compose exec -T "$MINIO_SERVICE" sh -c 'rm -rf /data/*'
fi

cat "$BACKUP_FILE" | docker compose exec -T "$MINIO_SERVICE" sh -c 'tar -C /data -xzf -'

echo "Restore completed for MinIO data from '$BACKUP_FILE'"
