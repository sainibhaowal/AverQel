"""Import public MCP Registry metadata into the marketplace catalog."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations.mcp_server import MCPRegistryEntry
from app.services.integrations.mcp_registry import OFFICIAL_MCP_VENDORS

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"

def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    server = item.get("server") if isinstance(item.get("server"), dict) else item
    name = str(server.get("name") or server.get("id") or "").strip()
    remotes = server.get("remotes") or []
    remote = remotes[0] if isinstance(remotes, list) and remotes and isinstance(remotes[0], dict) else {}
    packages = server.get("packages") or []
    package = packages[0] if isinstance(packages, list) and packages and isinstance(packages[0], dict) else {}
    url = remote.get("url") or remote.get("urlTemplate")
    transport = remote.get("type") or ("stdio" if packages else None)
    publisher = server.get("publisher") or server.get("author")
    categories = server.get("categories") or server.get("tags") or []
    if isinstance(categories, str): categories = [categories]
    categories = sorted({str(x).strip().lower() for x in categories if str(x).strip()})
    logo = server.get("icon") or server.get("logo") or server.get("iconUrl")
    return {"server_name": name, "display_name": str(server.get("title") or name), "publisher": publisher,
            "description": server.get("description"), "transport": transport, "remote_url": url,
            "package_metadata": package, "oauth_requirements": remote.get("securitySchemes") or {},
            "categories": categories, "logo_url": logo, "raw_metadata": item}

def sync_registry(db: Session, *, limit: int = 1000) -> int:
    response = httpx.get(REGISTRY_URL, params={"limit": limit}, timeout=30, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("servers", payload if isinstance(payload, list) else [])
    official_urls = {v.get("server_url") for v in OFFICIAL_MCP_VENDORS}
    count = 0
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        data = _normalize(raw)
        if not data["server_name"]:
            continue
        data["official"] = data["remote_url"] in official_urls
        data["verified"] = data["official"]
        data["verification_reason"] = "curated official endpoint" if data["official"] else "registry metadata only"
        row = db.execute(select(MCPRegistryEntry).where(MCPRegistryEntry.source == "official_registry", MCPRegistryEntry.server_name == data["server_name"])).scalar_one_or_none()
        if row is None:
            row = MCPRegistryEntry(source="official_registry", **data)
            db.add(row)
        else:
            for key, value in data.items(): setattr(row, key, value)
            row.last_seen_at = datetime.now(UTC)
        count += 1
    db.commit()
    return count
