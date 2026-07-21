from __future__ import annotations

import re
from pathlib import Path

from app.system.schemas.errors import WEEK2_ERROR_CODES


def test_all_api_error_codes_are_registered() -> None:
    code_pattern = re.compile(r'code="([A-Z0-9_]+)"')
    discovered: set[str] = set()

    for path in Path("backend/app").rglob("*.py"):
        discovered.update(code_pattern.findall(path.read_text()))

    missing = sorted(discovered - WEEK2_ERROR_CODES)
    assert missing == []
