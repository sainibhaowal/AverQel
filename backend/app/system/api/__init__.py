"""System and administration API routes."""

from app.system.api import (
    admin,
    app_feedback,
    capabilities,
    feedback,
    health,
    metrics,
    support,
)

__all__ = [
    "admin",
    "app_feedback",
    "capabilities",
    "feedback",
    "health",
    "metrics",
    "support",
]
