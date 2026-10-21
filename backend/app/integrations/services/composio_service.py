"""Per-user Composio SDK adapter for catalog, OAuth, and hosted MCP sessions."""

from __future__ import annotations

import base64
import hmac
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.models.composio_credential import ComposioCredential
from app.integrations.models.mcp_server import MCPServer
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto
from app.integrations.services.mcp_endpoint_security import validate_remote_endpoint
from app.platform.database.session import set_db_tenant_context, set_db_user_context

logger = logging.getLogger(__name__)

COMPOSIO_PROVIDER_PREFIX = "composio:"
COMPOSIO_API_HOST = "backend.composio.dev"
COMPOSIO_TOOLKIT_SLUG_PATTERN = re.compile(
    r"^(?:[a-z0-9][a-z0-9_-]{0,127}|_[a-z0-9][a-z0-9_-]{0,126})$"
)
COMPOSIO_TOOL_PAGE_LIMIT = 100
COMPOSIO_SCHEMA_FIELD_LIMIT = 100


class ComposioConfigurationError(RuntimeError):
    """A safe-to-display Composio configuration or catalog error."""


@dataclass(frozen=True, slots=True)
class ComposioConnectionStart:
    server: MCPServer
    authorization_url: str | None
    already_connected: bool = False
    authorization_required: bool = True


def composio_user_id(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Derive a stable, non-email Composio identity from the authenticated owner."""
    return f"averqel:{tenant_id}:{user_id}"


def composio_provider_slug(toolkit_slug: str) -> str:
    return f"{COMPOSIO_PROVIDER_PREFIX}{toolkit_slug}"


def composio_callback_url(public_origin: str | None, toolkit_slug: str) -> str | None:
    """Build the user-facing OAuth redirect URL from AverQel's configured origin."""
    origin = (public_origin or "").strip().rstrip("/")
    try:
        parsed = urlsplit(origin)
        hostname = (parsed.hostname or "").lower()
        local_http = parsed.scheme == "http" and hostname in {"localhost", "127.0.0.1", "::1"}
        origin_port = parsed.port
        if (
            not origin
            or (parsed.scheme != "https" and not local_http)
            or not hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or origin_port == 0
        ):
            return None
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                "/dashboard/mcp/composio/callback",
                urlencode({"toolkit_slug": toolkit_slug}),
                "",
            )
        )
    except ValueError:
        return None


def is_composio_server(server: MCPServer) -> bool:
    return str(getattr(server, "provider_slug", None) or "").startswith(COMPOSIO_PROVIDER_PREFIX)


def _credential_query(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ComposioCredential | None:
    set_db_tenant_context(db, tenant_id)
    set_db_user_context(db, user_id)
    return db.execute(
        select(ComposioCredential).where(
            ComposioCredential.tenant_id == tenant_id,
            ComposioCredential.user_id == user_id,
        )
    ).scalar_one_or_none()


def _sdk(api_key: str) -> Any:
    try:
        from composio import Composio
    except ImportError as exc:  # pragma: no cover - requirements install the SDK
        raise ComposioConfigurationError("The Composio integration is unavailable.") from exc
    return Composio(api_key=api_key)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    serializer = getattr(value, "model_dump", None)
    if callable(serializer):
        dumped = serializer(mode="json", exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _schema_property(value: Any, *, depth: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": "string"}
    if depth > 8:
        return {"type": "object", "properties": {}, "additionalProperties": False}
    result: dict[str, Any] = {}
    allowed = {
        "type",
        "description",
        "enum",
        "format",
        "default",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
    }
    for key in allowed:
        item = value.get(key)
        if key not in value:
            continue
        if key == "description" and isinstance(item, str):
            result[key] = item[:1200]
        elif key == "enum" and isinstance(item, list):
            result[key] = [
                option
                for option in item[:100]
                if option is None or isinstance(option, str | int | float | bool)
            ]
        elif key == "pattern" and isinstance(item, str):
            result[key] = item[:256]
        elif key in {"type", "format", "default"}:
            if isinstance(item, str | int | float | bool) or item is None:
                result[key] = item
        elif key in {"minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}:
            if isinstance(item, int | float):
                result[key] = item
    if isinstance(value.get("properties"), dict):
        result["properties"] = {
            str(key)[:160]: _schema_property(child, depth=depth + 1)
            for key, child in list(value["properties"].items())[:COMPOSIO_SCHEMA_FIELD_LIMIT]
        }
        result["additionalProperties"] = False
        required = value.get("required")
        if isinstance(required, list):
            result["required"] = [
                str(name)[:160]
                for name in required[:COMPOSIO_SCHEMA_FIELD_LIMIT]
                if str(name) in result["properties"]
            ]
    if isinstance(value.get("items"), dict):
        result["items"] = _schema_property(value["items"], depth=depth + 1)
    return result or {"type": "string"}


def _input_schema(raw: Any) -> dict[str, Any]:
    """Normalize Composio's parameter map into the JSON Schema MCP expects."""
    if not isinstance(raw, dict):
        return {"type": "object", "properties": {}, "additionalProperties": False}
    if raw.get("type") == "object" and isinstance(raw.get("properties"), dict):
        object_properties = {
            str(name)[:160]: _schema_property(value)
            for name, value in list(raw["properties"].items())[:COMPOSIO_SCHEMA_FIELD_LIMIT]
        }
        object_required = raw.get("required")
        return {
            "type": "object",
            "properties": object_properties,
            "required": (
                [
                    str(name)[:160]
                    for name in object_required[:COMPOSIO_SCHEMA_FIELD_LIMIT]
                    if str(name) in object_properties
                ]
                if isinstance(object_required, list)
                else []
            ),
            "additionalProperties": False,
        }
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, definition in list(raw.items())[:COMPOSIO_SCHEMA_FIELD_LIMIT]:
        if not isinstance(name, str):
            continue
        name = name[:160]
        properties[name] = _schema_property(definition)
        if isinstance(definition, dict) and definition.get("required") is True:
            required.append(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def classify_composio_tool(name: str, tool: dict[str, Any] | None = None) -> str:
    """Classify Composio actions conservatively for AverQel's approval policy."""
    metadata = tool or {}
    labels = {
        str(item).strip().lower()
        for item in metadata.get("risk_labels", [])
        if isinstance(item, str)
    }
    if "delete" in labels:
        return "delete"
    if "external_message" in labels:
        return "external_message"
    if "write" in labels:
        return "write"
    if "read" in labels:
        return "read"

    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).casefold()).strip("_")
    segments = set(normalized.split("_"))
    if segments & {"delete", "remove", "destroy", "revoke", "trash", "terminate", "cancel"}:
        return "delete"
    read_verbs = {
        "get",
        "list",
        "search",
        "fetch",
        "find",
        "read",
        "view",
        "query",
        "lookup",
        "check",
        "retrieve",
        "download",
    }
    action_verbs = {
        "add",
        "append",
        "cancel",
        "create",
        "delete",
        "destroy",
        "download",
        "edit",
        "fetch",
        "find",
        "get",
        "insert",
        "list",
        "lookup",
        "modify",
        "patch",
        "post",
        "publish",
        "query",
        "read",
        "remove",
        "replace",
        "retrieve",
        "revoke",
        "search",
        "send",
        "submit",
        "update",
        "upload",
        "view",
        "write",
    }
    external_verbs = {
        "comment",
        "email",
        "forward",
        "invite",
        "message",
        "notify",
        "post",
        "publish",
        "reply",
        "send",
    }
    tokens = normalized.split("_")
    first_action = next((token for token in tokens if token in action_verbs | external_verbs), None)
    if first_action in external_verbs:
        return "external_message"
    if first_action in read_verbs:
        return "read"
    return "write"


class ComposioService:
    """Use user-owned Composio keys and tenant/user-bound hosted sessions."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.crypto = ConnectorSecretCrypto(settings)

    def credential_exists(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return _credential_query(self.db, tenant_id=tenant_id, user_id=user_id) is not None

    def _api_key(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
        record = _credential_query(self.db, tenant_id=tenant_id, user_id=user_id)
        if record is None:
            raise ComposioConfigurationError("Add your Composio project API key to continue.")
        try:
            plaintext = self.crypto.decrypt(
                ciphertext=record.secret_ciphertext,
                nonce=record.secret_nonce,
                kid=record.secret_kid,
                aad=self._credential_aad(tenant_id=tenant_id, user_id=user_id),
            )
            value = plaintext.decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.error("Composio user credential decryption failed")
            raise ComposioConfigurationError("The saved Composio key could not be opened.") from exc
        if not value:
            raise ComposioConfigurationError("The saved Composio key is empty.")
        return value

    def _client(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        return _sdk(self._api_key(tenant_id=tenant_id, user_id=user_id))

    @staticmethod
    def _credential_aad(*, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bytes:
        return f"composio:{tenant_id}:{user_id}".encode()

    @staticmethod
    def _session_aad(*, tenant_id: uuid.UUID, user_id: uuid.UUID, server_id: uuid.UUID) -> bytes:
        return f"composio-session:{tenant_id}:{user_id}:{server_id}".encode()

    def _encrypt_session_id(
        self,
        session_id: str,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        server_id: uuid.UUID,
    ) -> dict[str, str]:
        encrypted = self.crypto.encrypt(
            session_id,
            aad=self._session_aad(
                tenant_id=tenant_id,
                user_id=user_id,
                server_id=server_id,
            ),
        )
        return {
            "composio_session_ciphertext": base64.urlsafe_b64encode(encrypted.ciphertext).decode(
                "ascii"
            ),
            "composio_session_nonce": base64.urlsafe_b64encode(encrypted.nonce).decode("ascii"),
            "composio_session_kid": encrypted.kid,
        }

    def _decrypt_session_id(
        self,
        config: dict[str, Any],
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        server_id: uuid.UUID,
    ) -> str | None:
        ciphertext = config.get("composio_session_ciphertext")
        nonce = config.get("composio_session_nonce")
        kid = config.get("composio_session_kid")
        if not (
            isinstance(ciphertext, str)
            and ciphertext
            and isinstance(nonce, str)
            and nonce
            and isinstance(kid, str)
            and kid
        ):
            return None
        try:
            decrypted = self.crypto.decrypt(
                ciphertext=base64.b64decode(ciphertext, altchars=b"-_", validate=True),
                nonce=base64.b64decode(nonce, altchars=b"-_", validate=True),
                kid=kid,
                aad=self._session_aad(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    server_id=server_id,
                ),
            )
            session_id = decrypted.decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.error("Composio MCP session credential could not be decrypted")
            raise ComposioConfigurationError(
                "The Composio MCP session credential could not be opened. Reconnect this app."
            ) from exc
        return session_id or None

    def configure_key(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, api_key: str) -> None:
        normalized = api_key.strip()
        if (
            len(normalized) < 12
            or len(normalized) > 4096
            or any(ord(char) < 32 for char in normalized)
        ):
            raise ComposioConfigurationError("Enter a valid Composio project API key.")
        try:
            _sdk(normalized)._client.toolkits.list(limit=1, type="native")
        except Exception as exc:  # noqa: BLE001
            # Provider exception text may include request details; never echo it.
            raise ComposioConfigurationError(
                "Composio rejected the API key or is temporarily unavailable."
            ) from exc

        existing = _credential_query(self.db, tenant_id=tenant_id, user_id=user_id)
        had_existing = existing is not None
        old_key = None
        if existing is not None:
            try:
                old_key = self.crypto.decrypt(
                    ciphertext=existing.secret_ciphertext,
                    nonce=existing.secret_nonce,
                    kid=existing.secret_kid,
                    aad=self._credential_aad(tenant_id=tenant_id, user_id=user_id),
                ).decode("utf-8")
            except Exception:
                old_key = None

        encrypted = self.crypto.encrypt(
            normalized, aad=self._credential_aad(tenant_id=tenant_id, user_id=user_id)
        )
        if existing is None:
            existing = ComposioCredential(
                tenant_id=tenant_id,
                user_id=user_id,
                secret_ciphertext=encrypted.ciphertext,
                secret_nonce=encrypted.nonce,
                secret_kid=encrypted.kid,
            )
            self.db.add(existing)
        else:
            existing.secret_ciphertext = encrypted.ciphertext
            existing.secret_nonce = encrypted.nonce
            existing.secret_kid = encrypted.kid
        if had_existing and (old_key is None or not hmac.compare_digest(old_key, normalized)):
            self._disable_owner_sessions(tenant_id=tenant_id, user_id=user_id)
        self.db.flush()

    def _disable_owner_sessions(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        set_db_tenant_context(self.db, tenant_id)
        set_db_user_context(self.db, user_id)
        servers = (
            self.db.execute(
                select(MCPServer).where(
                    MCPServer.tenant_id == tenant_id,
                    MCPServer.user_id == user_id,
                    MCPServer.provider_slug.like(f"{COMPOSIO_PROVIDER_PREFIX}%"),
                )
            )
            .scalars()
            .all()
        )
        for server in servers:
            config = dict(server.config or {})
            for key in (
                "composio_session_id",
                "composio_session_ciphertext",
                "composio_session_nonce",
                "composio_session_kid",
                "composio_connected_account_id",
                "composio_pending_connected_account_id",
                "mcp_tools_cache",
                "mcp_catalog_tool_count",
                "mcp_catalog_last_sync_at",
            ):
                config.pop(key, None)
            server.config = config
            server.enabled = False
            server.status = "disconnected"
            server.last_error = None

    def remove_key(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        record = _credential_query(self.db, tenant_id=tenant_id, user_id=user_id)
        if record is not None:
            self.db.delete(record)
        self._disable_owner_sessions(tenant_id=tenant_id, user_id=user_id)
        self.db.flush()

    def list_toolkits(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        cursor: str | None,
        category: str | None,
        query: str | None,
        limit: int,
    ) -> dict[str, Any]:
        client = self._client(tenant_id=tenant_id, user_id=user_id)
        try:
            # Use the generated resource exposed by the pinned Composio SDK so
            # cursor and total metadata are retained.  The convenience
            # ``toolkits.get(query=...)`` wrapper drops that pagination data.
            parameters: dict[str, Any] = {
                "limit": limit,
                "sort_by": "alphabetically",
                "type": "native",
                "include_deprecated": False,
            }
            if category:
                parameters["category"] = category
            if cursor:
                parameters["cursor"] = cursor
            if query:
                parameters["search"] = query[:200]
            response = client._client.toolkits.list(**parameters)
            items = _field(response, "items", [])
            next_cursor = _field(response, "next_cursor")
            current_page = _field(response, "current_page", 1)
            total_items = _field(response, "total_items", len(items))
        except Exception as exc:  # noqa: BLE001
            raise ComposioConfigurationError("Unable to load the Composio app catalog.") from exc

        normalized = [self._normalize_toolkit(item) for item in items if item is not None]
        return {
            "items": normalized,
            "next_cursor": str(next_cursor) if next_cursor else None,
            "current_page": int(current_page or 1),
            "total_items": int(total_items or len(normalized)),
        }

    @staticmethod
    def _normalize_toolkit(item: Any) -> dict[str, Any]:
        raw = _dump(item)
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else _dump(_field(item, "meta"))
        if not isinstance(meta, dict):
            meta = {}
        slug = str(raw.get("slug") or _field(item, "slug") or "")
        categories = meta.get("categories") or []
        normalized_categories: list[str] = []
        for category in categories:
            if isinstance(category, dict):
                name = category.get("name") or category.get("id")
            else:
                name = category
            if isinstance(name, str) and name.strip():
                normalized_categories.append(name.strip())
        schemes = raw.get("auth_schemes") or _field(item, "auth_schemes", []) or []
        normalized_schemes: list[str] = []
        for scheme in schemes:
            if isinstance(scheme, str) and scheme.strip():
                normalized_schemes.append(scheme.strip())
            elif isinstance(scheme, dict):
                name = scheme.get("name") or scheme.get("type") or scheme.get("auth_scheme")
                if isinstance(name, str) and name.strip():
                    normalized_schemes.append(name.strip())
        return {
            "slug": slug,
            "name": str(raw.get("name") or _field(item, "name") or ""),
            "description": str(meta.get("description") or ""),
            # Toolkit metadata can point to app-owned image hosts, and some
            # of those URLs are stale. Use Composio's maintained toolkit logo
            # CDN with the catalog slug instead of exposing arbitrary hosts.
            "logo_url": (
                f"https://logos.composio.dev/api/{slug}"
                if COMPOSIO_TOOLKIT_SLUG_PATTERN.fullmatch(slug)
                else None
            ),
            "app_url": meta.get("app_url") if isinstance(meta.get("app_url"), str) else None,
            "auth_guide_url": (
                raw.get("auth_guide_url") if isinstance(raw.get("auth_guide_url"), str) else None
            ),
            "version": meta.get("version") if isinstance(meta.get("version"), str) else None,
            "created_at": (
                meta.get("created_at") if isinstance(meta.get("created_at"), str) else None
            ),
            "updated_at": (
                meta.get("updated_at") if isinstance(meta.get("updated_at"), str) else None
            ),
            "categories": normalized_categories,
            "tool_count": int(meta.get("tools_count") or 0),
            "auth_schemes": normalized_schemes,
            "no_auth": bool(raw.get("no_auth", False)),
        }

    def toolkit_details(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        toolkit_slug: str,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_slug(toolkit_slug)
        client = self._client(tenant_id=tenant_id, user_id=user_id)
        try:
            toolkit = client.toolkits.get(toolkit_slug)
            parameters: dict[str, Any] = {
                "toolkit_slug": toolkit_slug,
                "limit": min(max(limit, 1), COMPOSIO_TOOL_PAGE_LIMIT),
                "toolkit_versions": "latest",
                "include_deprecated": False,
            }
            if cursor:
                parameters["cursor"] = cursor
            response = client._client.tools.list(**parameters)
            tools = _field(response, "items", [])
            next_cursor = _field(response, "next_cursor")
        except Exception as exc:  # noqa: BLE001
            raise ComposioConfigurationError("Unable to load this Composio app's tools.") from exc
        item = self._normalize_toolkit(toolkit)
        normalized_tools = []
        for tool in tools:
            raw = _dump(tool)
            name = str(raw.get("slug") or _field(tool, "slug") or "").strip()
            if not name:
                continue
            description = str(raw.get("description") or _field(tool, "description") or "")
            risk = classify_composio_tool(name)
            normalized_tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": _input_schema(
                        raw.get("input_parameters") or _field(tool, "input_parameters")
                    ),
                    "risk_labels": [risk],
                    "version": raw.get("version") or _field(tool, "version"),
                }
            )
        return {
            **item,
            "tools": normalized_tools,
            "tools_loaded": len(normalized_tools),
            "tools_next_cursor": str(next_cursor) if next_cursor else None,
        }

    def start_connection(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        toolkit_slug: str,
        callback_url: str | None,
    ) -> ComposioConnectionStart:
        self._validate_slug(toolkit_slug)
        client = self._client(tenant_id=tenant_id, user_id=user_id)
        try:
            details = self._normalize_toolkit(client.toolkits.get(toolkit_slug))
        except Exception as exc:  # noqa: BLE001
            raise ComposioConfigurationError("Unable to load this Composio app.") from exc
        if not details["slug"] or not details["name"]:
            raise ComposioConfigurationError("Composio did not return this app's metadata.")
        authorization_required = not details["no_auth"]
        if authorization_required:
            parsed_callback_url = urlsplit(callback_url or "")
            callback_hostname = (parsed_callback_url.hostname or "").lower()
            callback_port = parsed_callback_url.port
            local_http = parsed_callback_url.scheme == "http" and callback_hostname in {
                "localhost",
                "127.0.0.1",
                "::1",
            }
            callback_toolkits = parse_qs(parsed_callback_url.query).get("toolkit_slug", [])
            if (
                (parsed_callback_url.scheme != "https" and not local_http)
                or not callback_hostname
                or parsed_callback_url.username
                or parsed_callback_url.password
                or callback_port == 0
                or parsed_callback_url.path != "/dashboard/mcp/composio/callback"
                or callback_toolkits != [toolkit_slug]
            ):
                raise ComposioConfigurationError(
                    "Set AverQel's public HTTPS URL before connecting this Composio app."
                )

        provider_slug = composio_provider_slug(toolkit_slug)
        if details["slug"].casefold() != toolkit_slug.casefold():
            raise ComposioConfigurationError("Composio returned a different app than requested.")
        set_db_tenant_context(self.db, tenant_id)
        set_db_user_context(self.db, user_id)
        server = self.db.execute(
            select(MCPServer).where(
                MCPServer.tenant_id == tenant_id,
                MCPServer.user_id == user_id,
                MCPServer.provider_slug == provider_slug,
            )
        ).scalar_one_or_none()
        if server is not None and server.status == "connected" and server.enabled:
            return ComposioConnectionStart(
                server=server, authorization_url=None, already_connected=True
            )

        try:
            saved_session_id = (
                self._decrypt_session_id(
                    server.config if isinstance(server.config, dict) else {},
                    tenant_id=tenant_id,
                    user_id=user_id,
                    server_id=server.id,
                )
                if server is not None
                else None
            )
            if saved_session_id:
                session = client.use(saved_session_id, mcp=True)
            else:
                from composio import SESSION_PRESET_DIRECT_TOOLS

                session = client.sessions.create(
                    user_id=composio_user_id(tenant_id, user_id),
                    toolkits=[toolkit_slug],
                    session_preset=SESSION_PRESET_DIRECT_TOOLS,
                    mcp=True,
                )
            authorization_url = None
            pending_account_id = None
            if authorization_required:
                request = session.authorize(toolkit_slug, callback_url=callback_url)
                authorization_url = str(request.redirect_url)
                pending_account_id = str(_field(request, "id", "") or "").strip()
                if not pending_account_id or len(pending_account_id) > 256:
                    raise ComposioConfigurationError(
                        "Composio did not return a valid connection request."
                    )
                parsed_authorization_url = urlsplit(authorization_url)
                authorization_host = (parsed_authorization_url.hostname or "").lower()
                if (
                    parsed_authorization_url.scheme != "https"
                    or not authorization_host
                    or parsed_authorization_url.username
                    or parsed_authorization_url.password
                    or parsed_authorization_url.port not in (None, 443)
                    or not (
                        authorization_host == "composio.dev"
                        or authorization_host.endswith(".composio.dev")
                    )
                ):
                    raise ComposioConfigurationError(
                        "Composio returned an unsafe authorization link."
                    )
            session_id = str(session.session_id)
        except ComposioConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ComposioConfigurationError(
                "Unable to start Composio authorization for this app."
            ) from exc

        if server is None:
            server = MCPServer(
                tenant_id=tenant_id,
                user_id=user_id,
                registry_entry_id=None,
                provider_slug=provider_slug,
                name=details["name"],
                transport="streamable_http",
                config={},
                account_identity={},
                catalog_revision=0,
                enabled=True,
                status="needs_auth",
            )
            self.db.add(server)
            self.db.flush()
        config = dict(server.config or {})
        config.pop("composio_session_id", None)
        config.update(
            self._encrypt_session_id(
                session_id,
                tenant_id=tenant_id,
                user_id=user_id,
                server_id=server.id,
            )
        )
        config.update(
            {
                "composio_toolkit_slug": toolkit_slug,
                "source": "composio",
                "categories": details["categories"],
            }
        )
        if pending_account_id:
            # Bind the redirect to the exact owner-scoped request created above.
            # A callback query value alone is never accepted as proof of ownership.
            config["composio_pending_connected_account_id"] = pending_account_id
        else:
            config.pop("composio_pending_connected_account_id", None)
        server.name = details["name"]
        server.transport = "streamable_http"
        server.enabled = True
        server.status = "needs_auth" if authorization_required else "connecting"
        server.last_error = None
        server.account_identity = {}
        server.config = config
        self.db.commit()
        set_db_tenant_context(self.db, tenant_id)
        set_db_user_context(self.db, user_id)
        self.db.refresh(server)
        return ComposioConnectionStart(
            server=server,
            authorization_url=authorization_url,
            authorization_required=authorization_required,
        )

    @staticmethod
    def _validate_slug(slug: str) -> None:
        if not COMPOSIO_TOOLKIT_SLUG_PATTERN.fullmatch(slug):
            raise ComposioConfigurationError("The Composio app identifier is invalid.")

    def complete_auth(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        toolkit_slug: str,
        connected_account_id: str,
        status: str,
    ) -> MCPServer:
        """Verify a standard Composio redirect against its owner-scoped pending request."""
        self._validate_slug(toolkit_slug)
        account_id = connected_account_id.strip()
        if not account_id or len(account_id) > 256 or any(ord(char) < 33 for char in account_id):
            raise ComposioConfigurationError("The Composio authorization response is invalid.")
        if status not in {"success", "failed"}:
            raise ComposioConfigurationError("The Composio authorization response is invalid.")
        set_db_tenant_context(self.db, tenant_id)
        set_db_user_context(self.db, user_id)
        server = self.db.execute(
            select(MCPServer)
            .where(
                MCPServer.tenant_id == tenant_id,
                MCPServer.user_id == user_id,
                MCPServer.provider_slug == composio_provider_slug(toolkit_slug),
                MCPServer.status == "needs_auth",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if server is None:
            raise ComposioConfigurationError("No matching Composio app connection was started.")
        config = dict(server.config or {})
        if (
            config.get("composio_pending_connected_account_id") != account_id
            or config.get("composio_toolkit_slug") != toolkit_slug
            or not config.get("composio_session_ciphertext")
            or not self._decrypt_session_id(
                config,
                tenant_id=tenant_id,
                user_id=user_id,
                server_id=server.id,
            )
        ):
            raise ComposioConfigurationError("The Composio session does not match this app.")

        if status == "failed":
            config.pop("composio_pending_connected_account_id", None)
            server.config = config
            server.status = "disconnected"
            server.enabled = False
            server.last_error = None
            self.db.commit()
            set_db_tenant_context(self.db, tenant_id)
            set_db_user_context(self.db, user_id)
            self.db.refresh(server)
            return server

        expected_composio_user_id = composio_user_id(tenant_id, user_id)
        client = self._client(tenant_id=tenant_id, user_id=user_id)
        try:
            account = client.connected_accounts.wait_for_connection(account_id, timeout=5)
        except Exception as exc:  # noqa: BLE001
            raise ComposioConfigurationError(
                "Composio could not verify this connection. Return to the same signed-in AverQel account and retry."
            ) from exc
        account_toolkit = _field(account, "toolkit")
        returned_toolkit_slug = str(_field(account_toolkit, "slug", "") or "").strip().lower()
        returned_account_id = str(_field(account, "id", "") or "").strip()
        returned_user_id = str(_field(account, "user_id", "") or "").strip()
        if (
            returned_account_id != account_id
            or returned_toolkit_slug != toolkit_slug
            or str(_field(account, "status", "")).upper() != "ACTIVE"
            or (
                returned_user_id
                and not hmac.compare_digest(returned_user_id, expected_composio_user_id)
            )
        ):
            raise ComposioConfigurationError(
                "The Composio account does not match this AverQel user and app."
            )

        server.account_identity = {"account_id": account_id, "identity_source": "composio"}
        config["composio_connected_account_id"] = account_id
        config.pop("composio_pending_connected_account_id", None)
        server.config = config
        server.status = "connecting"
        server.last_error = None
        self.db.commit()
        set_db_tenant_context(self.db, tenant_id)
        set_db_user_context(self.db, user_id)
        self.db.refresh(server)
        return server

    def mcp_endpoint_config(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, server: MCPServer
    ) -> dict[str, Any]:
        config = server.config if isinstance(server.config, dict) else {}
        toolkit_slug = str(config.get("composio_toolkit_slug") or "").strip().lower()
        if not toolkit_slug or server.provider_slug != composio_provider_slug(toolkit_slug):
            raise ComposioConfigurationError("The Composio MCP session is unavailable.")
        session_id = self._decrypt_session_id(
            config,
            tenant_id=tenant_id,
            user_id=user_id,
            server_id=server.id,
        )
        if not session_id:
            raise ComposioConfigurationError("The Composio MCP session is unavailable.")
        client = self._client(tenant_id=tenant_id, user_id=user_id)
        try:
            session = client.use(session_id, mcp=True)
            endpoint = str(session.mcp.url)
            headers = session.mcp.headers
        except Exception as exc:  # noqa: BLE001
            raise ComposioConfigurationError(
                "The Composio MCP session could not be loaded."
            ) from exc
        try:
            endpoint = validate_remote_endpoint(endpoint)
        except ValueError as exc:
            raise ComposioConfigurationError("Composio returned an unsafe MCP endpoint.") from exc
        host = (urlsplit(endpoint).hostname or "").lower()
        if host != COMPOSIO_API_HOST:
            raise ComposioConfigurationError("Composio returned an unrecognized MCP endpoint.")
        if not isinstance(headers, dict) or not headers:
            raise ComposioConfigurationError("Composio did not provide MCP session authorization.")
        safe_headers: dict[str, str] = {}
        for key, value in headers.items():
            normalized = str(key).lower()
            if normalized not in {"x-api-key", "x-user-api-key", "x-org-id", "x-project-id"}:
                raise ComposioConfigurationError("Composio returned an unsupported MCP header.")
            if isinstance(value, str) and value:
                safe_headers[normalized] = value
        if not safe_headers:
            raise ComposioConfigurationError("Composio did not provide MCP session authorization.")
        return {
            "auth_mode": "mcp",
            "credentials": {
                "server_url": endpoint,
                "transport": "streamable_http",
                "oauth_mode": "none",
                "headers": safe_headers,
            },
        }
