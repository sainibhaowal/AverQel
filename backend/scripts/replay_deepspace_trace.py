#!/usr/bin/env python3
"""Replay one sanitized DeepSpace fixture without network or application storage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support both `python scripts/...` from backend/ and
# `python backend/scripts/...` from the repository root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.deepspace.services.replay_trace import replay_trace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.trace.read_text(encoding="utf-8"))
    print(json.dumps(replay_trace(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
