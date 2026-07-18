from __future__ import annotations

import logging
from uuid import UUID, uuid4

from uuid6 import uuid7

logger = logging.getLogger(__name__)


def generate_uuid7() -> UUID:
    """Generate a UUIDv7 identifier."""
    generated = uuid7()
    return generated if isinstance(generated, UUID) else UUID(str(generated))


def generate_uuid7_with_fallback() -> UUID:
    """
    Generate a UUIDv7 identifier and fall back to UUIDv4 if generation fails.

    The fallback preserves availability even if the UUIDv7 provider is unavailable
    or misbehaves at runtime.
    """
    try:
        return generate_uuid7()
    except Exception:  # noqa: BLE001
        logger.warning(
            "UUIDv7 generation failed; falling back to UUIDv4.", exc_info=True
        )
        return uuid4()
