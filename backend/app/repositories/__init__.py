"""Repository compatibility exports.

Repositories are implemented in their domain packages. Lazy exports preserve
the historical ``app.repositories`` imports without eagerly importing every
repository and creating cross-domain circular imports.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "UsersRepository": ("app.auth.repositories.users", "UsersRepository"),
    "RolesRepository": ("app.auth.repositories.roles", "RolesRepository"),
    "RefreshTokensRepository": (
        "app.auth.repositories.refresh_tokens",
        "RefreshTokensRepository",
    ),
    "DocumentsRepository": (
        "app.documents.repositories.documents",
        "DocumentsRepository",
    ),
    "CollectionNotificationsRepository": (
        "app.documents.repositories.collection_notifications",
        "CollectionNotificationsRepository",
    ),
    "IngestionJobsRepository": (
        "app.ingestion.repositories.ingestion_jobs",
        "IngestionJobsRepository",
    ),
    "QueriesRepository": ("app.repositories.query.queries", "QueriesRepository"),
    "ChunksRepository": ("app.documents.repositories.chunks", "ChunksRepository"),
    "IdempotencyKeysRepository": (
        "app.repositories.system.idempotency_keys",
        "IdempotencyKeysRepository",
    ),
    "AuditLogsRepository": (
        "app.repositories.system.audit_logs",
        "AuditLogsRepository",
    ),
    "DataDeletionsRepository": (
        "app.documents.repositories.data_deletions",
        "DataDeletionsRepository",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    return getattr(import_module(module_name), attribute_name)
