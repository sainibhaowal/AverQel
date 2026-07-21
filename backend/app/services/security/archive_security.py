"""Compatibility import for ingestion-owned archive security."""

from app.ingestion.services.security.archive_security import (
    ArchiveSecurityConfig,
    ArchiveSecurityService,
)

__all__ = ["ArchiveSecurityConfig", "ArchiveSecurityService"]
