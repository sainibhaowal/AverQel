#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

WINDOW_MINUTES="${WINDOW_MINUTES:-60}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgres}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-knowledge}"

cd "$BACKEND_DIR"

echo "== Container health =="
docker compose ps
echo

echo "== Security event counts in last ${WINDOW_MINUTES} minutes =="
docker compose exec -T "$POSTGRES_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -P pager=off -c "
WITH recent AS (
  SELECT action, status
  FROM audit_logs
  WHERE created_at >= NOW() - INTERVAL '${WINDOW_MINUTES} minutes'
)
SELECT label, count(*) AS count
FROM (
  SELECT CASE
    WHEN action LIKE 'auth.%' AND status <> 'success' THEN 'auth_failures'
    WHEN action = 'provider.secret.access' THEN 'provider_secret_reads'
    WHEN action LIKE 'deletion.%' AND status <> 'success' THEN 'deletion_failures'
    WHEN action LIKE 'admin.break_glass.%' THEN 'break_glass_events'
    ELSE NULL
  END AS label
  FROM recent
) labeled
WHERE label IS NOT NULL
GROUP BY label
ORDER BY label;
"

echo
echo "== Maintenance logs (recent) =="
docker compose logs --tail=80 worker scheduler | grep -Ei "deletion|retention|error|failed|provider.secret|break_glass|storage" || true
