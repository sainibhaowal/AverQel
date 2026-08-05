"""Persistence service for the code-reviewed official MCP catalog."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.catalog.mcp_official_providers import (
    CURATED_MCP_CATALOG_SOURCE,
    OFFICIAL_MCP_PROVIDERS,
    CuratedMCPProvider,
    validate_official_mcp_catalog,
)
from app.integrations.models.mcp_server import MCPRegistryEntry


@dataclass(frozen=True, slots=True)
class MCPCatalogSyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "total": self.created + self.updated + self.unchanged,
        }


class MCPCatalogService:
    """Upsert only AverQel's code-reviewed global catalog entries.

    The global registry has no tenant data. This service never touches MCP
    servers, OAuth tables, events, existing entries from other sources, or
    anything outside its own curated source namespace.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def sync_official_providers(
        self,
        providers: Iterable[CuratedMCPProvider] = OFFICIAL_MCP_PROVIDERS,
    ) -> MCPCatalogSyncResult:
        validate_official_mcp_catalog()
        provider_rows = tuple(providers)
        expected_slugs = {provider.provider_slug for provider in provider_rows}
        if len(expected_slugs) != len(provider_rows):
            raise ValueError("Curated MCP provider slugs must be unique")

        existing_entries = (
            self.session.execute(
                select(MCPRegistryEntry).where(
                    MCPRegistryEntry.source == CURATED_MCP_CATALOG_SOURCE,
                    MCPRegistryEntry.server_name.in_(expected_slugs),
                )
            )
            .scalars()
            .all()
        )
        existing_by_slug = {entry.server_name: entry for entry in existing_entries}

        created = updated = unchanged = 0
        for provider in provider_rows:
            values = provider.registry_values()
            entry = existing_by_slug.get(provider.provider_slug)
            if entry is None:
                self.session.add(MCPRegistryEntry(**values))
                created += 1
                continue
            if self._apply_values(entry, values):
                updated += 1
            else:
                unchanged += 1

        self.session.flush()
        return MCPCatalogSyncResult(created=created, updated=updated, unchanged=unchanged)

    @staticmethod
    def _apply_values(entry: MCPRegistryEntry, values: dict[str, object]) -> bool:
        changed = False
        for field, value in values.items():
            if getattr(entry, field) != value:
                setattr(entry, field, value)
                changed = True
        return changed
