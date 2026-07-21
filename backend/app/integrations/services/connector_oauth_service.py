from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.brand import APP_BRAND_NAME
from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.integration import Integration
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto

try:  # pragma: no cover - optional runtime dependency
    from mcp.client.auth.utils import (
        build_oauth_authorization_server_metadata_discovery_urls,
        build_protected_resource_metadata_discovery_urls,
        create_client_registration_request,
        get_client_metadata_scopes,
    )
    from mcp.client.streamable_http import MCP_PROTOCOL_VERSION
    from mcp.shared.auth import (
        OAuthClientInformationFull,
        OAuthClientMetadata,
        OAuthMetadata,
        OAuthToken,
        ProtectedResourceMetadata,
    )
    from mcp.types import LATEST_PROTOCOL_VERSION

    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - graceful fallback for non-MCP envs
    build_oauth_authorization_server_metadata_discovery_urls = None  # type: ignore[assignment]
    build_protected_resource_metadata_discovery_urls = None  # type: ignore[assignment]
    create_client_registration_request = None  # type: ignore[assignment]
    get_client_metadata_scopes = None  # type: ignore[assignment]
    MCP_PROTOCOL_VERSION = None  # type: ignore[assignment]
    OAuthClientInformationFull = Any  # type: ignore[assignment,misc]
    OAuthClientMetadata = Any  # type: ignore[assignment,misc]
    OAuthMetadata = Any  # type: ignore[assignment,misc]
    OAuthToken = Any  # type: ignore[assignment,misc]
    ProtectedResourceMetadata = Any  # type: ignore[assignment,misc]
    LATEST_PROTOCOL_VERSION = None  # type: ignore[assignment]
    MCP_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MCPProfile:
    slug: str
    server_url: str
    tools: tuple[str, ...]
    default_scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConnectorOAuthClientConfig:
    provider_key: str
    provider_label: str
    client_id: str
    client_secret: str
    missing: tuple[str, ...] = ()


class ConnectorOAuthService:
    """
    Connector onboarding service for provider OAuth bootstrap plus MCP tool discovery.

    The provider OAuth client ID / secret comes from deployment config so the
    browser can complete a real consent flow. MCP metadata is still used to
    discover the resource server, auth server, and exposed tool surface without
    changing the rest of the AverQel connector runtime contract.
    """

    PENDING_SECRET_TYPE: str = "mcp_oauth_pending"
    CREDENTIALS_SECRET_TYPE: str = "credentials"

    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings
        self.crypto = ConnectorSecretCrypto(settings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def readiness(self, *, integration: Integration) -> dict[str, Any]:
        if not MCP_SDK_AVAILABLE:
            return {
                "configured": False,
                "message": "MCP support is not installed in this runtime.",
                "missing": ["mcp_sdk"],
                "provider_key": integration.slug,
            }
        profile = self._profile_for_integration(integration)
        if profile is None:
            return {
                "configured": False,
                "message": "MCP connector metadata is not configured for this integration.",
                "missing": ["mcp_server_url"],
                "provider_key": integration.slug,
            }
        redirect_uri = self._connector_redirect_uri()
        if not redirect_uri:
            return {
                "configured": False,
                "message": (
                    f"{APP_BRAND_NAME} connector callback URL is not configured. "
                    f"Set AVERQEL_PUBLIC_ORIGIN so {APP_BRAND_NAME} can derive it."
                ),
                "missing": ["connector_oauth_redirect_uri"],
                "provider_key": integration.slug,
            }
        frontend_redirect_uri = self._connector_frontend_redirect_uri()
        if not frontend_redirect_uri:
            return {
                "configured": False,
                "message": (
                    f"{APP_BRAND_NAME} connector frontend redirect URL is not configured. "
                    f"Set AVERQEL_PUBLIC_ORIGIN so {APP_BRAND_NAME} can derive it."
                ),
                "missing": ["connector_oauth_frontend_redirect_uri"],
                "provider_key": integration.slug,
            }

        provider_config = self._provider_oauth_client_config_for_integration(
            integration
        )
        if provider_config is None:
            return {
                "configured": False,
                "message": f"OAuth client for {integration.slug} is not supported on this deployment.",
                "missing": ["oauth_provider_config"],
                "provider_key": integration.slug,
            }

        if provider_config.missing:
            pretty_missing = ", ".join(provider_config.missing)
            return {
                "configured": False,
                "message": (
                    f"{provider_config.provider_label} OAuth is not configured. "
                    f"Missing environment variables: {pretty_missing}."
                ),
                "missing": list(provider_config.missing),
                "provider_key": integration.slug,
            }

        tools = list(profile.tools)
        tool_count = len(tools)
        return {
            "configured": True,
            "message": (
                f"{provider_config.provider_label} OAuth client ready for {integration.name}. "
                f"{APP_BRAND_NAME} will connect through {profile.server_url} and expose {tool_count} tools."
            ),
            "missing": [],
            "provider_key": integration.slug,
        }

    def start(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        connector_id: uuid.UUID,
    ) -> tuple[bool, str | None, str]:
        if not MCP_SDK_AVAILABLE:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="MCP support is not installed in this runtime.",
                status_code=400,
            )
        connector = self._load_connector(connector_id, tenant_id)
        if connector is None:
            raise HTTPException(status_code=404, detail="Connector not found")

        integration = self._load_integration(connector.integration_id)
        if integration is None:
            raise HTTPException(status_code=404, detail="Integration not found")

        profile = self._profile_for_integration(integration)
        if profile is None:
            raise ApiError(
                code="CONNECTOR_OAUTH_UNSUPPORTED",
                message=f"{integration.slug} does not expose an MCP connection profile.",
                status_code=400,
            )

        provider_config = self._provider_oauth_client_config_for_integration(
            integration
        )
        if provider_config is None or provider_config.missing:
            missing = list(provider_config.missing if provider_config else [])
            if not missing:
                missing = ["oauth_client_id", "oauth_client_secret"]
            pretty_missing = ", ".join(missing)
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message=(
                    f"{integration.name} OAuth is not configured on this deployment. Missing: "
                    f"{pretty_missing}."
                ),
                status_code=400,
            )

        redirect_uri = self._connector_redirect_uri()
        if not redirect_uri:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message=(
                    f"{APP_BRAND_NAME} connector callback URL is not configured. "
                    f"Set AVERQEL_PUBLIC_ORIGIN so {APP_BRAND_NAME} can derive it."
                ),
                status_code=400,
            )

        try:
            resource_metadata, oauth_metadata = self._discover_mcp_metadata(
                profile.server_url
            )
            scope = get_client_metadata_scopes(None, resource_metadata, oauth_metadata)
            if not scope and profile.default_scopes:
                scope = " ".join(profile.default_scopes)

            client_metadata = OAuthClientMetadata(
                redirect_uris=[redirect_uri],
                token_endpoint_auth_method="client_secret_post",
                scope=scope,
                client_name=APP_BRAND_NAME,
                client_uri=self._public_origin(),
                software_id=APP_BRAND_NAME.lower(),
                software_version="mcp-connector",
            )
            client_info = OAuthClientInformationFull.model_validate(
                {
                    "redirect_uris": [redirect_uri],
                    "token_endpoint_auth_method": "client_secret_post",
                    "scope": scope,
                    "client_name": APP_BRAND_NAME,
                    "client_uri": self._public_origin(),
                    "software_id": APP_BRAND_NAME.lower(),
                    "software_version": "connector-oauth",
                    "client_id": provider_config.client_id,
                    "client_secret": provider_config.client_secret,
                }
            )
        except ApiError:
            raise
        except httpx.RequestError as exc:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message=f"Unable to reach MCP connector service for {integration.slug}: {exc}",
                status_code=400,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message=f"Failed to initialize connector flow for {integration.slug}: {exc}",
                status_code=400,
            ) from exc

        state_payload = {
            "connector_id": str(connector.id),
            "tenant_id": str(connector.tenant_id),
            "user_id": str(actor_user_id),
            "integration_slug": integration.slug,
            "server_url": profile.server_url,
            "issued_at": self._iso_now(),
            "nonce": secrets.token_urlsafe(24),
        }
        state = self._sign_state(state_payload)
        pkce = self._generate_pkce()

        pending_payload = {
            "state": state,
            "state_payload": state_payload,
            "code_verifier": pkce["code_verifier"],
            "code_challenge": pkce["code_challenge"],
            "redirect_uri": redirect_uri,
            "server_url": profile.server_url,
            # Tool names are discovered from the live MCP server after OAuth;
            # the wildcard is only a legacy connector compatibility marker.
            "mcp_tools": list(profile.tools) or ["*"],
            "integration_slug": integration.slug,
            "resource_metadata": resource_metadata.model_dump(mode="json"),
            "oauth_metadata": oauth_metadata.model_dump(mode="json"),
            "client_metadata": client_metadata.model_dump(
                mode="json", exclude_none=True
            ),
            "client_info": client_info.model_dump(mode="json", exclude_none=True),
        }
        self._upsert_secret(
            connector=connector,
            secret_type=self.PENDING_SECRET_TYPE,
            payload=pending_payload,
        )
        self.session.commit()

        authorization_url = self._build_authorization_url(
            oauth_metadata=oauth_metadata,
            client_info=client_info,
            client_metadata=client_metadata,
            resource_metadata=resource_metadata,
            state=state,
            code_challenge=pkce["code_challenge"],
        )

        return True, authorization_url, f"OAuth flow initialized for {connector.name}."

    async def callback(self, *, code: str | None, state: str | None) -> Connector:
        if not MCP_SDK_AVAILABLE:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="MCP support is not installed in this runtime.",
                status_code=400,
            )
        if not code or not state:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="Missing OAuth callback parameters.",
                status_code=400,
            )

        state_payload = self._verify_state(state)
        connector = self._load_connector(
            uuid.UUID(str(state_payload["connector_id"])),
            uuid.UUID(str(state_payload["tenant_id"])),
        )
        if connector is None:
            raise HTTPException(status_code=404, detail="Connector not found")

        pending = self._load_secret_payload(connector, self.PENDING_SECRET_TYPE)
        if pending is None:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="No pending MCP authorization state was found.",
                status_code=400,
            )

        pending_state = str(pending.get("state") or "")
        if not hmac.compare_digest(pending_state, state):
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="OAuth state mismatch.",
                status_code=400,
            )

        oauth_metadata = OAuthMetadata.model_validate(pending["oauth_metadata"])
        client_info = OAuthClientInformationFull.model_validate(pending["client_info"])
        resource_metadata = ProtectedResourceMetadata.model_validate(
            pending["resource_metadata"]
        )
        code_verifier = str(pending["code_verifier"] or "")
        redirect_uri = str(
            pending["redirect_uri"] or self._connector_redirect_uri() or ""
        )
        if not redirect_uri:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="Connector callback URI is not configured.",
                status_code=400,
            )

        try:
            token = self._exchange_token(
                oauth_metadata=oauth_metadata,
                client_info=client_info,
                resource_metadata=resource_metadata,
                code=code,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
            )
        except ApiError:
            raise
        except httpx.RequestError as exc:
            raise ApiError(
                code="CONNECTOR_OAUTH_TOKEN_EXCHANGE_FAILED",
                message=f"Unable to reach MCP token endpoint: {exc}",
                status_code=400,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="CONNECTOR_OAUTH_TOKEN_EXCHANGE_FAILED",
                message=f"Failed to complete MCP token exchange: {exc}",
                status_code=400,
            ) from exc

        connector.status = ConnectorStatus.ACTIVE
        connector.last_error = None
        connector.error_count = 0

        # --- Phase 3: Live MCP Tool Discovery & Caching ---
        config = dict(connector.config or {})
        config["auth_mode"] = "mcp"
        server_url = str(pending["server_url"] or "")
        config["mcp_server_url"] = server_url

        credentials_payload = self._build_credentials_payload(
            pending=pending,
            client_info=client_info,
            oauth_metadata=oauth_metadata,
            resource_metadata=resource_metadata,
            token=token,
            redirect_uri=redirect_uri,
        )

        from app.integrations.services.mcp_runtime import build_mcp_runtime

        mcp_runtime_config = {
            "auth_mode": "mcp",
            "credentials": credentials_payload,
            "mcp_server_url": server_url,
        }
        runtime = build_mcp_runtime(mcp_runtime_config)
        if runtime:
            try:
                # Fetch full tool schemas from the server
                tools = await runtime.list_tools()
                config["mcp_tools_cache"] = tools
                # Store only names in the legacy list for backward compatibility
                config["mcp_tools"] = [t.get("name") for t in tools]
            except Exception as exc:
                logger.warning(
                    f"Failed to cache tools for connector {connector.id}: {exc}"
                )

        connector.config = config
        # ------------------------------------------------

        credentials_payload = self._build_credentials_payload(
            pending=pending,
            client_info=client_info,
            oauth_metadata=oauth_metadata,
            resource_metadata=resource_metadata,
            token=token,
            redirect_uri=redirect_uri,
        )
        self._upsert_secret(
            connector=connector,
            secret_type=self.CREDENTIALS_SECRET_TYPE,
            payload=credentials_payload,
        )
        self._delete_secret(connector, self.PENDING_SECRET_TYPE)
        self.session.commit()
        self.session.refresh(connector)
        return connector

    # ------------------------------------------------------------------
    # Discovery / OAuth helpers
    # ------------------------------------------------------------------

    def _public_origin(self) -> str | None:
        value = (self.settings.averqel_public_origin or "").strip().rstrip("/")
        return value or None

    def _connector_redirect_uri(self) -> str | None:
        value = (self.settings.connector_oauth_redirect_uri or "").strip().rstrip("/")
        if not value:
            origin = self._public_origin()
            if origin:
                value = f"{origin}{self.settings.api_prefix}/integrations/connectors/oauth/callback"
        return value or None

    def _connector_frontend_redirect_uri(self) -> str | None:
        value = (
            (self.settings.connector_oauth_frontend_redirect_uri or "")
            .strip()
            .rstrip("/")
        )
        if not value:
            origin = self._public_origin()
            if origin:
                value = f"{origin}/dashboard/connectors"
        return value or None

    def _profile_for_integration(self, integration: Integration) -> MCPProfile | None:
        ui_metadata = (
            integration.ui_metadata if isinstance(integration.ui_metadata, dict) else {}
        )
        auth_mode = str(ui_metadata.get("auth_mode") or "").strip().lower()
        server_url = str(ui_metadata.get("mcp_server_url") or "").strip()
        tools = tuple(
            str(tool).strip()
            for tool in (ui_metadata.get("mcp_tools") or [])
            if isinstance(tool, str) and tool.strip()
        )
        scopes = tuple(
            str(scope).strip()
            for scope in (ui_metadata.get("mcp_scopes") or [])
            if isinstance(scope, str) and scope.strip()
        )

        if auth_mode != "mcp" or not server_url:
            # Keep built-in provider integrations usable when an older catalog
            # row predates the newer MCP metadata columns.
            built_in_profiles = {
                "google-drive": MCPProfile(
                    slug="google-drive",
                    server_url="https://drivemcp.googleapis.com/mcp/v1",
                    tools=(),
                    default_scopes=("https://www.googleapis.com/auth/drive",),
                )
            }
            return built_in_profiles.get(integration.slug)

        return MCPProfile(
            slug=integration.slug,
            server_url=server_url,
            tools=tools,
            default_scopes=scopes,
        )

    def _provider_oauth_client_config_for_integration(
        self, integration: Integration
    ) -> ConnectorOAuthClientConfig | None:
        ui_metadata = integration.ui_metadata if isinstance(integration.ui_metadata, dict) else {}
        provider_key = str(
            ui_metadata.get("oauth_provider_key")
            or {"google-drive": "google"}.get(integration.slug, integration.slug)
        ).strip()
        if not provider_key:
            return None
        provider_label = str(
            ui_metadata.get("oauth_provider_label") or integration.name
        )

        client_id_attr = f"connector_{provider_key}_oauth_client_id"
        client_secret_attr = f"connector_{provider_key}_oauth_client_secret"

        client_id = str(getattr(self.settings, client_id_attr, "") or "").strip()
        client_secret = str(
            getattr(self.settings, client_secret_attr, "") or ""
        ).strip()

        missing: list[str] = []
        if not client_id:
            missing.append(f"AKS_{client_id_attr.upper()}")
        if not client_secret:
            missing.append(f"AKS_{client_secret_attr.upper()}")

        return ConnectorOAuthClientConfig(
            provider_key=provider_key,
            provider_label=provider_label,
            client_id=client_id,
            client_secret=client_secret,
            missing=tuple(missing),
        )

    def _discover_mcp_metadata(
        self, server_url: str
    ) -> tuple[ProtectedResourceMetadata, OAuthMetadata]:
        headers = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resource_metadata = self._discover_resource_metadata(
                client, server_url, headers=headers
            )
            oauth_metadata = self._discover_oauth_metadata(
                client,
                server_url=server_url,
                auth_server_url=str(resource_metadata.authorization_servers[0]),
                headers=headers,
            )
        return resource_metadata, oauth_metadata

    def _discover_resource_metadata(
        self,
        client: httpx.Client,
        server_url: str,
        *,
        headers: dict[str, str],
    ) -> ProtectedResourceMetadata:
        last_error: str | None = None
        for url in build_protected_resource_metadata_discovery_urls(None, server_url):
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                last_error = f"{response.status_code} {response.text}"
                continue
            try:
                return ProtectedResourceMetadata.model_validate_json(response.text)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
        raise ApiError(
            code="CONNECTOR_OAUTH_INVALID",
            message=f"Unable to discover MCP protected resource metadata: {last_error or 'unknown error'}",
            status_code=400,
        )

    def _discover_oauth_metadata(
        self,
        client: httpx.Client,
        *,
        server_url: str,
        auth_server_url: str,
        headers: dict[str, str],
    ) -> OAuthMetadata:
        last_error: str | None = None
        for url in build_oauth_authorization_server_metadata_discovery_urls(
            auth_server_url, server_url
        ):
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                last_error = f"{response.status_code} {response.text}"
                continue
            try:
                return OAuthMetadata.model_validate_json(response.text)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
        raise ApiError(
            code="CONNECTOR_OAUTH_INVALID",
            message=f"Unable to discover MCP authorization server metadata: {last_error or 'unknown error'}",
            status_code=400,
        )

    def _register_client(
        self,
        *,
        oauth_metadata: OAuthMetadata,
        client_metadata: OAuthClientMetadata,
        server_url: str,
    ) -> OAuthClientInformationFull:
        base_url = self._base_origin(server_url)
        request = create_client_registration_request(
            oauth_metadata,
            client_metadata,
            base_url,
        )
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.send(request)
        if response.status_code not in {200, 201}:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message=f"MCP client registration failed: {response.status_code} {response.text}",
                status_code=400,
            )
        return OAuthClientInformationFull.model_validate_json(response.text)

    def _build_authorization_url(
        self,
        *,
        oauth_metadata: OAuthMetadata,
        client_info: OAuthClientInformationFull,
        client_metadata: OAuthClientMetadata,
        resource_metadata: ProtectedResourceMetadata,
        state: str,
        code_challenge: str,
    ) -> str:
        auth_endpoint = str(oauth_metadata.authorization_endpoint)
        redirect_uri = (
            str(client_metadata.redirect_uris[0])
            if client_metadata.redirect_uris
            else ""
        )
        if not redirect_uri:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="Redirect URI is missing from the MCP client metadata.",
                status_code=400,
            )

        params = {
            "response_type": "code",
            "client_id": client_info.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        scope = client_metadata.scope
        if scope:
            params["scope"] = scope

        resource = str(resource_metadata.resource or "").strip()
        if resource:
            params["resource"] = resource

        query = httpx.QueryParams(params)
        return f"{auth_endpoint}?{query}"

    def _exchange_token(
        self,
        *,
        oauth_metadata: OAuthMetadata,
        client_info: OAuthClientInformationFull,
        resource_metadata: ProtectedResourceMetadata,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OAuthToken:
        token_endpoint = str(oauth_metadata.token_endpoint)
        form_data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_info.client_id or "",
            "code_verifier": code_verifier,
        }
        if resource_metadata.resource:
            form_data["resource"] = str(resource_metadata.resource)

        auth_method = (client_info.token_endpoint_auth_method or "none").strip()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if (
            auth_method == "client_secret_basic"
            and client_info.client_id
            and client_info.client_secret
        ):
            basic_token = base64.b64encode(
                f"{client_info.client_id}:{client_info.client_secret}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {basic_token}"
            form_data.pop("client_id", None)
        elif auth_method == "client_secret_post" and client_info.client_secret:
            form_data["client_secret"] = client_info.client_secret

        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.post(token_endpoint, data=form_data, headers=headers)
        if response.status_code != 200:
            raise ApiError(
                code="CONNECTOR_OAUTH_TOKEN_EXCHANGE_FAILED",
                message=f"MCP token exchange failed: {response.status_code} {response.text}",
                status_code=400,
            )
        try:
            return OAuthToken.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="CONNECTOR_OAUTH_TOKEN_EXCHANGE_FAILED",
                message=f"Invalid MCP token response: {exc}",
                status_code=400,
            ) from exc

    # ------------------------------------------------------------------
    # Secret storage helpers
    # ------------------------------------------------------------------

    def _load_connector(
        self, connector_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Connector | None:
        connector = self.session.get(Connector, connector_id)
        if connector and connector.tenant_id == tenant_id:
            return connector
        return None

    def _load_integration(self, integration_id: uuid.UUID) -> Integration | None:
        return self.session.get(Integration, integration_id)

    def _load_secret_payload(
        self, connector: Connector, secret_type: str
    ) -> dict[str, Any] | None:
        stmt = select(ConnectorSecret).where(
            ConnectorSecret.connector_id == connector.id,
            ConnectorSecret.secret_type == secret_type,
        )
        secret = self.session.execute(stmt).scalars().first()
        if secret is None:
            return None
        decrypted = self.crypto.decrypt(
            ciphertext=secret.secret_ciphertext,
            nonce=secret.secret_nonce,
            kid=secret.secret_kid,
            aad=str(connector.tenant_id).encode(),
        )
        try:
            payload = json.loads(decrypted.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="Stored connector auth payload is invalid JSON.",
                status_code=400,
            ) from exc
        if not isinstance(payload, dict):
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="Stored connector auth payload is invalid.",
                status_code=400,
            )
        return payload

    def _upsert_secret(
        self,
        *,
        connector: Connector,
        secret_type: str,
        payload: dict[str, Any],
    ) -> None:
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        encrypted = self.crypto.encrypt(
            plaintext, aad=str(connector.tenant_id).encode()
        )
        stmt = select(ConnectorSecret).where(
            ConnectorSecret.connector_id == connector.id,
            ConnectorSecret.secret_type == secret_type,
        )
        secret = self.session.execute(stmt).scalars().first()
        if secret is None:
            secret = ConnectorSecret(
                connector_id=connector.id,
                tenant_id=connector.tenant_id,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
                secret_type=secret_type,
                metadata_json={
                    "auth_mode": "mcp",
                    "provider_key": (
                        connector.integration.slug if connector.integration else None
                    ),
                },
            )
            self.session.add(secret)
        else:
            secret.secret_ciphertext = encrypted.ciphertext
            secret.secret_nonce = encrypted.nonce
            secret.secret_kid = encrypted.kid
            secret.metadata_json = {
                "auth_mode": "mcp",
                "provider_key": (
                    connector.integration.slug if connector.integration else None
                ),
            }

    def _delete_secret(self, connector: Connector, secret_type: str) -> None:
        stmt = delete(ConnectorSecret).where(
            ConnectorSecret.connector_id == connector.id,
            ConnectorSecret.secret_type == secret_type,
        )
        self.session.execute(stmt)

    def _build_credentials_payload(
        self,
        *,
        pending: dict[str, Any],
        client_info: OAuthClientInformationFull,
        oauth_metadata: OAuthMetadata,
        resource_metadata: ProtectedResourceMetadata,
        token: OAuthToken,
        redirect_uri: str,
    ) -> dict[str, Any]:
        scope = token.scope or pending.get("client_metadata", {}).get("scope")
        scopes = scope.split(" ") if isinstance(scope, str) and scope.strip() else []
        return {
            "auth_mode": "mcp",
            "server_url": pending.get("server_url"),
            "mcp_tools": list(pending.get("mcp_tools") or []),
            "authorization_endpoint": str(oauth_metadata.authorization_endpoint),
            "token_uri": str(oauth_metadata.token_endpoint),
            "resource": (
                str(resource_metadata.resource) if resource_metadata.resource else None
            ),
            "client_id": client_info.client_id,
            "client_secret": client_info.client_secret,
            "client_name": client_info.client_name,
            "token": token.access_token,
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_type": token.token_type,
            "expires_in": token.expires_in,
            "scope": token.scope,
            "scopes": scopes,
            "redirect_uri": redirect_uri,
            "client_info": client_info.model_dump(mode="json", exclude_none=True),
            "oauth_metadata": oauth_metadata.model_dump(mode="json", exclude_none=True),
            "resource_metadata": resource_metadata.model_dump(
                mode="json", exclude_none=True
            ),
        }

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _state_secret(self) -> str:
        return (
            self.settings.refresh_token_hash_secret or self.settings.jwt_secret
        ).strip()

    def _sign_state(self, payload: dict[str, Any]) -> str:
        encoded = (
            base64.urlsafe_b64encode(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            .decode("utf-8")
            .rstrip("=")
        )
        signature = hmac.new(
            self._state_secret().encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        token = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
        return f"{encoded}.{token}"

    def _verify_state(self, state: str) -> dict[str, Any]:
        try:
            encoded, token = state.split(".", 1)
        except ValueError as exc:
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="Invalid OAuth state.",
                status_code=400,
            ) from exc

        expected = hmac.new(
            self._state_secret().encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_token = base64.urlsafe_b64encode(expected).decode("utf-8").rstrip("=")
        if not hmac.compare_digest(expected_token, token):
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="OAuth state verification failed.",
                status_code=400,
            )

        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            payload = json.loads(
                base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            )
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="OAuth state payload is invalid.",
                status_code=400,
            ) from exc
        if not isinstance(payload, dict):
            raise ApiError(
                code="CONNECTOR_OAUTH_INVALID",
                message="OAuth state payload is invalid.",
                status_code=400,
            )
        return payload

    @staticmethod
    def _generate_pkce() -> dict[str, str]:
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        return {"code_verifier": code_verifier, "code_challenge": code_challenge}

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _base_origin(server_url: str) -> str:
        parsed = httpx.URL(server_url)
        return (
            f"{parsed.scheme}://{parsed.host}{f':{parsed.port}' if parsed.port else ''}"
        )
