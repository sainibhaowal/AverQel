from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import Settings
from app.integrations.models.mcp_server import (
    MCPOAuthToken,
    MCPOAuthTransaction,
    MCPServer,
)
from app.integrations.repositories.mcp_events import MCPEventsRepository
from app.integrations.services.connector_oauth_service import ConnectorOAuthService
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto


class MCPServerOAuthService:
    """Generic MCP OAuth broker for tenant-owned remote endpoints.

    OAuth transaction material is encrypted separately from the server record.
    The server JSON configuration contains no PKCE verifier, OAuth state, or
    client metadata.
    """

    TRANSACTION_TTL = timedelta(minutes=10)

    def __init__(self, db: Any, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.helper = ConnectorOAuthService(db, settings)

    def verify_state(self, state: str) -> dict[str, Any]:
        """Verify callback integrity before any tenant-scoped database read."""
        return self.helper._verify_state(state)

    @staticmethod
    def _state_hash(state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    @staticmethod
    def _transaction_aad(transaction: MCPOAuthTransaction) -> bytes:
        return (
            f"mcp_oauth_transaction:{transaction.tenant_id}:"
            f"{transaction.server_id}:{transaction.id}"
        ).encode()

    def _decrypt_token_credentials(self, server: MCPServer) -> dict[str, Any]:
        record = self.db.execute(
            select(MCPOAuthToken).where(
                MCPOAuthToken.server_id == server.id,
                MCPOAuthToken.tenant_id == server.tenant_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return {}
        crypto = ConnectorSecretCrypto(self.settings)
        try:
            payload = json.loads(
                crypto.decrypt(
                    ciphertext=record.secret_ciphertext,
                    nonce=record.secret_nonce,
                    kid=record.secret_kid,
                    aad=str(server.tenant_id).encode(),
                ).decode("utf-8")
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Unable to read existing MCP credentials") from exc
        if not isinstance(payload, dict):
            raise ValueError("Stored MCP credentials are invalid")
        return payload

    def _load_transaction(
        self,
        *,
        server: MCPServer,
        state: str,
        state_payload: dict[str, Any],
    ) -> tuple[MCPOAuthTransaction | None, dict[str, Any] | None]:
        raw_transaction_id = state_payload.get("transaction_id")
        try:
            transaction_id = uuid.UUID(str(raw_transaction_id))
        except (TypeError, ValueError):
            transaction_id = None

        statement = select(MCPOAuthTransaction).where(
            MCPOAuthTransaction.tenant_id == server.tenant_id,
            MCPOAuthTransaction.user_id == server.user_id,
            MCPOAuthTransaction.server_id == server.id,
            MCPOAuthTransaction.state_hash == self._state_hash(state),
        )
        if transaction_id is not None:
            statement = statement.where(MCPOAuthTransaction.id == transaction_id)
        transaction = self.db.execute(statement.with_for_update()).scalar_one_or_none()
        if transaction is None:
            return None, None
        if transaction.consumed_at is not None:
            raise ValueError("OAuth transaction has already been consumed")
        if datetime.now(UTC) >= transaction.expires_at:
            raise ValueError("OAuth transaction has expired")

        crypto = ConnectorSecretCrypto(self.settings)
        try:
            payload = json.loads(
                crypto.decrypt(
                    ciphertext=transaction.secret_ciphertext,
                    nonce=transaction.secret_nonce,
                    kid=transaction.secret_kid,
                    aad=self._transaction_aad(transaction),
                ).decode("utf-8")
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Unable to read MCP OAuth transaction") from exc
        if not isinstance(payload, dict):
            raise ValueError("MCP OAuth transaction payload is invalid")
        return transaction, payload

    @staticmethod
    def _validate_legacy_pending(server: MCPServer, state: str) -> dict[str, Any] | None:
        pending = (server.config or {}).get("oauth_pending")
        if not isinstance(pending, dict) or pending.get("state") != state:
            return None
        expires_at = pending.get("expires_at")
        if expires_at:
            try:
                expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("OAuth transaction has an invalid expiry") from exc
            if datetime.now(UTC) >= expires:
                raise ValueError("OAuth transaction has expired")
        return pending

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

        resource_metadata, oauth_metadata = self.helper._discover_mcp_metadata(
            server.config["server_url"]
        )
        pkce = self.helper._generate_pkce()
        from mcp.client.auth.utils import get_client_metadata_scopes
        from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata

        scope = get_client_metadata_scopes(None, resource_metadata, oauth_metadata) or ""
        metadata = OAuthClientMetadata(
            redirect_uris=[redirect_uri],
            token_endpoint_auth_method="none",
            scope=scope,
            client_name="AverQel",
            client_uri=self.helper._public_origin(),
            software_id="averqel",
            software_version="1.0",
        )

        existing_credentials = self._decrypt_token_credentials(server)
        client_info_data = existing_credentials.get("client_info")
        if not isinstance(client_info_data, dict):
            client_info_data = (server.config or {}).get("oauth_client_info")
        if isinstance(client_info_data, dict):
            client_info = OAuthClientInformationFull.model_validate(client_info_data)
        else:
            client_info = self.helper._register_client(
                oauth_metadata=oauth_metadata,
                client_metadata=metadata,
                server_url=server.config["server_url"],
            )

        transaction_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + self.TRANSACTION_TTL
        state_payload = {
            "mcp_server_id": str(server.id),
            "tenant_id": str(server.tenant_id),
            "user_id": str(user_id),
            "transaction_id": str(transaction_id),
            "nonce": secrets.token_urlsafe(24),
            "issued_at": datetime.now(UTC).isoformat(),
        }
        state = self.helper._sign_state(state_payload)
        transaction = MCPOAuthTransaction(
            id=transaction_id,
            tenant_id=server.tenant_id,
            user_id=user_id,
            server_id=server.id,
            state_hash=self._state_hash(state),
            expires_at=expires_at,
        )
        encrypted = ConnectorSecretCrypto(self.settings).encrypt(
            json.dumps(
                {
                    "code_verifier": pkce["code_verifier"],
                    "client_info": client_info.model_dump(mode="json", exclude_none=True),
                    "client_metadata": metadata.model_dump(mode="json", exclude_none=True),
                    "resource_metadata": resource_metadata.model_dump(mode="json", exclude_none=True),
                    "oauth_metadata": oauth_metadata.model_dump(mode="json", exclude_none=True),
                },
                separators=(",", ":"),
            ),
            aad=self._transaction_aad(transaction),
        )
        transaction.secret_ciphertext = encrypted.ciphertext
        transaction.secret_nonce = encrypted.nonce
        transaction.secret_kid = encrypted.kid
        self.db.add(transaction)

        config = dict(server.config or {})
        config.pop("oauth_pending", None)
        config["oauth_transaction_id"] = str(transaction.id)
        server.config = config
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
            oauth_metadata=oauth_metadata,
            client_info=client_info,
            client_metadata=metadata,
            resource_metadata=resource_metadata,
            state=state,
            code_challenge=pkce["code_challenge"],
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
        if datetime.now(UTC) - issued > self.TRANSACTION_TTL:
            raise ValueError("OAuth state has expired")

        transaction, pending = self._load_transaction(
            server=server, state=state, state_payload=payload
        )
        if pending is None:
            # Compatibility for OAuth flows started before the encrypted
            # transaction migration. New flows never write this field.
            pending = self._validate_legacy_pending(server, state)
        if pending is None:
            raise ValueError("OAuth transaction is missing or expired")

        from mcp.shared.auth import (
            OAuthClientInformationFull,
            OAuthClientMetadata,
            OAuthMetadata,
            ProtectedResourceMetadata,
        )

        token = self.helper._exchange_token(
            oauth_metadata=OAuthMetadata.model_validate(pending["oauth_metadata"]),
            client_info=OAuthClientInformationFull.model_validate(pending["client_info"]),
            resource_metadata=ProtectedResourceMetadata.model_validate(pending["resource_metadata"]),
            code=code,
            code_verifier=pending["code_verifier"],
            redirect_uri=str(
                OAuthClientMetadata.model_validate(pending["client_metadata"]).redirect_uris[0]
            ),
        )
        token_payload = token.model_dump(mode="json", exclude_none=True)
        existing_credentials = self._decrypt_token_credentials(server)
        existing_credentials.update(token_payload)
        existing_credentials.update(
            {
                "client_info": pending["client_info"],
                "client_metadata": pending["client_metadata"],
                "oauth_metadata": pending["oauth_metadata"],
                "resource_metadata": pending["resource_metadata"],
            }
        )
        encrypted = ConnectorSecretCrypto(self.settings).encrypt(
            json.dumps(existing_credentials, separators=(",", ":")),
            aad=str(server.tenant_id).encode(),
        )
        token_expires_in = getattr(token, "expires_in", None)
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=int(token_expires_in))
            if token_expires_in is not None
            else None
        )
        record = self.db.query(MCPOAuthToken).filter(
            MCPOAuthToken.server_id == server.id,
            MCPOAuthToken.tenant_id == server.tenant_id,
        ).one_or_none()
        if record is None:
            record = MCPOAuthToken(
                tenant_id=server.tenant_id,
                server_id=server.id,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
                expires_at=expires_at,
            )
            self.db.add(record)
        else:
            record.secret_ciphertext = encrypted.ciphertext
            record.secret_nonce = encrypted.nonce
            record.secret_kid = encrypted.kid
            record.expires_at = expires_at

        server.config = {
            key: value
            for key, value in (server.config or {}).items()
            if key not in {
                "oauth_pending",
                "oauth_transaction_id",
                "oauth_client_info",
                "client_metadata",
                "oauth_metadata",
                "resource_metadata",
            }
        }
        server.config["auth_mode"] = "mcp"
        server.status = "disconnected"
        if transaction is not None:
            transaction.consumed_at = datetime.now(UTC)
        self.db.add(server)
        MCPEventsRepository(self.db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=server.user_id,
            event_type="oauth_completed",
            payload={"provider": server.config.get("vendor_slug")},
        )
        self.db.commit()
