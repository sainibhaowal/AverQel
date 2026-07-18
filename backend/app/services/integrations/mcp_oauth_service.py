from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.models.integrations.mcp_server import MCPOAuthToken, MCPServer
from app.services.integrations.connector_oauth_service import ConnectorOAuthService
from app.services.security.connector_secret_crypto import ConnectorSecretCrypto
from app.repositories.mcp_events import MCPEventsRepository


class MCPServerOAuthService:
    """Generic MCP OAuth broker for official server endpoints."""

    def __init__(self, db: Any, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.helper = ConnectorOAuthService(db, settings)

    def verify_state(self, state: str) -> dict[str, Any]:
        """Verify callback integrity before any tenant-scoped database read."""
        return self.helper._verify_state(state)

    def start(self, *, server: MCPServer, user_id: uuid.UUID) -> str:
        if server.user_id != user_id:
            raise ValueError("MCP server does not belong to this user")
        if not server.config.get("server_url"):
            raise ValueError("This MCP vendor does not publish a remote endpoint")
        origin = self.helper._public_origin()
        redirect_uri = (
            f"{origin}{self.settings.api_prefix}/mcp/servers/{server.id}/oauth/callback"
            if origin
            else None
        )
        if not redirect_uri:
            raise ValueError("MCP OAuth callback URL is not configured")
        resource_metadata, oauth_metadata = self.helper._discover_mcp_metadata(server.config["server_url"])
        pkce = self.helper._generate_pkce()
        from mcp.client.auth.utils import get_client_metadata_scopes
        from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata
        scope = get_client_metadata_scopes(None, resource_metadata, oauth_metadata) or ""
        metadata = OAuthClientMetadata(
            redirect_uris=[redirect_uri], token_endpoint_auth_method="none",
            scope=scope, client_name="AverQel", client_uri=self.helper._public_origin(),
            software_id="averqel", software_version="1.0",
        )
        client_info_data = server.config.get("oauth_client_info")
        if isinstance(client_info_data, dict):
            client_info = OAuthClientInformationFull.model_validate(client_info_data)
        else:
            client_info = self.helper._register_client(
                oauth_metadata=oauth_metadata,
                client_metadata=metadata,
                server_url=server.config["server_url"],
            )
        state_payload = {
            "mcp_server_id": str(server.id), "tenant_id": str(server.tenant_id),
            "user_id": str(user_id), "nonce": secrets.token_urlsafe(24),
            "issued_at": datetime.now(UTC).isoformat(),
        }
        state = self.helper._sign_state(state_payload)
        server.config = {
            **server.config,
            "oauth_pending": {
                "state": state, "code_verifier": pkce["code_verifier"],
                "client_info": client_info.model_dump(mode="json", exclude_none=True),
                "client_metadata": metadata.model_dump(mode="json", exclude_none=True),
                "resource_metadata": resource_metadata.model_dump(mode="json", exclude_none=True),
                "oauth_metadata": oauth_metadata.model_dump(mode="json", exclude_none=True),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            },
        }
        self.db.add(server)
        self.db.commit()
        MCPEventsRepository(self.db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=server.user_id,
            event_type="oauth_started",
            payload={"server_url": server.config.get("server_url")},
        )
        self.db.commit()
        return self.helper._build_authorization_url(
            oauth_metadata=oauth_metadata, client_info=client_info,
            client_metadata=metadata, resource_metadata=resource_metadata,
            state=state, code_challenge=pkce["code_challenge"],
        )

    def finish(self, *, server: MCPServer, code: str, state: str) -> None:
        payload = self.helper._verify_state(state)
        if (
            payload.get("mcp_server_id") != str(server.id)
            or payload.get("tenant_id") != str(server.tenant_id)
            or payload.get("user_id") != str(server.user_id)
        ):
            raise ValueError("OAuth state does not belong to this MCP server")
        issued_at = payload.get("issued_at")
        if not issued_at:
            raise ValueError("OAuth state is missing an issue time")
        try:
            issued = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("OAuth state has an invalid issue time") from exc
        if datetime.now(UTC) - issued > timedelta(minutes=10):
            raise ValueError("OAuth state has expired")
        pending = (server.config or {}).get("oauth_pending") or {}
        if pending.get("state") != state:
            raise ValueError("OAuth state is missing or expired")
        pending_expires = pending.get("expires_at")
        if pending_expires:
            try:
                expires = datetime.fromisoformat(str(pending_expires).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("OAuth transaction has an invalid expiry") from exc
            if datetime.now(UTC) >= expires:
                raise ValueError("OAuth transaction has expired")
        from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthMetadata, ProtectedResourceMetadata
        token = self.helper._exchange_token(
            oauth_metadata=OAuthMetadata.model_validate(pending["oauth_metadata"]),
            client_info=OAuthClientInformationFull.model_validate(pending["client_info"]),
            resource_metadata=ProtectedResourceMetadata.model_validate(pending["resource_metadata"]),
            code=code, code_verifier=pending["code_verifier"],
            redirect_uri=str(OAuthClientMetadata.model_validate(pending["client_metadata"]).redirect_uris[0]),
        )
        encrypted = ConnectorSecretCrypto(self.settings).encrypt(
            json.dumps(token.model_dump(mode="json", exclude_none=True)),
            aad=str(server.tenant_id).encode(),
        )
        expires_at = None
        token_expires_in = getattr(token, "expires_in", None)
        if token_expires_in is not None:
            expires_at = datetime.now(UTC) + timedelta(seconds=int(token_expires_in))
        record = self.db.query(MCPOAuthToken).filter(MCPOAuthToken.server_id == server.id).one_or_none()
        if record is None:
            record = MCPOAuthToken(tenant_id=server.tenant_id, server_id=server.id, secret_ciphertext=encrypted.ciphertext, secret_nonce=encrypted.nonce, secret_kid=encrypted.kid, expires_at=expires_at)
            self.db.add(record)
        else:
            record.secret_ciphertext, record.secret_nonce, record.secret_kid = encrypted.ciphertext, encrypted.nonce, encrypted.kid
            record.expires_at = expires_at
        server.config = {
            **server.config,
            "oauth_client_info": pending["client_info"],
            "client_metadata": pending["client_metadata"],
            "oauth_metadata": pending["oauth_metadata"],
            "resource_metadata": pending["resource_metadata"],
            "auth_mode": "mcp",
        }
        server.config.pop("oauth_pending", None)
        server.status = "disconnected"
        self.db.add(server)
        MCPEventsRepository(self.db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=server.user_id,
            event_type="oauth_completed",
            payload={"provider": server.config.get("vendor_slug")},
        )
        self.db.commit()
