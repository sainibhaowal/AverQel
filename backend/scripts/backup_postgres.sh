#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKEND_STATE_DIR="${AVERQEL_BACKEND_STATE_DIR:-$BACKEND_DIR/.local}"

OUTPUT_DIR="$BACKEND_STATE_DIR/backups"
POSTGRES_SERVICE="postgres"
DB_NAME="knowledge"
DB_USER="postgres"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/backup_postgres.sh [options]

Options:
  --output-dir <dir>            Backup output directory (default: ./.local/backups)
  --postgres-service <name>     Docker compose service name (default: postgres)
  --db-name <name>              Database name (default: knowledge)
  --db-user <name>              Database user (default: postgres)
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
    --postgres-service)
      POSTGRES_SERVICE="${2:-}"
      shift 2
      ;;
    --db-name)
      DB_NAME="${2:-}"
      shift 2
      ;;
    --db-user)
      DB_USER="${2:-}"
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
BACKUP_FILE="$OUTPUT_DIR/postgres_${DB_NAME}_${TS}.sql.gz"
SHA_FILE="$BACKUP_FILE.sha256"
META_FILE="$BACKUP_FILE.metadata.json"

cd "$BACKEND_DIR"

DUMP_CMD="docker compose exec -T $POSTGRES_SERVICE pg_dump -U $DB_USER $DB_NAME | gzip -c > '$BACKUP_FILE'"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN: $DUMP_CMD"
  echo "DRY RUN: sha256sum '$BACKUP_FILE' > '$SHA_FILE'"
  echo "DRY RUN: write metadata to '$META_FILE'"
  exit 0
fi

eval "$DUMP_CMD"
sha256sum "$BACKUP_FILE" > "$SHA_FILE"
CHECKSUM="$(cut -d ' ' -f1 "$SHA_FILE")"
SIZE_BYTES="$(wc -c < "$BACKUP_FILE" | tr -d ' ')"
CREATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "$META_FILE" <<JSON
{
  "created_at_utc": "$CREATED_AT",
  "postgres_service": "$POSTGRES_SERVICE",
  "db_name": "$DB_NAME",
  "db_user": "$DB_USER",
  "backup_file": "$(basename "$BACKUP_FILE")",
  "sha256": "$CHECKSUM",
  "size_bytes": $SIZE_BYTES
}
JSON

echo "Backup created: $BACKUP_FILE"
echo "Checksum file: $SHA_FILE"
echo "Metadata file: $META_FILE"
