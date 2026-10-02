"""Redact sensitive spans from provider-exposed reasoning before user delivery."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

REASONING_REDACTION_VERSION: Final[int] = 1
MASK: Final[str] = "••••••••"


_REDACTION_PATTERNS: Final[
    tuple[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]], ...]
] = (
    # PEM material must never be displayed as a partial value.
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 _-]*PRIVATE KEY-----.*?-----END [A-Z0-9 _-]*PRIVATE KEY-----",
            re.IGNORECASE | re.DOTALL,
        ),
        MASK,
    ),
    # Common credential labels, including values copied from tool headers.
    (
        re.compile(
            r"(?i)\b(authorization|x-api-key|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|session[ _-]?token|password|secret|cookie)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;\]\)}]+"
        ),
        lambda match: f"{match.group(1)}: {MASK}",
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{6,}"), f"Bearer {MASK}"),
    # Provider keys and JWT-like credentials occasionally appear without labels.
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), MASK),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), MASK),
    # Never reveal credentials embedded in a connection URL.
    (re.compile(r"([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE), r"\1••••:••••@"),
    # Internal endpoints and loopback/private-network addresses are server details.
    (
        re.compile(
            r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|[A-Za-z0-9.-]+\.internal)(?::\d+)?(?:/[^\s]*)?",
            re.IGNORECASE,
        ),
        MASK,
    ),
    # Opaque workspace/resource identifiers are not useful in visible reasoning.
    (
        re.compile(
            r"(?i)\b(file|conversation|tenant|user|run|tool)[ _-]?id\b\s*[:=]\s*[0-9a-f]{8}-[0-9a-f-]{27,}"
        ),
        lambda match: f"{match.group(1)} id: {MASK}",
    ),
    # Do not surface copied hidden-instruction blocks.
    (
        re.compile(
            r"(?is)\b(system prompt|developer instructions?|hidden instructions?)\b\s*[:=-]\s*.*?(?=\n\s*\n|\Z)"
        ),
        lambda match: f"{match.group(1)}: {MASK}",
    ),
)


def redact_reasoning_text(value: str) -> str:
    """Return user-visible reasoning with known secret/private spans masked.

    This deliberately preserves all non-sensitive text and token order. Raw
    provider reasoning must never be streamed or persisted by a caller.
    """

    redacted = str(value or "")
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
