"""Compatibility import for query API routes."""

from app.query.api.queries import _merge_chat_reasoning_capabilities, router

__all__ = ["_merge_chat_reasoning_capabilities", "router"]
