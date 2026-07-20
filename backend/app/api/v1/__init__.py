from app.auth import api as auth

from app.api.v1 import (
    admin,
    analytics,
    client_storage,
    collections,
    documents,
    health,
    intelligence,
    metrics,
    providers,
    queries,
    support,
    workspace,
)

__all__ = [
    "auth",
    "admin",
    "collections",
    "client_storage",
    "documents",
    "health",
    "metrics",
    "providers",
    "queries",
    "intelligence",
    "workspace",
    "analytics",
    "support",
]
