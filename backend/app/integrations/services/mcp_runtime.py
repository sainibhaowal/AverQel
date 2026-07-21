from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.models.connector import Connector
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.mcp_server import MCPOAuthToken, MCPServer
from app.integrations.services.config_utils import (
    resolve_config_dict,
    resolve_config_value,
)
from app.integrations.services.connector_service import ConnectorService
from app.integrations.services.health_utils import (
    build_health_report,
    classify_health_status,
)
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto

try:  # pragma: no cover - optional runtime dependency
    from mcp.client.auth.oauth2 import OAuthClientProvider, TokenStorage
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client
    from mcp.shared.auth import (
        OAuthClientInformationFull,
        OAuthClientMetadata,
        OAuthMetadata,
        OAuthToken,
        ProtectedResourceMetadata,
    )

    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - graceful fallback when MCP is unavailable
    OAuthClientProvider = Any  # type: ignore[assignment,misc]
    TokenStorage = object  # type: ignore[assignment,misc]
    ClientSession = Any  # type: ignore[assignment,misc]
    streamable_http_client = None  # type: ignore[assignment]
    sse_client = None  # type: ignore[assignment]
    create_mcp_http_client = None  # type: ignore[assignment]
    OAuthClientInformationFull = Any  # type: ignore[assignment,misc]
    OAuthClientMetadata = Any  # type: ignore[assignment,misc]
    OAuthMetadata = Any  # type: ignore[assignment,misc]
    OAuthToken = Any  # type: ignore[assignment,misc]
    ProtectedResourceMetadata = Any  # type: ignore[assignment,misc]
    MCP_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPCatalog:
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)
    resource_templates: dict[str, dict[str, Any]] = field(default_factory=dict)
    revision: int = 0

    @staticmethod
    def namespace(server: str, name: str) -> str:
        clean = lambda value: re.sub(r"[^a-zA-Z0-9_-]", "_", value)
        return f"{clean(server)}_{clean(name)}"

    @staticmethod
    def normalize_schema(schema: Any) -> dict[str, Any]:
        value = schema if isinstance(schema, dict) else {}
        normalized = dict(value)
        normalized["type"] = "object"
        normalized["properties"] = (
            value.get("properties") if isinstance(value.get("properties"), dict) else {}
        )
        normalized.setdefault("additionalProperties", False)
        return normalized

    def replace_tools(self, server: str, tools: Iterable[dict[str, Any]]) -> None:
        prefix = f"{server}_"
        self.tools = {key: value for key, value in self.tools.items() if not key.startswith(prefix)}
        for tool in tools:
            name = str(tool.get("name") or "").strip()
            if not name:
                continue
            item = dict(tool)
            item["name"] = name
            item["exposed_name"] = self.namespace(server, name)
            item["inputSchema"] = self.normalize_schema(tool.get("inputSchema"))
            item["server"] = server
            self.tools[item["exposed_name"]] = item
        self.revision += 1

    def _replace_named(self, field_name: str, server: str, items: Iterable[dict[str, Any]]) -> None:
        current = getattr(self, field_name)
        prefix = f"{server}_"
        setattr(self, field_name, {key: value for key, value in current.items() if not key.startswith(prefix)})
        target = getattr(self, field_name)
        for item in items:
            name = str(item.get("name") or item.get("uri") or item.get("uriTemplate") or "").strip()
            if not name:
                continue
            value = dict(item)
            value["name"] = name
            value["exposed_name"] = self.namespace(server, name)
            value["server"] = server
            target[value["exposed_name"]] = value
        self.revision += 1

    def replace_prompts(self, server: str, prompts: Iterable[dict[str, Any]]) -> None:
        self._replace_named("prompts", server, prompts)

    def replace_resources(self, server: str, resources: Iterable[dict[str, Any]]) -> None:
        self._replace_named("resources", server, resources)

    def replace_resource_templates(self, server: str, templates: Iterable[dict[str, Any]]) -> None:
        self._replace_named("resource_templates", server, templates)


class MCPRuntimeError(RuntimeError):
    """Raised when MCP-backed connector runtime work fails."""


class _InMemoryTokenStorage:
    def __init__(
        self,
        *,
        tokens: OAuthToken | None = None,
        client_info: OAuthClientInformationFull | None = None,
        on_tokens_updated: Any | None = None,
    ) -> None:
        self._tokens = tokens
        self._client_info = client_info
        self._on_tokens_updated = on_tokens_updated

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens
        if self._on_tokens_updated is not None:
            result = self._on_tokens_updated(tokens)
            if hasattr(result, "__await__"):
                await result

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


@dataclass(slots=True)
class MCPConnectorRuntime:
    server_url: str
    client_metadata: OAuthClientMetadata | None
    storage: _InMemoryTokenStorage
    oauth_metadata: OAuthMetadata | None
    resource_metadata: ProtectedResourceMetadata | None
    declared_tools: tuple[str, ...]
    timeout: float = 30.0
    transport: str = "streamable_http"
    fallback_transport: str | None = None
    message_handler: Any | None = None
    notification_handler: Any | None = None
    anonymous: bool = False
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict[str, Any], *, on_tokens_updated: Any | None = None, message_handler: Any | None = None, notification_handler: Any | None = None) -> MCPConnectorRuntime | None:
        if not MCP_SDK_AVAILABLE:
            return None

        auth_mode = str(resolve_config_value(config, "auth_mode") or "").strip().lower()
        if auth_mode != "mcp":
            return None

        bundle = resolve_config_dict(config, "credentials")
        if not bundle:
            return None

        server_url = str(
            bundle.get("server_url") or config.get("mcp_server_url") or ""
        ).strip()
        transport = str(bundle.get("transport") or config.get("mcp_transport") or "streamable_http").strip().lower()
        fallback_transport = str(
            bundle.get("fallback_transport")
            or config.get("mcp_fallback_transport")
            or (
                "sse"
                if config.get("mcp_sse_fallback", transport == "streamable_http")
                else ""
            )
        ).strip().lower() or None
        if transport not in {"streamable_http", "sse"}:
            raise MCPRuntimeError(f"Unsupported MCP transport: {transport}")
        if fallback_transport == transport:
            fallback_transport = None
        if fallback_transport not in {None, "sse", "streamable_http"}:
            raise MCPRuntimeError(f"Unsupported MCP fallback transport: {fallback_transport}")
        if not server_url:
            return None

        anonymous = str(bundle.get("oauth_mode") or config.get("oauth_mode") or "").lower() == "none"
        client_info = None
        tokens = None
        client_metadata = None
        client_info_data = bundle.get("client_info")
        if anonymous:
            client_metadata = None
        elif not isinstance(client_info_data, dict):
            return None
        else:
            try:
                client_info = OAuthClientInformationFull.model_validate(client_info_data)
            except Exception as exc:  # noqa: BLE001
                raise MCPRuntimeError(f"Invalid MCP client info bundle: {exc}") from exc
            tokens = cls._tokens_from_bundle(bundle)
            if tokens is None:
                return None
            client_metadata = cls._client_metadata_from_client_info(client_info)
        oauth_metadata = cls._metadata_from_bundle(
            bundle.get("oauth_metadata"), OAuthMetadata
        )
        resource_metadata = cls._metadata_from_bundle(
            bundle.get("resource_metadata"), ProtectedResourceMetadata
        )
        declared_tools = tuple(
            str(tool).strip()
            for tool in (bundle.get("mcp_tools") or config.get("mcp_tools") or [])
            if str(tool).strip()
        )
        api_key = str(bundle.get("api_key") or "").strip()
        api_key_header = str(bundle.get("api_key_header") or "").strip()
        headers = {api_key_header: api_key} if api_key and api_key_header else {}

        return cls(
            server_url=server_url,
            client_metadata=client_metadata,
            storage=_InMemoryTokenStorage(tokens=tokens, client_info=client_info, on_tokens_updated=on_tokens_updated),
            oauth_metadata=oauth_metadata,
            resource_metadata=resource_metadata,
            declared_tools=declared_tools,
            transport=transport,
            fallback_transport=fallback_transport,
            message_handler=message_handler,
            notification_handler=notification_handler,
            anonymous=anonymous,
            headers=headers,
        )

    @staticmethod
    def _client_metadata_from_client_info(
        client_info: OAuthClientInformationFull,
    ) -> OAuthClientMetadata:
        payload = client_info.model_dump(mode="json", exclude_none=True)
        for key in (
            "client_id",
            "client_secret",
            "client_id_issued_at",
            "client_secret_expires_at",
        ):
            payload.pop(key, None)
        if not payload.get("token_endpoint_auth_method"):
            payload["token_endpoint_auth_method"] = "none"
        return OAuthClientMetadata.model_validate(payload)

    @staticmethod
    def _tokens_from_bundle(bundle: dict[str, Any]) -> OAuthToken | None:
        access_token = str(
            bundle.get("access_token") or bundle.get("token") or ""
        ).strip()
        refresh_token = str(bundle.get("refresh_token") or "").strip() or None
        if not access_token and not refresh_token:
            return None
        payload: dict[str, Any] = {
            "access_token": access_token or bundle.get("token") or "",
            "token_type": str(bundle.get("token_type") or "Bearer"),
            "refresh_token": refresh_token,
        }
        if bundle.get("expires_in") is not None:
            payload["expires_in"] = bundle.get("expires_in")
        scope = bundle.get("scope")
        if isinstance(scope, str) and scope.strip():
            payload["scope"] = scope.strip()
        elif isinstance(bundle.get("scopes"), list):
            scopes = [
                str(item).strip() for item in bundle["scopes"] if str(item).strip()
            ]
            if scopes:
                payload["scope"] = " ".join(scopes)
        return OAuthToken.model_validate(payload)

    @staticmethod
    def _metadata_from_bundle(
        raw: Any,
        model: Any,
    ) -> Any | None:
        if not isinstance(raw, dict):
            return None
        try:
            return model.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise MCPRuntimeError(f"Invalid MCP metadata bundle: {exc}") from exc

    @staticmethod
    def _text_from_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict | list):
            try:
                return json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                return str(content)
        return str(content).strip()

    @staticmethod
    def _result_content_to_text(result: Any) -> str:
        parts: list[str] = []
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            text = MCPConnectorRuntime._text_from_content(structured)
            if text:
                parts.append(text)

        for item in getattr(result, "content", []) or []:
            if isinstance(item, dict):
                item_type_raw = item.get("type", "")
            else:
                item_type_raw = getattr(item, "type", "")
            item_type = str(item_type_raw or "").lower()
            if item_type == "text":
                if isinstance(item, dict):
                    text_value: Any = item.get("text")
                else:
                    text_value = getattr(item, "text", None)
                rendered = MCPConnectorRuntime._text_from_content(text_value)
                if rendered:
                    parts.append(rendered)
                continue
            if item_type == "resource":
                resource = getattr(item, "resource", None)
                if resource is None and isinstance(item, dict):
                    resource = item.get("resource")
                resource_payload = MCPConnectorRuntime._dump_json_value(resource)
                rendered = MCPConnectorRuntime._text_from_content(resource_payload)
                if rendered:
                    parts.append(rendered)
                continue

            rendered = MCPConnectorRuntime._text_from_content(item)
            if rendered:
                parts.append(rendered)

        return "\n\n".join(part for part in parts if part.strip()).strip()

    @staticmethod
    def _dump_json_value(value: Any) -> Any:
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json", exclude_none=True)
        return value

    @staticmethod
    def _extract_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in (
                "items",
                "results",
                "messages",
                "threads",
                "files",
                "events",
                "pages",
                "documents",
                "entries",
                "blocks",
            ):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []

    @staticmethod
    def _record_identifier(record: dict[str, Any]) -> str | None:
        for key in (
            "id",
            "file_id",
            "threadId",
            "thread_id",
            "message_id",
            "messageId",
            "page_id",
            "pageId",
            "channel_id",
            "channelId",
            "path",
            "url",
        ):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _session_client(self) -> OAuthClientProvider | None:
        if not MCP_SDK_AVAILABLE:
            raise MCPRuntimeError("MCP SDK is not installed.")
        if self.anonymous:
            return None
        return OAuthClientProvider(
            server_url=self.server_url,
            client_metadata=self.client_metadata,
            storage=self.storage,
            timeout=self.timeout,
        )

    @asynccontextmanager
    async def _session_for_transport(self, transport: str) -> AsyncIterator[ClientSession]:
        if not MCP_SDK_AVAILABLE:
            raise MCPRuntimeError("MCP SDK is not installed.")
        async def _handle_message(message: Any) -> None:
            raw = getattr(getattr(message, "message", message), "root", None)
            raw = raw or getattr(message, "message", message)
            method = getattr(raw, "method", None)
            if self.notification_handler is not None and method:
                result = self.notification_handler(
                    str(method),
                    getattr(raw, "params", None),
                )
                if hasattr(result, "__await__"):
                    await result
            from mcp.client.session import _default_message_handler
            await _default_message_handler(message)

        if transport == "sse":
            auth = self._session_client()
            async with create_mcp_http_client(headers=self.headers or None, auth=auth) as http_client:
                async with sse_client(self.server_url, http_client=http_client) as streams:
                    read_stream, write_stream = streams
                    async with ClientSession(read_stream, write_stream, message_handler=self.message_handler or _handle_message) as session:
                        await session.initialize()
                        yield session
            return

        auth = self._session_client()
        async with create_mcp_http_client(headers=self.headers or None, auth=auth) as http_client:
            async with streamable_http_client(self.server_url, http_client=http_client) as streams:
                read_stream, write_stream, _session_id = streams
                async with ClientSession(read_stream, write_stream, message_handler=self.message_handler or _handle_message) as session:
                    await session.initialize()
                    yield session

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ClientSession]:
        """Open the configured transport, falling back only on initialization.

        A fallback is never attempted after a session has been yielded. This
        prevents retrying a potentially side-effecting tool call over another
        transport after the primary connection was already usable.
        """
        transports = [self.transport]
        if self.fallback_transport and self.fallback_transport not in transports:
            transports.append(self.fallback_transport)
        last_error: Exception | None = None
        for transport in transports:
            yielded = False
            try:
                async with self._session_for_transport(transport) as session:
                    yielded = True
                    if transport != self.transport:
                        logger.warning(
                            "MCP transport fallback activated: %s -> %s",
                            self.transport,
                            transport,
                        )
                    yield session
                    return
            except Exception as exc:  # noqa: BLE001
                if yielded or transport == transports[-1]:
                    raise
                last_error = exc
                logger.warning(
                    "MCP transport %s failed during initialization; trying %s: %s",
                    transport,
                    transports[transports.index(transport) + 1],
                    exc,
                )
        if last_error is not None:
            raise last_error

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self.session() as session:
            items: list[dict[str, Any]] = []
            cursor = None
            for _ in range(100):
                result = await session.list_tools(cursor=cursor)
                items.extend(MCPConnectorRuntime._dump_json_value(tool) for tool in result.tools)
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
            return items

    async def list_prompts(self) -> list[dict[str, Any]]:
        async with self.session() as session:
            if not getattr(session, "list_prompts", None):
                return []
            items: list[dict[str, Any]] = []
            cursor = None
            for _ in range(100):
                result = await session.list_prompts(cursor=cursor)
                items.extend(MCPConnectorRuntime._dump_json_value(item) for item in result.prompts)
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
            return items

    async def list_resources(self) -> list[dict[str, Any]]:
        async with self.session() as session:
            if not getattr(session, "list_resources", None):
                return []
            items: list[dict[str, Any]] = []
            cursor = None
            for _ in range(100):
                result = await session.list_resources(cursor=cursor)
                items.extend(MCPConnectorRuntime._dump_json_value(item) for item in result.resources)
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
            return items

    async def list_resource_templates(self) -> list[dict[str, Any]]:
        async with self.session() as session:
            if not getattr(session, "list_resource_templates", None):
                return []
            items: list[dict[str, Any]] = []
            cursor = None
            for _ in range(100):
                result = await session.list_resource_templates(cursor=cursor)
                items.extend(MCPConnectorRuntime._dump_json_value(item) for item in result.resourceTemplates)
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
            return items

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with self.session() as session:
                    return await session.call_tool(name, arguments or {})
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == 2:
                    break
                await anyio.sleep(0.25 * (2**attempt))
        raise MCPRuntimeError(f"MCP tool {name} failed after reconnect attempts: {last_error}") from last_error

    async def validate_tools(
        self, *, provider: str, expected_tools: Iterable[str]
    ) -> dict[str, Any]:
        tool_catalog = await self.list_tools()
        available = sorted(
            {
                str(tool.get("name") or "").strip()
                for tool in tool_catalog
                if str(tool.get("name") or "").strip()
            }
        )
        missing = [tool for tool in expected_tools if tool not in available]
        if missing:
            return build_health_report(
                status="degraded",
                healthy=False,
                message=f"MCP server is missing expected tools: {', '.join(missing)}.",
                error_code="missing_tools",
                metadata={
                    "provider": provider,
                    "mcp_server_url": self.server_url,
                    "available_tools": available,
                    "missing_tools": missing,
                },
            )
        return build_health_report(
            status="healthy",
            healthy=True,
            metadata={
                "provider": provider,
                "mcp_server_url": self.server_url,
                "available_tools": available,
            },
        )

    async def snapshot_from_tool_call(
        self,
        *,
        provider: str,
        tool_name: str,
        arguments: dict[str, Any],
        title: str,
        scope_label: str,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = await self.call_tool(tool_name, arguments)
        if bool(getattr(result, "isError", False)):
            rendered = self._result_content_to_text(result)
            raise MCPRuntimeError(rendered or f"MCP tool call failed: {tool_name}")

        rendered = self._result_content_to_text(result)
        if not rendered:
            return {
                "status": "skipped",
                "message": f"{provider} MCP tool {tool_name} returned no content.",
                "metadata": {
                    "provider": provider,
                    "tool": tool_name,
                    "scope": scope_label,
                    **(metadata or {}),
                },
            }

        markdown_content = (
            f"# {title}\n\n"
            f"**Scope:** {scope_label}\n"
            f"**Tool:** {tool_name}\n\n"
            f"{rendered}"
        )
        content_hash = hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()
        return {
            "status": "success",
            "title": title,
            "payload": markdown_content,
            "filename": filename,
            "hash": content_hash,
            "metadata": {
                "provider": provider,
                "tool": tool_name,
                "scope": scope_label,
                "mcp_server_url": self.server_url,
                **(metadata or {}),
            },
        }


def build_mcp_runtime(config: dict[str, Any], *, on_tokens_updated: Any | None = None, message_handler: Any | None = None, notification_handler: Any | None = None) -> MCPConnectorRuntime | None:
    try:
        return MCPConnectorRuntime.from_config(config, on_tokens_updated=on_tokens_updated, message_handler=message_handler, notification_handler=notification_handler)
    except MCPRuntimeError as exc:
        logger.warning("Unable to build MCP runtime: %s", exc)
        return None


def build_mcp_server_runtime(
    *,
    db: Session,
    settings: Settings,
    server: MCPServer,
    message_handler: Any | None = None,
    notification_handler: Any | None = None,
) -> MCPConnectorRuntime | None:
    """Build a runtime from a durable generic MCP server record.

    OAuth material is decrypted only for the lifetime of this runtime and is
    never copied back into the server JSON configuration. Refreshed tokens are
    encrypted back into ``mcp_oauth_tokens`` through the callback supplied to
    the SDK token storage.
    """
    from sqlalchemy import select

    token_record = db.execute(
        select(MCPOAuthToken).where(
            MCPOAuthToken.server_id == server.id,
            MCPOAuthToken.tenant_id == server.tenant_id,
        )
    ).scalar_one_or_none()
    config = dict(server.config or {})
    if token_record is None and str(config.get("oauth_mode") or "").lower() != "none":
        return None
    crypto = ConnectorSecretCrypto(settings)
    if token_record is None:
        token_payload = {}
    else:
        try:
            plaintext = crypto.decrypt(
                ciphertext=token_record.secret_ciphertext,
                nonce=token_record.secret_nonce,
                kid=token_record.secret_kid,
                aad=str(server.tenant_id).encode(),
            )
            token_payload = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise MCPRuntimeError(f"Unable to decrypt MCP OAuth token: {exc}") from exc
    if not isinstance(token_payload, dict):
        raise MCPRuntimeError("MCP OAuth token payload is invalid")

    credentials = dict(config)
    credentials.update(token_payload)
    credentials["auth_mode"] = "mcp"
    credentials["transport"] = server.transport
    credentials["server_url"] = config.get("server_url")
    credentials["client_info"] = config.get("oauth_client_info")
    credentials["client_metadata"] = config.get("client_metadata")
    credentials["oauth_metadata"] = config.get("oauth_metadata")
    credentials["resource_metadata"] = config.get("resource_metadata")

    async def _persist(tokens: Any) -> None:
        if token_record is None:
            return
        payload = tokens.model_dump(mode="json", exclude_none=True) if hasattr(tokens, "model_dump") else dict(vars(tokens))
        encrypted = crypto.encrypt(json.dumps(payload, separators=(",", ":")), aad=str(server.tenant_id).encode())
        token_record.secret_ciphertext = encrypted.ciphertext
        token_record.secret_nonce = encrypted.nonce
        token_record.secret_kid = encrypted.kid
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            from datetime import UTC, datetime, timedelta
            try:
                token_record.expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                pass
        db.add(token_record)
        from app.integrations.repositories.mcp_events import MCPEventsRepository
        MCPEventsRepository(db).append(
            tenant_id=server.tenant_id,
            server_id=server.id,
            user_id=server.user_id,
            event_type="oauth_token_refreshed",
            payload={"has_refresh_token": bool(payload.get("refresh_token")), "expires_in": payload.get("expires_in")},
        )
        db.commit()

    return build_mcp_runtime(
        {"auth_mode": "mcp", "credentials": credentials, **config},
        on_tokens_updated=_persist,
        message_handler=message_handler,
        notification_handler=notification_handler,
    )


async def execute_mcp_server_tool(
    *,
    db: Session,
    settings: Settings,
    server: MCPServer,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute a tool for a generic installed MCP server and persist its events."""
    from app.integrations.repositories.mcp_events import MCPEventsRepository

    def _redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): ("[REDACTED]" if any(marker in str(key).lower() for marker in ("token", "secret", "password", "authorization", "code")) else _redact(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [_redact(item) for item in value]
        return value

    events = MCPEventsRepository(db)
    events.append(
        tenant_id=server.tenant_id,
        user_id=server.user_id,
        server_id=server.id,
        event_type="tool_call_started",
        payload={"tool": tool_name, "arguments": _redact(arguments)},
    )
    runtime = build_mcp_server_runtime(db=db, settings=settings, server=server)
    if runtime is None:
        events.append(
            tenant_id=server.tenant_id,
            user_id=server.user_id,
            server_id=server.id,
            event_type="tool_call_failed",
            payload={"tool": tool_name, "error": "MCP server is not authenticated"},
        )
        db.commit()
        return {"status": "error", "message": "MCP server is not authenticated", "is_error": True}
    try:
        result = await runtime.call_tool(tool_name, arguments)
        payload = serialize_mcp_result(result)
        events.append(
            tenant_id=server.tenant_id,
            user_id=server.user_id,
            server_id=server.id,
            event_type="tool_call_completed",
            payload={"tool": tool_name, "result": payload},
        )
        db.commit()
        return payload
    except Exception as exc:  # noqa: BLE001
        events.append(
            tenant_id=server.tenant_id,
            user_id=server.user_id,
            server_id=server.id,
            event_type="tool_call_failed",
            payload={"tool": tool_name, "error": str(exc)},
        )
        db.commit()
        return {"status": "error", "message": str(exc), "is_error": True}


def render_mcp_result_text(result: Any) -> str:
    if not MCP_SDK_AVAILABLE:
        return ""
    return MCPConnectorRuntime._result_content_to_text(result)


def serialize_mcp_result(result: Any) -> dict[str, Any]:
    payload: dict[str, Any]
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json", exclude_none=True)
        payload = dumped if isinstance(dumped, dict) else {"result": dumped}
    elif hasattr(result, "__dict__"):
        payload = {
            key: value for key, value in vars(result).items() if not key.startswith("_")
        }
    else:
        payload = {"result": result}
    payload["rendered_text"] = render_mcp_result_text(result)
    payload["is_error"] = bool(getattr(result, "isError", False))
    return payload


async def validate_mcp_runtime(
    runtime: MCPConnectorRuntime,
    *,
    provider: str,
    expected_tools: Iterable[str],
) -> dict[str, Any]:
    try:
        return await runtime.validate_tools(
            provider=provider, expected_tools=expected_tools
        )
    except Exception as exc:  # noqa: BLE001
        status, error_code = classify_health_status(exception=exc, message=str(exc))
        return build_health_report(
            status=status,
            healthy=False,
            message=str(exc),
            error_code=error_code,
            metadata={
                "provider": provider,
                "mcp_server_url": runtime.server_url,
            },
        )


async def sync_google_drive(
    runtime: MCPConnectorRuntime, config: dict[str, Any]
) -> dict[str, Any]:
    folder_id = str(resolve_config_value(config, "folder_id") or "").strip() or None
    page_size = max(1, min(int(resolve_config_value(config, "page_size") or 50), 100))
    max_files = max(
        1, min(int(resolve_config_value(config, "max_files") or page_size * 4), 250)
    )
    arguments: dict[str, Any] = {
        "page_size": page_size,
        "max_results": max_files,
    }
    if folder_id:
        arguments["folder_id"] = folder_id
        arguments["query"] = folder_id

    scope_label = f"folder {folder_id}" if folder_id else "entire Drive"
    scope_key = folder_id or "full_drive"
    result = await runtime.snapshot_from_tool_call(
        provider="google-drive",
        tool_name="search_files",
        arguments=arguments,
        title="Google Drive MCP Sync",
        scope_label=scope_label,
        filename=f"google_drive_{scope_key.replace('/', '_')[:40]}.md",
        metadata={
            "folder_id": folder_id,
            "page_size": page_size,
            "max_files": max_files,
        },
    )
    if result.get("status") != "success":
        return result
    result["message"] = (
        f"Successfully ingested MCP snapshot from Google Drive ({scope_label})."
    )
    return result


async def sync_gmail(
    runtime: MCPConnectorRuntime, config: dict[str, Any]
) -> dict[str, Any]:
    query = str(resolve_config_value(config, "query") or "newer_than:30d").strip()
    max_results = max(
        1, min(int(resolve_config_value(config, "max_results") or 25), 50)
    )
    result = await runtime.snapshot_from_tool_call(
        provider="gmail",
        tool_name="search_threads",
        arguments={"query": query, "max_results": max_results},
        title="Gmail MCP Sync",
        scope_label=f"query {query}",
        filename=f"gmail_{hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]}.md",
        metadata={"query": query, "max_results": max_results},
    )
    if result.get("status") != "success":
        return result
    result["message"] = f"Successfully ingested MCP snapshot from Gmail ({query})."
    return result


async def sync_google_calendar(
    runtime: MCPConnectorRuntime,
    config: dict[str, Any],
) -> dict[str, Any]:
    time_min = str(resolve_config_value(config, "time_min") or "").strip() or None
    max_results = max(
        1, min(int(resolve_config_value(config, "max_results") or 20), 50)
    )
    result = await runtime.snapshot_from_tool_call(
        provider="google-calendar",
        tool_name="list_events",
        arguments={"time_min": time_min, "max_results": max_results},
        title="Google Calendar MCP Sync",
        scope_label=time_min or "upcoming window",
        filename="google_calendar_upcoming_events.md",
        metadata={"time_min": time_min, "max_results": max_results},
    )
    if result.get("status") != "success":
        return result
    result["message"] = (
        f"Successfully ingested MCP snapshot from Google Calendar ({time_min or 'upcoming window'})."
    )
    return result


async def sync_github(
    runtime: MCPConnectorRuntime, config: dict[str, Any]
) -> dict[str, Any]:
    repo_owner = str(resolve_config_value(config, "repo_owner") or "").strip()
    repo_name = str(resolve_config_value(config, "repo_name") or "").strip()
    repo_url = str(resolve_config_value(config, "repo_url") or "").strip()
    branch = str(resolve_config_value(config, "branch") or "main").strip() or "main"
    path = str(resolve_config_value(config, "path") or "").strip().strip("/")
    query = str(resolve_config_value(config, "query") or "").strip()
    if not repo_owner or not repo_name:
        if repo_url:
            try:
                from urllib.parse import urlparse

                parsed = urlparse(repo_url)
                parts = [part for part in parsed.path.strip("/").split("/") if part]
                if len(parts) >= 2:
                    repo_owner = repo_owner or parts[0]
                    repo_name = repo_name or parts[1].removesuffix(".git")
            except Exception:  # noqa: BLE001
                pass
    if not repo_owner or not repo_name:
        raise MCPRuntimeError("GitHub repository owner and name are required.")

    search_terms = " ".join(
        part
        for part in (
            f"repo:{repo_owner}/{repo_name}",
            f"branch:{branch}",
            f"path:{path}" if path else "",
            query,
        )
        if part
    ).strip()
    result = await runtime.snapshot_from_tool_call(
        provider="github",
        tool_name="search",
        arguments={"query": search_terms, "max_results": 20},
        title="GitHub MCP Sync",
        scope_label=f"{repo_owner}/{repo_name}@{branch}"
        + (f" path {path}" if path else ""),
        filename=f"github_{repo_name}_{branch}.md",
        metadata={
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "branch": branch,
            "path": path,
            "query": query,
        },
    )
    if result.get("status") != "success":
        return result
    result["message"] = (
        f"Successfully ingested MCP snapshot from GitHub ({repo_owner}/{repo_name})."
    )
    return result


async def sync_slack(
    runtime: MCPConnectorRuntime, config: dict[str, Any]
) -> dict[str, Any]:
    channel_id = str(resolve_config_value(config, "channel_id") or "").strip()
    limit = max(1, min(int(resolve_config_value(config, "limit") or 100), 200))
    if not channel_id:
        raise MCPRuntimeError("Slack channel_id is required.")

    result = await runtime.snapshot_from_tool_call(
        provider="slack",
        tool_name="slack_read_channel",
        arguments={"channel_id": channel_id, "limit": limit},
        title="Slack MCP Sync",
        scope_label=f"channel {channel_id}",
        filename=f"slack_{channel_id}_history.md",
        metadata={"channel_id": channel_id, "limit": limit},
    )
    if result.get("status") != "success":
        return result
    result["message"] = (
        f"Successfully ingested MCP snapshot from Slack channel {channel_id}."
    )
    return result


async def sync_notion(
    runtime: MCPConnectorRuntime, config: dict[str, Any]
) -> dict[str, Any]:
    page_id = str(resolve_config_value(config, "page_id", "workspace_id") or "").strip()
    if not page_id:
        raise MCPRuntimeError("Notion page_id is required.")

    clean_page_id = page_id.replace("-", "")
    result = await runtime.snapshot_from_tool_call(
        provider="notion",
        tool_name="fetch",
        arguments={"page_id": clean_page_id},
        title="Notion MCP Sync",
        scope_label=f"page {clean_page_id}",
        filename=f"notion_{clean_page_id}.md",
        metadata={"page_id": clean_page_id},
    )
    if result.get("status") != "success":
        return result
    result["message"] = (
        f"Successfully ingested MCP snapshot from Notion page {clean_page_id}."
    )
    return result


async def execute_mcp_tool(
    *,
    db: Session,
    settings: Settings,
    connector: Connector,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Universal entry point for executing any MCP tool.
    Handles credential decryption, runtime initialization, and tool execution.
    """
    # 1. Load credentials
    crypto = ConnectorSecretCrypto(settings)
    from sqlalchemy import select

    stmt = select(ConnectorSecret).where(
        ConnectorSecret.connector_id == connector.id,
        ConnectorSecret.secret_type == "credentials",
    )
    secret = db.execute(stmt).scalars().first()
    if not secret:
        return {
            "status": "error",
            "message": f"No credentials found for connector {connector.id}",
        }

    decrypted = crypto.decrypt(
        ciphertext=secret.secret_ciphertext,
        nonce=secret.secret_nonce,
        kid=secret.secret_kid,
        aad=str(connector.tenant_id).encode(),
    )
    credentials = json.loads(decrypted.decode("utf-8"))

    async def _persist_refreshed_tokens(tokens: Any) -> None:
        """Persist SDK refreshes through the existing encrypted secret record."""
        token_payload = (
            tokens.model_dump(mode="json", exclude_none=True)
            if hasattr(tokens, "model_dump")
            else dict(vars(tokens))
        )
        credentials.update(token_payload)
        encrypted = crypto.encrypt(
            json.dumps(credentials, separators=(",", ":")),
            aad=str(connector.tenant_id).encode(),
        )
        secret.secret_ciphertext = encrypted.ciphertext
        secret.secret_nonce = encrypted.nonce
        secret.secret_kid = encrypted.kid
        db.add(secret)
        db.commit()

    # 2. Build runtime config
    config = {
        "auth_mode": "mcp",
        "credentials": credentials,
        "mcp_server_url": (
            connector.config.get("mcp_server_url") if connector.config else None
        ),
    }

    # 3. Build runtime
    runtime = build_mcp_runtime(config, on_tokens_updated=_persist_refreshed_tokens)
    if not runtime:
        return {
            "status": "error",
            "message": "Failed to initialize MCP runtime.",
        }

    # 4. Call tool
    try:
        result = await runtime.call_tool(tool_name, arguments)
        return serialize_mcp_result(result)
    except Exception as exc:
        logger.exception("MCP tool execution failed: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
            "is_error": True,
        }


class UniversalMCPConnector(ConnectorService):
    """
    Universal MCP-backed connector that routes to specialized sync helpers.
    """

    def sync(self) -> dict[str, Any]:
        config = self.connector.config or {}
        runtime = build_mcp_runtime(config)
        if not runtime:
            return {
                "status": "error",
                "message": "Failed to initialize MCP runtime.",
            }

        # Determine integration slug for routing
        from app.integrations.models.integration import Integration

        integration = self.session.get(Integration, self.connector.integration_id)
        slug = integration.slug if integration else "unknown"

        # Mapping table for MCP sync functions
        sync_map = {
            "google-drive": sync_google_drive,
            "gmail": sync_gmail,
            "google-calendar": sync_google_calendar,
            "github": sync_github,
            "slack": sync_slack,
            "notion": sync_notion,
        }

        sync_fn = sync_map.get(slug)
        if not sync_fn:
            return {
                "status": "error",
                "message": f"MCP sync not implemented for integration: {slug}",
            }

        try:
            return anyio.run(sync_fn, runtime, config)
        except Exception as exc:
            logger.exception("MCP sync failed for %s: %s", slug, exc)
            return {
                "status": "error",
                "message": str(exc),
            }

    def validate_config(self) -> bool:
        runtime = build_mcp_runtime(self.connector.config or {})
        return runtime is not None

    def validate_health(self) -> dict[str, Any]:
        runtime = build_mcp_runtime(self.connector.config or {})
        if not runtime:
            return build_health_report(
                status="degraded",
                healthy=False,
                message="Failed to build MCP runtime",
                error_code="mcp_runtime_init_failed",
            )

        from app.integrations.models.integration import Integration

        integration = self.session.get(Integration, self.connector.integration_id)
        slug = integration.slug if integration else "unknown"

        # Heuristic for expected tools
        tool_map = {
            "google-drive": ["search_files"],
            "gmail": ["search_threads"],
            "google-calendar": ["list_events"],
            "github": ["search"],
            "slack": ["slack_read_channel"],
            "notion": ["fetch"],
        }
        expected_tools = tool_map.get(slug, [])

        try:

            async def _validate() -> dict[str, Any]:
                return await validate_mcp_runtime(
                    runtime,
                    provider=slug,
                    expected_tools=expected_tools,
                )

            return anyio.run(_validate)
        except Exception as exc:
            return build_health_report(
                status="degraded",
                healthy=False,
                message=f"MCP health check failed: {exc}",
                error_code="mcp_health_check_failed",
            )
