#!/usr/bin/env bash
set -euo pipefail

GATE="${1:?gate name is required}"

case "$GATE" in
  ruff)
    ruff check .
    ;;
  ruff-fix)
    ruff check . --fix
    if ! git diff --exit-code; then
      echo "::error::ruff --fix produced changes - please run 'ruff check . --fix' locally and commit"
      git diff
      exit 1
    fi
    ;;
  black)
    black --check .
    ;;
  black-format)
    black .
    if ! git diff --exit-code; then
      echo "::error::black produced changes - please run 'black .' locally and commit"
      git diff
      exit 1
    fi
    ;;
  mypy)
    mypy .
    ;;
  bandit)
    bandit -r app -q --severity-level medium
    ;;
  pip-audit)
    # OSV is an external service. Retry only availability failures so a
    # temporary outage does not fail the gate, while real findings remain
    # blocking and are returned immediately.
    max_attempts=4
    attempt=1
    while true; do
      set +e
      audit_output="$(pip-audit -s osv -r requirements.txt -r requirements-dev.txt 2>&1)"
      audit_status=$?
      set -e
      printf '%s\n' "$audit_output"

      if [ "$audit_status" -eq 0 ]; then
        break
      fi

      if ! grep -Eiq 'ServiceError|HTTP (429|500|502|503|504)|timed out|timeout|connection (reset|error)' <<<"$audit_output"; then
        exit "$audit_status"
      fi

      if [ "$attempt" -ge "$max_attempts" ]; then
        echo "::error::pip-audit service was unavailable after $max_attempts attempts"
        exit "$audit_status"
      fi

      delay=$((5 * 2 ** (attempt - 1)))
      echo "::warning::pip-audit service unavailable; retrying in ${delay}s (attempt $((attempt + 1))/$max_attempts)"
      sleep "$delay"
      attempt=$((attempt + 1))
    done
    ;;
  safety)
    safety check --full-report
    ;;
  pytest)
    pytest -q -m unit_no_db --dist=loadgroup
    ;;
  *)
    echo "Unknown backend gate: $GATE" >&2
    exit 2
    ;;
esac
