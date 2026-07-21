from app.auth import api as auth

from app.api.v1 import (
    client_storage,
    workspace,
)
from app.query.api import chats, intelligence, queries
from app.system.api import admin, capabilities, feedback, health, metrics, support
from app.documents.api import collections, documents
from app.analytics.api import analytics, dashboard
from app.providers.api import providers

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
