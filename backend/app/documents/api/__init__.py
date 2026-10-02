"""Documents and collections API routes."""

from app.documents.api import collection_security, collections, documents, organization

__all__ = ["collection_security", "collections", "documents", "organization"]
