"""Reviewed OAuth profiles for AverQel's curated remote MCP providers.

This module contains public protocol metadata and validation rules only. Client
credentials are read from ``Settings`` at request time and are never returned
by readiness checks, serialized into server configuration, or written to MCP
events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx

if TYPE_CHECKING:
    from app.core.config import Settings


GOOGLE_PROVIDER_SLUGS = frozenset(
    {
        "google-gmail",
        "google-drive",
        "google-calendar",
        "google-chat",
        "google-people",
    }
)


@dataclass(frozen=True, slots=True)
class MCPProviderOAuthProfile:
    """Static, code-reviewed OAuth contract for one provider family."""

    key: str
    label: str
    provider_slugs: frozenset[str]
    authorization_endpoint: str
    token_endpoint: str
    identity_endpoint: str
    identity_email_endpoint: str | None
    revocation_endpoint: str | None
    revocation_method: str = "post"
    scopes_by_provider: dict[str, tuple[str, ...]] | None = None
    default_scopes: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    token_endpoint_auth_method: str = "client_secret_post"
    extra_authorization_params: tuple[tuple[str, str], ...] = ()

    def matches(self, provider_slug: str | None) -> bool:
        return bool(provider_slug and provider_slug in self.provider_slugs)

    def scopes_for(self, provider_slug: str) -> tuple[str, ...]:
        if self.scopes_by_provider and provider_slug in self.scopes_by_provider:
            return self.scopes_by_provider[provider_slug]
        return self.default_scopes

    def configured_credentials(self, settings: Settings) -> tuple[str, str, tuple[str, ...]]:
        id_name = f"mcp_{self.key}_oauth_client_id"
        secret_name = f"mcp_{self.key}_oauth_client_secret"
        client_id = str(getattr(settings, id_name, "") or "").strip()
        client_secret = str(getattr(settings, secret_name, "") or "").strip()
        missing: list[str] = []
        if not client_id:
            missing.append(id_name.upper())
        if not client_secret:
            missing.append(secret_name.upper())
        return client_id, client_secret, tuple(missing)

    def readiness(self, settings: Settings) -> tuple[bool, str | None]:
        _, _, missing = self.configured_credentials(settings)
        if missing:
            return (
                False,
                f"{self.label} MCP OAuth is not configured: {', '.join(missing)}.",
            )
        if not (settings.mcp_oauth_redirect_uri or settings.averqel_public_origin):
            return False, "MCP OAuth callback URL is not configured."
        return True, None

    def authorization_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scopes: tuple[str, ...],
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": " ".join(scopes),
        }
        params.update(dict(self.extra_authorization_params))
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    def verify_scopes(
        self,
        *,
        provider_slug: str,
        granted_scope: str | None,
    ) -> tuple[str, ...]:
        """Reject scope escalation and incomplete provider authorization."""
        expected = set(self.scopes_for(provider_slug))
        required = set(self.required_scopes)
        # OAuth providers do not all serialize the returned scope list the
        # same way.  Google returns a space-delimited value while GitHub
        # returns comma-delimited scopes (and may include optional spaces).
        # Normalize both forms before applying the strict allowlist below.
        granted = {
            item.strip()
            for item in str(granted_scope or "").replace(",", " ").split()
            if item.strip()
        }
        if not granted:
            raise ValueError("OAuth provider did not return granted scopes")
        unexpected = granted - expected
        if unexpected:
            raise ValueError("OAuth provider returned an unapproved scope")
        missing = required - granted
        if missing:
            raise ValueError("OAuth provider did not grant the required scopes")
        return tuple(sorted(granted))

    def identity_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    def identity_endpoints(self, provider_slug: str) -> tuple[str, ...]:
        """Return provider-specific identity endpoints in safe fallback order.

        Google userinfo is not authorized by every curated service scope. Gmail
        can identify the connected mailbox through its read-only profile
        endpoint, so a Gmail OAuth connection does not need to request the
        broader userinfo.profile scope merely to display its account label.
        """
        if provider_slug == "google-gmail":
            return (
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                self.identity_endpoint,
            )
        return (self.identity_endpoint,)

    def extract_identity(
        self,
        payload: object,
        email_payload: object | None = None,
    ) -> dict[str, str | int]:
        """Return a small non-secret account label for the installed server."""
        data = payload if isinstance(payload, dict) else {}
        identity: dict[str, str | int] = {}
        subject = data.get("sub") or data.get("id")
        email = data.get("email") or data.get("emailAddress")
        display_name = data.get("name") or data.get("login") or data.get("email")
        if isinstance(subject, str | int) and str(subject).strip():
            identity["provider_subject"] = subject
            identity["account_id"] = subject
        if isinstance(email, str) and email.strip():
            identity["email"] = email.strip().lower()
        if not identity.get("email") and isinstance(email_payload, list):
            for item in email_payload:
                if (
                    isinstance(item, dict)
                    and item.get("primary")
                    and isinstance(item.get("email"), str)
                ):
                    identity["email"] = str(item["email"]).strip().lower()
                    break
        if isinstance(display_name, str) and display_name.strip():
            identity["display_name"] = display_name.strip()[:240]
        if not identity:
            raise ValueError("OAuth account identity could not be verified")
        return identity

    def oauth_metadata(self, *, scopes: tuple[str, ...]) -> dict[str, object]:
        """Build the metadata shape consumed by the MCP runtime SDK."""
        return {
            "issuer": self.authorization_endpoint,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "revocation_endpoint": self.revocation_endpoint,
            "scopes_supported": list(scopes),
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": [self.token_endpoint_auth_method],
            "code_challenge_methods_supported": ["S256"],
        }

    def protected_resource_metadata(
        self, *, resource_url: str, scopes: tuple[str, ...]
    ) -> dict[str, object]:
        return {
            "resource": resource_url,
            "authorization_servers": [self.authorization_endpoint],
            "scopes_supported": list(scopes),
            "bearer_methods_supported": ["header"],
        }


GOOGLE_MCP_OAUTH_PROFILE = MCPProviderOAuthProfile(  # nosec B106 - protocol endpoint profile
    key="google",
    label="Google",
    provider_slugs=GOOGLE_PROVIDER_SLUGS,
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    identity_endpoint="https://www.googleapis.com/oauth2/v3/userinfo",
    identity_email_endpoint=None,
    revocation_endpoint="https://oauth2.googleapis.com/revoke",
    scopes_by_provider={
        "google-gmail": (
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        ),
        "google-drive": (
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
        ),
        "google-calendar": (
            "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
            "https://www.googleapis.com/auth/calendar.events.freebusy",
            "https://www.googleapis.com/auth/calendar.events.readonly",
        ),
        "google-chat": (
            "https://www.googleapis.com/auth/chat.spaces.readonly",
            "https://www.googleapis.com/auth/chat.memberships.readonly",
            "https://www.googleapis.com/auth/chat.messages.readonly",
            "https://www.googleapis.com/auth/chat.messages.create",
            "https://www.googleapis.com/auth/chat.users.readstate.readonly",
        ),
        "google-people": (
            "https://www.googleapis.com/auth/directory.readonly",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/contacts.readonly",
        ),
    },
    required_scopes=(),
    extra_authorization_params=(
        ("access_type", "offline"),
        ("prompt", "consent"),
    ),
)


GITHUB_MCP_OAUTH_PROFILE = MCPProviderOAuthProfile(  # nosec B106 - protocol endpoint profile
    key="github",
    label="GitHub",
    provider_slugs=frozenset({"github"}),
    authorization_endpoint="https://github.com/login/oauth/authorize",
    token_endpoint="https://github.com/login/oauth/access_token",
    identity_endpoint="https://api.github.com/user",
    identity_email_endpoint="https://api.github.com/user/emails",
    # GitHub's OAuth-authorizations API revokes one app grant at this
    # endpoint.  The access token is supplied in the JSON request body.
    revocation_endpoint="https://api.github.com/applications/{client_id}/grant",
    revocation_method="delete_basic",
    default_scopes=("read:user", "user:email", "repo"),
    required_scopes=("read:user", "user:email", "repo"),
)


MCP_PROVIDER_OAUTH_PROFILES = (
    GOOGLE_MCP_OAUTH_PROFILE,
    GITHUB_MCP_OAUTH_PROFILE,
)


def get_mcp_provider_profile(
    provider_slug: str | None,
) -> MCPProviderOAuthProfile | None:
    for profile in MCP_PROVIDER_OAUTH_PROFILES:
        if profile.matches(provider_slug):
            return profile
    return None


def validate_mcp_provider_profile_url(url: str) -> str:
    parsed = httpx.URL(url)
    if parsed.scheme != "https" or not parsed.host or parsed.username or parsed.password:
        raise ValueError("MCP provider OAuth endpoints must be HTTPS URLs without credentials")
    return str(parsed)
