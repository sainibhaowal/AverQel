from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.models.connector import Connector


class ConnectorService(ABC):
    """
    Base class for all external data connectors.
    Handles the orchestration of fetching data and feeding it into the ingestion pipeline.
    """

    def __init__(self, connector: Connector, session: Session):
        self.connector = connector
        self.session = session

    @abstractmethod
    def sync(self) -> dict[str, Any]:
        """
        Initiate the synchronization process.
        Returns a summary of the sync results (new docs, updated docs, errors).
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate that the current connector configuration and credentials are valid.
        """
        pass

    def validate_health(self) -> dict[str, Any]:
        """
        Return a structured health report for connector monitoring and circuit breaking.

        Concrete connectors can override this to provide richer health diagnostics. The
        default implementation preserves the legacy boolean validation behavior.
        """

        healthy = bool(self.validate_config())
        now = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        return {
            "healthy": healthy,
            "status": "healthy" if healthy else "degraded",
            "error_code": None if healthy else "validation_failed",
            "error_message": None if healthy else "Legacy validation failed.",
            "metadata": {},
            "checked_at": now,
        }
