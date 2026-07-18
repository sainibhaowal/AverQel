"""Curated official-vendor MCP catalog.

This intentionally does not proxy the public community registry. Raw registry
entries are unverified package IDs and are not suitable for a user-facing
marketplace.
"""

from __future__ import annotations

from typing import Any


OFFICIAL_MCP_VENDORS: tuple[dict[str, Any], ...] = (
    {
        "slug": "google-gmail",
        "aliases": ["gmail"],
        "vendor": "Google",
        "name": "Gmail",
        "description": "Official Google Workspace Gmail MCP server.",
        "server_url": "https://gmailmcp.googleapis.com/mcp/v1",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "google",
        "docs_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
    },
    {
        "slug": "google-drive",
        "vendor": "Google",
        "name": "Google Drive",
        "description": "Official Google Workspace Drive MCP server.",
        "server_url": "https://drivemcp.googleapis.com/mcp/v1",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "google",
        "docs_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
    },
    {
        "slug": "google-calendar",
        "vendor": "Google",
        "name": "Google Calendar",
        "description": "Official Google Workspace Calendar MCP server.",
        "server_url": "https://calendarmcp.googleapis.com/mcp/v1",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "google",
        "docs_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
    },
    {
        "slug": "google-chat",
        "vendor": "Google",
        "name": "Google Chat",
        "description": "Official Google Workspace Chat MCP server.",
        "server_url": "https://chatmcp.googleapis.com/mcp/v1",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "google",
        "docs_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
    },
    {
        "slug": "google-people",
        "vendor": "Google",
        "name": "Google People",
        "description": "Official Google People MCP server.",
        "server_url": "https://people.googleapis.com/mcp/v1",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "google",
        "docs_url": "https://developers.google.com/workspace/guides/configure-mcp-servers",
    },
    {
        "slug": "notion",
        "vendor": "Notion",
        "name": "Notion",
        "description": "Official hosted Notion MCP server.",
        "server_url": "https://mcp.notion.com/mcp",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "notion",
        "docs_url": "https://developers.notion.com/guides/mcp/overview",
    },
    {
        "slug": "github",
        "vendor": "GitHub",
        "name": "GitHub",
        "description": "Official GitHub Copilot MCP server.",
        "server_url": "https://api.githubcopilot.com/mcp/",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "oauth_provider_key": "github",
        "docs_url": "https://docs.github.com/en/copilot/customizing-copilot/using-remote-mcp-servers",
    },
    {
        "slug": "slack",
        "vendor": "Slack",
        "name": "Slack",
        "description": "Official Slack-hosted MCP server.",
        "server_url": None,
        "transport": "streamable_http",
        "oauth": "vendor_registration_required",
        "docs_url": "https://docs.slack.dev/ai/mcp-server",
    },
    {
        "slug": "figma",
        "vendor": "Figma",
        "name": "Figma",
        "description": "Official Figma remote MCP server.",
        "server_url": None,
        "transport": "streamable_http",
        "oauth": "vendor_registration_required",
        "docs_url": "https://developers.figma.com/docs/figma-mcp-server/",
    },
    {
        "slug": "microsoft-learn",
        "vendor": "Microsoft",
        "name": "Microsoft Learn",
        "description": "Official Microsoft Learn MCP server.",
        "server_url": "https://learn.microsoft.com/api/mcp",
        "transport": "streamable_http",
        "oauth": "none",
        "docs_url": "https://learn.microsoft.com/en-us/training/support/mcp-developer-reference",
    },
    {
        "slug": "seedlegals",
        "vendor": "SeedLegals",
        "name": "SeedLegals",
        "description": "Official SeedLegals MCP server for documents, signing status, and reminders.",
        "server_url": "https://api.seedlegals.com/mcp",
        "transport": "streamable_http",
        "oauth": "mcp_oauth",
        "docs_url": "https://seedlegals.com/resources/mcp-server/",
    },
)


def list_official_vendors() -> list[dict[str, Any]]:
    return [dict(item) for item in OFFICIAL_MCP_VENDORS]


def get_official_vendor(slug: str) -> dict[str, Any] | None:
    return next(
        (
            dict(item)
            for item in OFFICIAL_MCP_VENDORS
            if item["slug"] == slug or slug in (item.get("aliases") or [])
        ),
        None,
    )
