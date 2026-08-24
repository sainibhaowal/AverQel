"""Code-reviewed metadata for AverQel's official remote MCP catalog.

This module is deliberately data-only. It contains public provider metadata,
never OAuth client credentials, user tokens, HTTP headers, or live catalog
responses. Live tools are rediscovered only after a user authenticates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

CURATED_MCP_CATALOG_SOURCE = "averqel-curated-official-v1"
CATALOG_REVIEWED_AT = datetime(2026, 7, 23, tzinfo=UTC)
CATALOG_REVIEW_DUE_AT = datetime(2026, 10, 21, tzinfo=UTC)

RiskLabel = Literal["read", "write", "delete", "external_message"]


@dataclass(frozen=True, slots=True)
class CuratedMCPTool:
    """A reviewed catalog tool safe for marketplace display."""

    name: str
    description: str
    category: str
    risk_labels: tuple[RiskLabel, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "risk_labels": list(self.risk_labels),
        }


@dataclass(frozen=True, slots=True)
class CuratedMCPProvider:
    """One reviewed official remote MCP provider entry."""

    provider_slug: str
    display_name: str
    publisher: str
    description: str
    remote_url: str
    documentation_url: str
    author_website_url: str
    support_url: str
    privacy_policy_url: str
    categories: tuple[str, ...]
    supported_products: tuple[str, ...]
    requested_scopes: tuple[str, ...]
    tool_preview: tuple[CuratedMCPTool, ...]
    availability: str
    popularity_rank: int
    trusted_logo_key: str
    scope_mode: str = "explicit"
    scope_note: str | None = None
    catalog_status: str | None = None
    connection_ready: bool = False
    connection_readiness_reason: str | None = None

    @property
    def transport(self) -> str:
        return "streamable_http"

    @property
    def tools(self) -> tuple[CuratedMCPTool, ...]:
        """The complete reviewed tool set currently published by AverQel.

        ``tool_preview`` remains the compatibility name used by existing
        marketplace cards. Both values come from the same reviewed source;
        the detail API exposes ``tools`` explicitly so it is not mistaken for
        a truncated live-server response.
        """
        return self.tool_preview

    def registry_values(self) -> dict[str, Any]:
        """Return safe values for ``MCPRegistryEntry`` fields.

        Static-profile providers remain unavailable until their server-side
        OAuth credentials are configured. Providers that publish a reviewed
        MCP OAuth discovery flow can opt into the generic broker safely.
        """
        badges = {
            "official": True,
            "community": False,
            "new": False,
            "trending": False,
            "interactive": False,
            "developer_preview": self.availability == "developer_preview",
        }
        risk_policy = {
            "default_mode": "needs_approval",
            "read": {"default_mode": "always_allow"},
            "write": {"default_mode": "needs_approval"},
            "delete": {"default_mode": "needs_approval"},
            "external_message": {"default_mode": "needs_approval"},
        }
        tools = [tool.as_dict() for tool in self.tools]
        tool_preview = tools
        tool_risk_summary = {
            label: sum(label in tool.risk_labels for tool in self.tool_preview)
            for label in ("read", "write", "delete", "external_message")
        }
        catalog_metadata = {
            "schema_version": 1,
            "provider_slug": self.provider_slug,
            "publisher_type": "official",
            "author_name": self.publisher,
            "author_website_url": self.author_website_url,
            "documentation_url": self.documentation_url,
            "support_url": self.support_url,
            "privacy_policy_url": self.privacy_policy_url,
            "badges": badges,
            "availability": self.availability,
            "reviewed_at": CATALOG_REVIEWED_AT.isoformat(),
            "review_due_at": CATALOG_REVIEW_DUE_AT.isoformat(),
            "trusted_logo_key": self.trusted_logo_key,
            "supported_products": list(self.supported_products),
            "tool_categories": sorted({tool.category for tool in self.tool_preview}),
            "tools": tools,
            "tool_preview": tool_preview,
            "risk_policy": risk_policy,
            "health": {
                "status": "not_checked",
                "last_checked_at": None,
                "detail": "Live health is checked only after user authentication.",
            },
            "connection_ready": self.connection_ready,
            "connection_readiness_reason": self.connection_readiness_reason
            or (None if self.connection_ready else "OAuth provider profile is not configured yet."),
        }
        if self.scope_note:
            catalog_metadata["scope_note"] = self.scope_note

        return {
            "source": CURATED_MCP_CATALOG_SOURCE,
            "server_name": self.provider_slug,
            "display_name": self.display_name,
            "publisher": self.publisher,
            "provider_slug": self.provider_slug,
            "publisher_type": "official",
            "version": None,
            "description": self.description,
            "transport": self.transport,
            "remote_url": self.remote_url,
            "documentation_url": self.documentation_url,
            "health_status": "not_checked",
            "health_checked_at": None,
            "requested_scopes": list(self.requested_scopes),
            "supported_products": list(self.supported_products),
            "risk_policy": risk_policy,
            "oauth_profile": {
                "status": "discovery_ready" if self.connection_ready else "not_configured",
                "provider_slug": self.provider_slug,
            },
            "author_website_url": self.author_website_url,
            "support_url": self.support_url,
            "privacy_policy_url": self.privacy_policy_url,
            "catalog_badges": badges,
            "trusted_logo_key": self.trusted_logo_key,
            "tool_categories": catalog_metadata["tool_categories"],
            "tool_risk_summary": tool_risk_summary,
            "package_metadata": {
                "provider_slug": self.provider_slug,
                "auth_type": "oauth",
                "tools": tools,
                "tool_preview": tool_preview,
                "tool_categories": catalog_metadata["tool_categories"],
                "supported_products": list(self.supported_products),
                "risk_policy": risk_policy,
                "trusted_logo_key": self.trusted_logo_key,
            },
            "oauth_requirements": {
                "type": "oauth",
                "requested_scopes": list(self.requested_scopes),
                "scope_mode": self.scope_mode,
                "scope_note": self.scope_note,
            },
            "categories": list(self.categories),
            "official": True,
            "verified": True,
            "raw_metadata": {
                "schema_version": 1,
                "server": {
                    "homepage": self.author_website_url,
                    "documentationUrl": self.documentation_url,
                    "supportUrl": self.support_url,
                    "privacyPolicyUrl": self.privacy_policy_url,
                    "remotes": [
                        {
                            "type": self.transport,
                            "url": self.remote_url,
                            "securitySchemes": {"type": "oauth2"},
                        }
                    ],
                },
                "catalog": catalog_metadata,
            },
            # Curated logos are served from local assets in Phase 6. Never
            # populate a third-party remote image URL from this catalog.
            "logo_url": None,
            "tool_count": len(tool_preview),
            "verification_reason": "Code-reviewed official remote MCP endpoint.",
            "trust_status": "approved",
            "verification_source": self.documentation_url,
            "verified_at": CATALOG_REVIEWED_AT,
            "popularity_rank": self.popularity_rank,
            "catalog_status": self.catalog_status
            or ("oauth_discovery_ready" if self.connection_ready else "oauth_profile_required"),
            "enrichment_error": None,
        }


GOOGLE_DOCUMENTATION_URL = "https://developers.google.com/workspace/guides/configure-mcp-servers"
GOOGLE_WEBSITE_URL = "https://workspace.google.com/"
GOOGLE_SUPPORT_URL = "https://support.google.com/"
GOOGLE_PRIVACY_URL = "https://policies.google.com/privacy"
GITHUB_DOCUMENTATION_URL = "https://github.com/github/github-mcp-server"
GITHUB_WEBSITE_URL = "https://github.com/"
GITHUB_SUPPORT_URL = "https://support.github.com/"
GITHUB_PRIVACY_URL = "https://docs.github.com/site-policy/privacy-policies/github-privacy-statement"
NOTION_DOCUMENTATION_URL = "https://developers.notion.com/guides/mcp/get-started-with-mcp"
NOTION_WEBSITE_URL = "https://www.notion.so/"
NOTION_SUPPORT_URL = "https://www.notion.so/help"
NOTION_PRIVACY_URL = "https://www.notion.so/help/privacy"
SLACK_DOCUMENTATION_URL = "https://docs.slack.dev/ai/slack-mcp-server/"
SLACK_WEBSITE_URL = "https://slack.com/"
SLACK_SUPPORT_URL = "https://slack.com/help"
SLACK_PRIVACY_URL = "https://slack.com/trust/privacy-policy"

SLACK_MCP_READ_SCOPES = (
    "search:read.public",
    "search:read.private",
    "search:read.mpim",
    "search:read.im",
    "search:read.files",
    "files:read",
    "search:read.users",
    "emoji:read",
    "channels:read",
    "groups:read",
    "mpim:read",
    "channels:history",
    "groups:history",
    "mpim:history",
    "im:history",
    "users:read",
    "users:read.email",
    "canvases:read",
)
SLACK_MCP_WRITE_SCOPES = (
    "chat:write",
    "channels:write",
    "groups:write",
    "im:write",
    "mpim:write",
    "reactions:write",
    "canvases:write",
)
SLACK_MCP_SCOPES = SLACK_MCP_READ_SCOPES + SLACK_MCP_WRITE_SCOPES


OFFICIAL_MCP_PROVIDERS: tuple[CuratedMCPProvider, ...] = (
    CuratedMCPProvider(
        provider_slug="google-gmail",
        display_name="Google Gmail",
        publisher="Google",
        description="Search Gmail, read threads, manage labels, and create email drafts with user approval.",
        remote_url="https://gmailmcp.googleapis.com/mcp/v1",
        documentation_url=GOOGLE_DOCUMENTATION_URL,
        author_website_url=GOOGLE_WEBSITE_URL,
        support_url=GOOGLE_SUPPORT_URL,
        privacy_policy_url=GOOGLE_PRIVACY_URL,
        categories=("Communication", "Productivity"),
        supported_products=("Gmail",),
        requested_scopes=(
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        ),
        tool_preview=(
            CuratedMCPTool("search_threads", "Search Gmail threads.", "Email", ("read",)),
            CuratedMCPTool("get_thread", "Read a Gmail thread.", "Email", ("read",)),
            CuratedMCPTool("create_draft", "Create a Gmail draft for review.", "Email", ("write",)),
        ),
        availability="developer_preview",
        popularity_rank=1,
        trusted_logo_key="google",
    ),
    CuratedMCPProvider(
        provider_slug="google-drive",
        display_name="Google Drive",
        publisher="Google",
        description="Search, read, create, and copy Drive files with user approval.",
        remote_url="https://drivemcp.googleapis.com/mcp/v1",
        documentation_url=GOOGLE_DOCUMENTATION_URL,
        author_website_url=GOOGLE_WEBSITE_URL,
        support_url=GOOGLE_SUPPORT_URL,
        privacy_policy_url=GOOGLE_PRIVACY_URL,
        categories=("Files", "Productivity"),
        supported_products=("Google Drive",),
        requested_scopes=(
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
        ),
        tool_preview=(
            CuratedMCPTool("search_files", "Search files in Google Drive.", "Files", ("read",)),
            CuratedMCPTool("read_file_content", "Read a Drive file's content.", "Files", ("read",)),
            CuratedMCPTool("create_file", "Create a file in Google Drive.", "Files", ("write",)),
        ),
        availability="developer_preview",
        popularity_rank=2,
        trusted_logo_key="google",
    ),
    CuratedMCPProvider(
        provider_slug="google-calendar",
        display_name="Google Calendar",
        publisher="Google",
        description="View availability and calendar events, then create or update events with approval.",
        remote_url="https://calendarmcp.googleapis.com/mcp/v1",
        documentation_url=GOOGLE_DOCUMENTATION_URL,
        author_website_url=GOOGLE_WEBSITE_URL,
        support_url=GOOGLE_SUPPORT_URL,
        privacy_policy_url=GOOGLE_PRIVACY_URL,
        categories=("Productivity", "Planning"),
        supported_products=("Google Calendar",),
        requested_scopes=(
            "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
            "https://www.googleapis.com/auth/calendar.events.freebusy",
            "https://www.googleapis.com/auth/calendar.events.readonly",
        ),
        tool_preview=(
            CuratedMCPTool("list_events", "List calendar events.", "Calendar", ("read",)),
            CuratedMCPTool("create_event", "Create a calendar event.", "Calendar", ("write",)),
            CuratedMCPTool("delete_event", "Delete a calendar event.", "Calendar", ("delete",)),
        ),
        availability="developer_preview",
        popularity_rank=3,
        trusted_logo_key="google",
    ),
    CuratedMCPProvider(
        provider_slug="google-chat",
        display_name="Google Chat",
        publisher="Google",
        description="Search and read Google Chat messages, then send messages with approval.",
        remote_url="https://chatmcp.googleapis.com/mcp/v1",
        documentation_url=GOOGLE_DOCUMENTATION_URL,
        author_website_url=GOOGLE_WEBSITE_URL,
        support_url=GOOGLE_SUPPORT_URL,
        privacy_policy_url=GOOGLE_PRIVACY_URL,
        categories=("Communication", "Productivity"),
        supported_products=("Google Chat",),
        requested_scopes=(
            "https://www.googleapis.com/auth/chat.spaces.readonly",
            "https://www.googleapis.com/auth/chat.memberships.readonly",
            "https://www.googleapis.com/auth/chat.messages.readonly",
            "https://www.googleapis.com/auth/chat.messages.create",
            "https://www.googleapis.com/auth/chat.users.readstate.readonly",
        ),
        tool_preview=(
            CuratedMCPTool(
                "search_messages", "Search Google Chat messages.", "Messages", ("read",)
            ),
            CuratedMCPTool(
                "list_messages", "List messages in a Chat space.", "Messages", ("read",)
            ),
            CuratedMCPTool(
                "send_message",
                "Send a Google Chat message.",
                "Messages",
                ("write", "external_message"),
            ),
        ),
        availability="developer_preview",
        popularity_rank=4,
        trusted_logo_key="google",
    ),
    CuratedMCPProvider(
        provider_slug="google-people",
        display_name="Google People",
        publisher="Google",
        description="Read the signed-in user's profile and search contacts or directory people.",
        remote_url="https://people.googleapis.com/mcp/v1",
        documentation_url=GOOGLE_DOCUMENTATION_URL,
        author_website_url=GOOGLE_WEBSITE_URL,
        support_url=GOOGLE_SUPPORT_URL,
        privacy_policy_url=GOOGLE_PRIVACY_URL,
        categories=("People", "Productivity"),
        supported_products=("People API",),
        requested_scopes=(
            "https://www.googleapis.com/auth/directory.readonly",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/contacts.readonly",
        ),
        tool_preview=(
            CuratedMCPTool(
                "get_user_profile",
                "Read the signed-in user's profile.",
                "People",
                ("read",),
            ),
            CuratedMCPTool("search_contacts", "Search the user's contacts.", "People", ("read",)),
            CuratedMCPTool(
                "search_directory_people",
                "Search the Workspace directory.",
                "People",
                ("read",),
            ),
        ),
        availability="developer_preview",
        popularity_rank=5,
        trusted_logo_key="google",
    ),
    CuratedMCPProvider(
        provider_slug="github",
        display_name="GitHub",
        publisher="GitHub",
        description="Use GitHub's hosted MCP server to work with repositories, issues, pull requests, and workflows.",
        remote_url="https://api.githubcopilot.com/mcp/",
        documentation_url=GITHUB_DOCUMENTATION_URL,
        author_website_url=GITHUB_WEBSITE_URL,
        support_url=GITHUB_SUPPORT_URL,
        privacy_policy_url=GITHUB_PRIVACY_URL,
        categories=("Development", "Productivity"),
        supported_products=("GitHub", "GitHub Copilot"),
        requested_scopes=(),
        tool_preview=(),
        availability="host_oauth_configuration_required",
        popularity_rank=6,
        trusted_logo_key="github",
        scope_mode="provider_negotiated",
        scope_note="The reviewed AverQel GitHub OAuth profile will declare the exact requested scopes in Phase 3.",
    ),
    CuratedMCPProvider(
        provider_slug="notion",
        display_name="Notion",
        publisher="Notion",
        description="Search, read, and update workspace content through Notion's official remote MCP server.",
        remote_url="https://mcp.notion.com/mcp",
        documentation_url=NOTION_DOCUMENTATION_URL,
        author_website_url=NOTION_WEBSITE_URL,
        support_url=NOTION_SUPPORT_URL,
        privacy_policy_url=NOTION_PRIVACY_URL,
        categories=("Knowledge", "Productivity"),
        supported_products=("Notion",),
        requested_scopes=(),
        tool_preview=(),
        availability="developer_preview",
        popularity_rank=7,
        trusted_logo_key="notion",
        scope_mode="provider_negotiated",
        scope_note=(
            "Notion negotiates OAuth scopes during MCP discovery. AverQel uses PKCE, "
            "dynamic client registration, encrypted token storage, and live tool discovery."
        ),
        catalog_status="oauth_discovery_ready",
        connection_ready=True,
    ),
    CuratedMCPProvider(
        provider_slug="slack",
        display_name="Slack",
        publisher="Slack",
        description="Search and read Slack messages, files, channels, users, and canvases through Slack's official MCP server.",
        remote_url="https://mcp.slack.com/mcp",
        documentation_url=SLACK_DOCUMENTATION_URL,
        author_website_url=SLACK_WEBSITE_URL,
        support_url=SLACK_SUPPORT_URL,
        privacy_policy_url=SLACK_PRIVACY_URL,
        categories=("Communication", "Productivity"),
        supported_products=("Slack",),
        requested_scopes=SLACK_MCP_SCOPES,
        tool_preview=(
            CuratedMCPTool(
                "slack_search_messages",
                "Search public and private Slack messages the user can access.",
                "Messages",
                ("read",),
            ),
            CuratedMCPTool(
                "slack_search_files",
                "Search Slack files and retrieve permitted file content.",
                "Files",
                ("read",),
            ),
            CuratedMCPTool(
                "slack_read_channel",
                "Read the message history of an accessible Slack channel.",
                "Messages",
                ("read",),
            ),
            CuratedMCPTool(
                "slack_read_thread",
                "Read a complete Slack message thread.",
                "Messages",
                ("read",),
            ),
            CuratedMCPTool(
                "slack_search_users",
                "Search users and profiles in the connected Slack workspace.",
                "People",
                ("read",),
            ),
            CuratedMCPTool(
                "slack_search_channels",
                "Search accessible public and private Slack channels.",
                "Channels",
                ("read",),
            ),
            CuratedMCPTool(
                "slack_send_message",
                "Send a Slack message after explicit user approval.",
                "Messages",
                ("write", "external_message"),
            ),
            CuratedMCPTool(
                "slack_create_channel",
                "Create a Slack channel after explicit user approval.",
                "Channels",
                ("write",),
            ),
            CuratedMCPTool(
                "slack_create_conversation",
                "Create a Slack direct or group conversation after approval.",
                "Messages",
                ("write", "external_message"),
            ),
            CuratedMCPTool(
                "slack_add_reaction",
                "Add a reaction to a Slack message after approval.",
                "Messages",
                ("write", "external_message"),
            ),
            CuratedMCPTool(
                "slack_create_canvas",
                "Create a Slack canvas after explicit user approval.",
                "Canvases",
                ("write",),
            ),
            CuratedMCPTool(
                "slack_update_canvas",
                "Update a Slack canvas after explicit user approval.",
                "Canvases",
                ("write",),
            ),
        ),
        availability="developer_preview",
        popularity_rank=8,
        trusted_logo_key="slack",
        scope_note=(
            "Requires an approved Slack app with confidential OAuth credentials. "
            "AverQel requests the reviewed read and write user scopes. Read actions "
            "are read-only; write and external-message actions require approval."
        ),
    ),
)


def validate_official_mcp_catalog() -> None:
    """Fail fast when a future edit violates static catalog safety rules."""
    slugs: set[str] = set()
    ranks: set[int] = set()
    for provider in OFFICIAL_MCP_PROVIDERS:
        if provider.provider_slug in slugs:
            raise ValueError(f"Duplicate curated MCP provider slug: {provider.provider_slug}")
        slugs.add(provider.provider_slug)
        if provider.popularity_rank in ranks:
            raise ValueError(f"Duplicate curated MCP popularity rank: {provider.popularity_rank}")
        ranks.add(provider.popularity_rank)

        for label, value in (
            ("remote endpoint", provider.remote_url),
            ("documentation URL", provider.documentation_url),
            ("author website URL", provider.author_website_url),
            ("support URL", provider.support_url),
            ("privacy URL", provider.privacy_policy_url),
        ):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"Curated MCP {label} is not a safe HTTPS URL: {value}")
        if provider.transport != "streamable_http":
            raise ValueError(f"Unsupported curated MCP transport: {provider.transport}")
        if any(
            not scope
            or any(character.isspace() for character in scope)
            or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/"
                for character in scope
            )
            for scope in provider.requested_scopes
        ):
            raise ValueError(
                f"Curated MCP provider has an invalid OAuth scope: {provider.provider_slug}"
            )


validate_official_mcp_catalog()
