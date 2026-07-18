#!/usr/bin/env bash
set -euo pipefail

exec uvicorn app.inference.main:app --host 0.0.0.0 --port 1011
