"""Compatibility import for the provider API routes.

The canonical provider API now lives under ``app.providers.api``.
"""

from app.providers.api.providers import router

__all__ = ["router"]
