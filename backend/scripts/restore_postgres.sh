#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

BACKUP_FILE=""
POSTGRES_SERVICE="postgres"
TARGET_DB="knowledge_restore"
TARGET_USER="postgres"
DROP_AND_RECREATE="false"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: scripts/restore_postgres.sh --backup-file <path> [options]

Options:
  --backup-file <path>          Required backup file path (.sql or .sql.gz)
  --postgres-service <name>     Docker compose service name (default: postgres)
  --target-db <name>            Restore target DB (default: knowledge_restore)
  --target-user <name>          Target DB user (default: postgres)
  --drop-and-recreate           Drop target DB before restore
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
    --postgres-service)
      POSTGRES_SERVICE="${2:-}"
      shift 2
      ;;
    --target-db)
      TARGET_DB="${2:-}"
      shift 2
      ;;
    --target-user)
      TARGET_USER="${2:-}"
      shift 2
      ;;
    --drop-and-recreate)
      DROP_AND_RECREATE="true"
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

if ! [[ "$TARGET_DB" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "Invalid --target-db value. Allowed: letters, numbers, underscore." >&2
  exit 1
fi

if ! [[ "$TARGET_USER" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "Invalid --target-user value. Allowed: letters, numbers, underscore." >&2
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

drop_create_cmd="docker compose exec -T $POSTGRES_SERVICE psql -U $TARGET_USER -d postgres -v ON_ERROR_STOP=1 -c \"DROP DATABASE IF EXISTS $TARGET_DB;\" -c \"CREATE DATABASE $TARGET_DB;\""
check_exists_cmd="docker compose exec -T $POSTGRES_SERVICE psql -U $TARGET_USER -d postgres -v ON_ERROR_STOP=1 -tAc \"SELECT 1 FROM pg_database WHERE datname='$TARGET_DB';\""
create_db_cmd="docker compose exec -T $POSTGRES_SERVICE createdb -U $TARGET_USER $TARGET_DB"
verify_cmd="docker compose exec -T $POSTGRES_SERVICE psql -U $TARGET_USER -d $TARGET_DB -v ON_ERROR_STOP=1 -tAc \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public';\""

if [[ "$DRY_RUN" == "true" ]]; then
  if [[ "$DROP_AND_RECREATE" == "true" ]]; then
    echo "DRY RUN: $drop_create_cmd"
  else
    echo "DRY RUN: $check_exists_cmd"
    echo "DRY RUN: (if missing) $create_db_cmd"
  fi
  if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "DRY RUN: gzip -dc '$BACKUP_FILE' | docker compose exec -T $POSTGRES_SERVICE psql -U $TARGET_USER -d $TARGET_DB -v ON_ERROR_STOP=1"
  else
    echo "DRY RUN: cat '$BACKUP_FILE' | docker compose exec -T $POSTGRES_SERVICE psql -U $TARGET_USER -d $TARGET_DB -v ON_ERROR_STOP=1"
  fi
  echo "DRY RUN: $verify_cmd"
  exit 0
fi

if [[ "$DROP_AND_RECREATE" == "true" ]]; then
  eval "$drop_create_cmd"
else
  DB_EXISTS="$(eval "$check_exists_cmd" | tr -d '[:space:]')"
  if [[ "$DB_EXISTS" != "1" ]]; then
    eval "$create_db_cmd"
  fi
fi

if [[ "$BACKUP_FILE" == *.gz ]]; then
  gzip -dc "$BACKUP_FILE" | docker compose exec -T "$POSTGRES_SERVICE" psql -U "$TARGET_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1
else
  cat "$BACKUP_FILE" | docker compose exec -T "$POSTGRES_SERVICE" psql -U "$TARGET_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1
fi

TABLE_COUNT="$(eval "$verify_cmd" | tr -d '[:space:]')"
verify_cols_cmd="docker compose exec -T $POSTGRES_SERVICE psql -U $TARGET_USER -d $TARGET_DB -v ON_ERROR_STOP=1 -tAc \"SELECT STRING_AGG(column_name, ', ') FROM information_schema.columns WHERE table_name='documents' AND column_name LIKE 'extraction_%';\""
EXTRACT_COLS="$(eval "$verify_cols_cmd" | tr -d '[:space:]')"

echo "Restore completed for database '$TARGET_DB'"
echo "Public table count after restore: ${TABLE_COUNT:-0}"
echo "Validated extraction metadata columns present: ${EXTRACT_COLS:-None}"
