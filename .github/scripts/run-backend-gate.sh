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
    pip-audit -s osv --ignore-vuln GHSA-xf7x-x43h-rpqh -r requirements.txt -r requirements-dev.txt
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
