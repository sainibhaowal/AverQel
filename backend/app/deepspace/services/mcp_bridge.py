"""Narrow bridge from DeepSpace tool calling to the existing MCP runtime.

This module deliberately owns no OAuth or transport logic. MCP connection
ownership, catalog freshness, policy, and remote execution remain in the MCP
integration service; DeepSpace discovers tools from the user's connected MCP
accounts and forwards approved calls through that service.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy
from app.integrations.models.mcp_server import MCPServer
from app.integrations.services.mcp_runtime import (
    MCPToolPolicyDecision,
    evaluate_mcp_tool_policy,
    execute_mcp_server_tool,
    mcp_catalog_is_fresh,
    mcp_server_provider_available,
)


def _safe_function_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "tool"
    return normalized[:48]


@dataclass(frozen=True, slots=True)
class DeepSpaceMCPTool:
    """One namespaced, conversation-scoped MCP tool binding."""

    exposed_name: str
    server: MCPServer
    raw_name: str
    catalog: dict[str, Any]

    @property
    def definition(self) -> dict[str, Any]:
        schema = self.catalog.get("inputSchema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": False}
        else:
            schema = dict(schema)
            schema.pop("$schema", None)
            schema["type"] = "object"
            if not isinstance(schema.get("properties"), dict):
                schema["properties"] = {}
            schema.setdefault("additionalProperties", False)

        description = str(self.catalog.get("description") or "MCP tool").strip()
        return {
            "type": "function",
            "function": {
                "name": self.exposed_name,
                "description": (
                    f"MCP server {self.server.name!r}, tool {self.raw_name!r}. {description} "
                    "Use only for the user's explicitly requested connected service action."
                )[:4000],
                "parameters": schema,
            },
        }


class DeepSpaceMCPBridge:
    """Discover and execute tools from the user's connected MCP accounts."""

    MAX_SERVERS = 50
    MAX_TOOLS_PER_SERVER = 100

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    @staticmethod
    def _exposed_name(server: MCPServer, raw_name: str) -> str:
        # The short server id prevents collisions between two providers that
        # publish the same tool name while keeping the model-facing name small.
        return f"mcp_{server.id.hex[:10]}_{_safe_function_name(raw_name)}"[:64]

    def tools_for_conversation(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
    ) -> dict[str, DeepSpaceMCPTool]:
        # Lightweight provider/service test doubles do not expose a database
        # execute method; MCP remains simply unavailable in that environment.
        if not callable(getattr(self.db, "execute", None)):
            return {}
        servers = self.db.execute(
            select(MCPServer)
            .where(
                MCPServer.tenant_id == auth.tenant_id,
                MCPServer.user_id == auth.user_id,
                MCPServer.enabled.is_(True),
                MCPServer.status == "connected",
            )
            .order_by(MCPServer.created_at.desc())
            .limit(self.MAX_SERVERS)
        ).scalars().all()

        bindings: dict[str, DeepSpaceMCPTool] = {}
        max_age = int(getattr(self.settings, "mcp_catalog_max_age_seconds", 3600))
        for server in servers:
            provider_available, _reason = mcp_server_provider_available(self.db, server)
            if not provider_available or not mcp_catalog_is_fresh(server, max_age_seconds=max_age):
                continue

            config = server.config if isinstance(server.config, dict) else {}
            cached_tools = config.get("mcp_tools_cache")
            if not isinstance(cached_tools, list):
                continue

            policy = self.db.execute(
                select(MCPConnectionPolicy).where(
                    MCPConnectionPolicy.server_id == server.id,
                    MCPConnectionPolicy.tenant_id == auth.tenant_id,
                    MCPConnectionPolicy.user_id == auth.user_id,
                )
            ).scalar_one_or_none()
            if policy is None or not policy.default_enabled:
                continue
            for raw_tool in cached_tools[: self.MAX_TOOLS_PER_SERVER]:
                if not isinstance(raw_tool, dict):
                    continue
                raw_name = str(raw_tool.get("name") or "").strip()
                if not raw_name:
                    continue
                exposed_name = self._exposed_name(server, raw_name)
                bindings[exposed_name] = DeepSpaceMCPTool(
                    exposed_name=exposed_name,
                    server=server,
                    raw_name=raw_name,
                    catalog=dict(raw_tool),
                )
        return bindings

    def policy_for_tool(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        binding: DeepSpaceMCPTool,
    ) -> MCPToolPolicyDecision:
        return evaluate_mcp_tool_policy(
            db=self.db,
            server=binding.server,
            tool_name=binding.raw_name,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
            tool=binding.catalog,
            expected_catalog_revision=binding.server.catalog_revision,
            max_age_seconds=int(getattr(self.settings, "mcp_catalog_max_age_seconds", 3600)),
        )

    async def execute(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        binding: DeepSpaceMCPTool,
        arguments: dict[str, Any],
        approval_granted: bool = False,
    ) -> dict[str, Any]:
        return await execute_mcp_server_tool(
            db=self.db,
            settings=self.settings,
            server=binding.server,
            tool_name=binding.raw_name,
            arguments=arguments,
            conversation_id=conversation_id,
            approval_granted=approval_granted,
        )
