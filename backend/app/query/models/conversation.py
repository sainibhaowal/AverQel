"""Compatibility import for legacy Query code.

The canonical conversation model is DeepSpace-owned. Query code can still
read its historical import path without creating a second SQLAlchemy mapper.
"""

from app.deepspace.models.conversation import Conversation

__all__ = ["Conversation"]
