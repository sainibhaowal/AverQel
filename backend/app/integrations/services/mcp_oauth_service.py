from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
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
from app.integrations.services.mcp_endpoint_security import validate_remote_endpoint
from app.integrations.services.mcp_http_client import build_safe_sync_client
from app.integrations.services.mcp_provider_auth import get_mcp_provider_profile


class MCPServerOAuthService:
    """Generic MCP OAuth broker for tenant-owned remote endpoints.

    OAuth transaction material is encrypted separately from the server record.
    The server JSON configuration contains no PKCE verifier, OAuth state, or
    client metadata.
    """

    TRANSACTION_TTL = timedelta(minutes=10)

    @staticmethod
    def _safe_scope_list(value: object) -> list[str]:
        if isinstance(value, str):
            return sorted({item for item in value.split() if item})
        if isinstance(value, list):
            return sorted({str(item).strip() for item in value if str(item).strip()})
        return []

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
                MCPOAuthToken.user_id == server.user_id,
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

    def _mcp_redirect_uri(self, server: MCPServer) -> str:
        configured = (self.settings.mcp_oauth_redirect_uri or "").strip().rstrip("/")
        if configured:
            return configured.replace("{server_id}", str(server.id))
        origin = self.helper._public_origin()
        if origin:
            return f"{origin}{self.settings.api_prefix}/mcp/oauth/callback"
        raise ValueError("MCP OAuth callback URL is not configured")

    def _static_profile(self, server: MCPServer):
        profile = get_mcp_provider_profile(server.provider_slug)
        if profile is None:
            return None
        ready, reason = profile.readiness(self.settings)
        if not ready:
            raise ValueError(reason or "MCP provider OAuth is not configured")
        return profile

    def _start_static_profile(self, *, server: MCPServer, user_id: uuid.UUID, profile: Any) -> str:
        from mcp.shared.auth import (
            OAuthClientInformationFull,
            OAuthClientMetadata,
            OAuthMetadata,
            ProtectedResourceMetadata,
        )

        client_id, client_secret, missing = profile.configured_credentials(self.settings)
        if missing:
            raise ValueError("MCP provider OAuth is not configured")
        redirect_uri = self._mcp_redirect_uri(server)
        scopes = profile.scopes_for(server.provider_slug or "")
        client_metadata = OAuthClientMetadata(
            redirect_uris=[redirect_uri],
            token_endpoint_auth_method=profile.token_endpoint_auth_method,
            scope=" ".join(scopes),
            client_name="AverQel",
            client_uri=self.helper._public_origin(),
            software_id="averqel",
            software_version="1.0",
        )
        client_info = OAuthClientInformationFull(
            **client_metadata.model_dump(mode="json", exclude_none=True),
            client_id=client_id,
            client_secret=client_secret,
        )
        oauth_metadata = OAuthMetadata.model_validate(
            profile.oauth_metadata(scopes=scopes)
        )
        resource_metadata = ProtectedResourceMetadata.model_validate(
            profile.protected_resource_metadata(
                resource_url=str(server.config.get("server_url") or ""),
                scopes=scopes,
            )
        )
        pkce = self.helper._generate_pkce()
        transaction_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + self.TRANSACTION_TTL
        state_payload = {
            "mcp_server_id": str(server.id),
            "tenant_id": str(server.tenant_id),
            "user_id": str(user_id),
            "provider_slug": server.provider_slug,
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
                    "provider_slug": server.provider_slug,
                    "code_verifier": pkce["code_verifier"],
                    "client_info": client_info.model_dump(mode="json", exclude_none=True),
                    "client_metadata": client_metadata.model_dump(mode="json", exclude_none=True),
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
        config["oauth_profile"] = profile.key
        server.config = config
        self.db.add(server)
        self.db.commit()
        MCPEventsRepository(self.db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=server.user_id,
            event_type="oauth_started",
            payload={"provider": profile.key},
        )
        self.db.commit()
        return profile.authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=pkce["code_challenge"],
            scopes=scopes,
        )

    def _exchange_static_token(
        self,
        *,
        profile: Any,
        client_id: str,
        client_secret: str,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> Any:
        form_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": code_verifier,
        }
        headers = {"Accept": "application/json"}
        with build_safe_sync_client(timeout=30.0) as client:
            response = client.post(profile.token_endpoint, data=form_data, headers=headers)
        if response.status_code != 200:
            raise ValueError("MCP OAuth token exchange failed")
        try:
            from mcp.shared.auth import OAuthToken

            return OAuthToken.model_validate(response.json())
        except Exception as exc:  # noqa: BLE001
            raise ValueError("MCP OAuth provider returned an invalid token") from exc

    def _fetch_static_identity(self, *, profile: Any, access_token: str) -> dict[str, str | int]:
        headers = profile.identity_headers(access_token)
        try:
            with build_safe_sync_client(timeout=15.0) as client:
                response = client.get(profile.identity_endpoint, headers=headers)
                if response.status_code == 200:
                    identity_payload = response.json()
                    email_payload = None
                    if profile.identity_email_endpoint:
                        email_response = client.get(profile.identity_email_endpoint, headers=headers)
                        if email_response.status_code == 200:
                            email_payload = email_response.json()
                    return profile.extract_identity(identity_payload, email_payload)
        except Exception:  # noqa: BLE001
            pass
        return {
            "provider_subject": f"{profile.key}-user",
            "account_id": f"{profile.key}-user",
            "display_name": f"{profile.label} Account",
        }

    def _finish_static_profile(
        self,
        *,
        server: MCPServer,
        code: str,
        state: str,
        state_payload: dict[str, Any],
        profile: Any,
    ) -> None:
        transaction, pending = self._load_transaction(
            server=server, state=state, state_payload=state_payload
        )
        if transaction is None or pending is None:
            raise ValueError("OAuth transaction is missing or expired")
        if pending.get("provider_slug") != server.provider_slug:
            raise ValueError("OAuth provider does not match this MCP server")
        client_id, client_secret, missing = profile.configured_credentials(self.settings)
        if missing:
            raise ValueError("MCP provider OAuth is not configured")
        token = self._exchange_static_token(
            profile=profile,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            code_verifier=str(pending.get("code_verifier") or ""),
            redirect_uri=str(
                pending.get("client_metadata", {}).get("redirect_uris", [""])[0]
            ),
        )
        granted_scopes = profile.verify_scopes(
            provider_slug=server.provider_slug or "",
            granted_scope=getattr(token, "scope", None),
        )
        identity = self._fetch_static_identity(
            profile=profile,
            access_token=str(token.access_token),
        )
        token_payload = token.model_dump(mode="json", exclude_none=True)
        token_payload.update(
            {
                "provider_slug": server.provider_slug,
                "scope": " ".join(granted_scopes),
                "client_info": pending["client_info"],
                "client_metadata": pending["client_metadata"],
                "oauth_metadata": pending["oauth_metadata"],
                "resource_metadata": pending["resource_metadata"],
            }
        )
        existing_credentials = self._decrypt_token_credentials(server)
        existing_credentials.update(token_payload)
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
            MCPOAuthToken.user_id == server.user_id,
        ).one_or_none()
        if record is None:
            record = MCPOAuthToken(
                tenant_id=server.tenant_id,
                user_id=server.user_id,
                server_id=server.id,
                registry_entry_id=server.registry_entry_id,
                provider_slug=server.provider_slug,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
                expires_at=expires_at,
                granted_scopes=granted_scopes,
            )
            self.db.add(record)
        else:
            record.secret_ciphertext = encrypted.ciphertext
            record.secret_nonce = encrypted.nonce
            record.secret_kid = encrypted.kid
            record.expires_at = expires_at
            record.granted_scopes = granted_scopes
        server.account_identity = identity
        server.config = {
            key: value
            for key, value in (server.config or {}).items()
            if key not in {"oauth_pending", "oauth_transaction_id", "oauth_client_info", "client_metadata", "oauth_metadata", "resource_metadata"}
        }
        server.status = "connected"
        server.enabled = True
        server.last_connected_at = datetime.now(UTC)
        server.last_error = None
        transaction.consumed_at = datetime.now(UTC)
        self.db.add(server)
        MCPEventsRepository(self.db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=server.user_id,
            event_type="oauth_completed",
            payload={"provider": profile.key},
        )
        self.db.commit()

    def disconnect(self, *, server: MCPServer, user_id: uuid.UUID) -> None:
        if server.user_id != user_id:
            raise ValueError("MCP server does not belong to this user")
        profile = get_mcp_provider_profile(server.provider_slug)
        record = self.db.execute(
            select(MCPOAuthToken).where(
                MCPOAuthToken.server_id == server.id,
                MCPOAuthToken.tenant_id == server.tenant_id,
                MCPOAuthToken.user_id == user_id,
            )
        ).scalar_one_or_none()
        if record is not None and profile is not None and profile.revocation_endpoint:
            credentials = self._decrypt_token_credentials(server)
            token_value = str(credentials.get("refresh_token") or credentials.get("access_token") or "").strip()
            if token_value:
                client_id, client_secret, _ = profile.configured_credentials(self.settings)
                if client_id and client_secret:
                    endpoint = profile.revocation_endpoint.format(client_id=client_id)
                    with build_safe_sync_client(timeout=15.0) as client:
                        if profile.revocation_method == "delete_basic":
                            response = client.delete(
                                endpoint,
                                headers={"Accept": "application/json"},
                                auth=httpx.BasicAuth(client_id, client_secret),
                            )
                        else:
                            response = client.post(endpoint, data={"token": token_value})
                    if response.status_code not in {200, 204}:
                        raise ValueError("OAuth provider token revocation failed")
        if record is not None:
            self.db.delete(record)
        server.account_identity = {}
        server.status = "needs_auth"
        server.config = {
            key: value
            for key, value in (server.config or {}).items()
            if key not in {"auth_mode", "oauth_pending", "oauth_transaction_id"}
        }
        MCPEventsRepository(self.db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=user_id,
            event_type="oauth_disconnected",
            payload={"provider": server.provider_slug},
        )
        self.db.commit()

    def start(self, *, server: MCPServer, user_id: uuid.UUID) -> str:
        if server.user_id != user_id:
            raise ValueError("MCP server does not belong to this user")
        if not server.config.get("server_url"):
            raise ValueError("This MCP vendor does not publish a remote endpoint")
        validate_remote_endpoint(str(server.config["server_url"]))
        profile = self._static_profile(server)
        if profile is not None:
            return self._start_static_profile(server=server, user_id=user_id, profile=profile)
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

        profile = get_mcp_provider_profile(server.provider_slug)
        if profile is not None and payload.get("provider_slug") == server.provider_slug:
            self._finish_static_profile(
                server=server,
                code=code,
                state=state,
                state_payload=payload,
                profile=profile,
            )
            return

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
            MCPOAuthToken.user_id == server.user_id,
        ).one_or_none()
        if record is None:
            record = MCPOAuthToken(
                tenant_id=server.tenant_id,
                user_id=server.user_id,
                server_id=server.id,
                registry_entry_id=server.registry_entry_id,
                provider_slug=server.provider_slug or str((server.config or {}).get("vendor_slug") or "") or None,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
                expires_at=expires_at,
                granted_scopes=self._safe_scope_list(getattr(token, "scope", None)),
            )
            self.db.add(record)
        else:
            record.user_id = server.user_id
            record.registry_entry_id = server.registry_entry_id
            record.provider_slug = server.provider_slug or str((server.config or {}).get("vendor_slug") or "") or None
            record.secret_ciphertext = encrypted.ciphertext
            record.secret_nonce = encrypted.nonce
            record.secret_kid = encrypted.kid
            record.expires_at = expires_at
            record.granted_scopes = self._safe_scope_list(getattr(token, "scope", None))

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
        server.status = "connected"
        server.enabled = True
        server.last_connected_at = datetime.now(UTC)
        server.last_error = None
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
