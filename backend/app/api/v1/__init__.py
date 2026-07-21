from app.analytics.api import analytics, dashboard
from app.auth import api as auth
from app.deepspace.api import chats as deepspace_chats
from app.deepspace.api import client_storage, workspace
from app.deepspace.api import export as deepspace_export
from app.documents.api import collections, documents
from app.providers.api import providers
from app.query.api import chats, intelligence, queries
from app.system.api import admin, capabilities, feedback, health, metrics, support

__all__ = [
    "auth",
    "analytics",
    "admin",
    "capabilities",
    "chats",
    "collections",
    "client_storage",
    "deepspace_chats",
    "deepspace_export",
    "documents",
    "feedback",
    "health",
    "intelligence",
    "metrics",
    "providers",
    "queries",
    "workspace",
    "support",
    "dashboard",
]
