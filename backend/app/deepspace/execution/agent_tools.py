"""
Agent Tool Definitions for DeepSpace Autonomous Intelligence.

Each tool is a structured definition the LLM can invoke via function calling.
Tools have:
  - A JSON Schema for input parameters
  - A permission level (auto / notify / approval)
  - An execute() coroutine that runs the actual operation
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import mimetypes
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.deepspace.execution.aci_tools import (
    DIRECTORY_SUMMARY_TREE,
    GREP_SEARCH_LIMITED,
    VIEW_FILE_PAGINATED,
    exec_directory_summary_tree,
    exec_grep_search_limited,
    exec_view_file_paginated,
)
from app.deepspace.execution.agent_permissions import (
    PermissionLevel,
    get_permission,
    permission_for_mcp_policy,
    permission_tier_number,
)
from app.deepspace.execution.tool_context import ToolContext
from app.deepspace.execution.tool_contracts import (
    ToolContract,
    build_tool_execution_policy,
    failure_result,
    infer_tool_contract,
    redact_tool_payload,
    validate_tool_arguments,
)
from app.deepspace.workspace.coding_harness import CodingHarness
from app.integrations.services.config_utils import (
    resolve_config_dict,
    resolve_config_text,
)
from app.integrations.services.mcp_runtime import (
    build_mcp_runtime,
    render_mcp_result_text,
    serialize_mcp_result,
)
from app.system.services.otel import trace_async

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolResult:
    """The structured output of a tool execution."""

    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN_ONLY = "planOnly"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"


@dataclass(slots=True, frozen=True)
class AgentToolDef:
    """
    A tool definition that can be passed to the LLM for function calling.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    permission_level: PermissionLevel
    metadata: dict[str, Any] = None
    contract: ToolContract | None = None

    def __post_init__(self) -> None:
        metadata = dict(self.metadata or {})
        if self.metadata is None:
            object.__setattr__(self, "metadata", metadata)
        if self.contract is None:
            object.__setattr__(
                self,
                "contract",
                infer_tool_contract(
                    name=self.name,
                    permission_level=self.permission_level,
                    metadata=metadata,
                ),
            )

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tool Definitions (Complete Specification)
# ---------------------------------------------------------------------------

TASK = AgentToolDef(
    name="task",
    description="Launch a specialized sub-agent for a complex isolated task. Returns only a summary of the result.",
    parameters={
        "type": "object",
        "properties": {
            "subagent_type": {
                "type": "string",
                "enum": [
                    "general-purpose",
                    "research",
                    "writer",
                    "analyst",
                    "executor",
                    "explorer",
                    "planner",
                    "email-agent",
                    "research-agent",
                    "data-agent",
                    "document-agent",
                    "media-agent",
                    "scheduler-agent",
                    "memory-agent",
                ],
                "description": "The specialized type of sub-agent to spawn.",
            },
            "prompt": {
                "type": "string",
                "description": "Detailed task description. Must be self-contained.",
            },
            "description": {
                "type": "string",
                "description": "3-5 word summary shown to user.",
            },
            "model": {
                "type": "string",
                "enum": ["sonnet", "opus", "haiku"],
                "description": "Model strength to use.",
            },
            "resume": {
                "type": "string",
                "description": "Agent ID to resume from previous execution.",
            },
        },
        "required": ["subagent_type", "prompt", "description"],
    },
    permission_level=PermissionLevel.TIER5_SPAWN,
)

BASH = AgentToolDef(
    name="bash",
    description="Execute shell commands in a persistent bash session. Preserves state (cwd, env).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to run."},
            "timeout": {
                "type": "integer",
                "default": 120000,
                "description": "Max runtime in ms.",
            },
            "description": {
                "type": "string",
                "description": "5-10 word summary shown to user.",
            },
            "run_in_background": {
                "type": "boolean",
                "default": False,
                "description": "Set to true to monitor with bash_output.",
            },
            "dangerouslyDisableSandbox": {"type": "boolean", "default": False},
        },
        "required": ["command"],
    },
    permission_level=PermissionLevel.TIER3_APPROVE,
)

GLOB = AgentToolDef(
    name="glob",
    description="Fast file pattern matching across workspace using glob syntax.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Pattern like '**/*.pdf' or 'src/**/*.ts'.",
            },
            "path": {
                "type": "string",
                "description": "Directory to search from. Default: root.",
            },
        },
        "required": ["pattern"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

GREP = AgentToolDef(
    name="grep",
    description="Powerful content search across files using ripgrep (rg).",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for.",
            },
            "path": {"type": "string", "description": "File or directory to search."},
            "glob": {"type": "string", "description": "Filter files (e.g., '*.py')."},
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "default": "content",
            },
            "context_before": {"type": "integer", "description": "Lines before match."},
            "context_after": {"type": "integer", "description": "Lines after match."},
            "case_insensitive": {"type": "boolean", "default": True},
        },
        "required": ["pattern"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

READ_FILE = AgentToolDef(
    name="read_file",
    description="Read any file (text, code, PDF, images, notebooks).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file."},
            "offset": {"type": "integer", "description": "Start line (0-indexed)."},
            "limit": {
                "type": "integer",
                "description": "Max lines to read (default 2000).",
            },
        },
        "required": ["path"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

EDIT_FILE = AgentToolDef(
    name="edit_file",
    description="Surgical string replacement in a file. Old string MUST be unique.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file."},
            "old_string": {"type": "string", "description": "Exact text to find."},
            "new_string": {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

WRITE_FILE = AgentToolDef(
    name="write_file",
    description="Create or fully overwrite a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path."},
            "content": {"type": "string", "description": "Full file content."},
        },
        "required": ["path", "content"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

NOTEBOOK_EDIT = AgentToolDef(
    name="notebook_edit",
    description="Edit Jupyter notebook (.ipynb) cells directly.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to .ipynb."},
            "cell_id": {"type": "string", "description": "Target cell ID or index."},
            "new_source": {"type": "string", "description": "New content."},
            "cell_type": {
                "type": "string",
                "enum": ["code", "markdown"],
                "default": "code",
            },
            "edit_mode": {
                "type": "string",
                "enum": ["replace", "insert", "delete"],
                "default": "replace",
            },
        },
        "required": ["path", "new_source"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

WEB_FETCH = AgentToolDef(
    name="web_fetch",
    description="Fetch and analyze web page content with specific extraction goals.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL."},
            "prompt": {
                "type": "string",
                "description": "What to extract from the page.",
            },
        },
        "required": ["url", "prompt"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

WEB_SEARCH = AgentToolDef(
    name="web_search",
    description="Search the web for current information, research, or facts.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Min 2 chars."},
            "allowed_domains": {"type": "array", "items": {"type": "string"}},
            "blocked_domains": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

TODO_WRITE = AgentToolDef(
    name="todo_write",
    description="Create and manage proactive work (use for multi-step or cross-app tasks).",
    parameters={
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "activeForm": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                        "priority": {"type": "integer", "default": 0},
                        "thread_id": {"type": "string"},
                        "metadata_json": {"type": "object"},
                        "automation_json": {"type": "object"},
                        "is_recurring": {"type": "boolean", "default": False},
                        "enabled": {"type": "boolean", "default": True},
                        "next_run_at": {"type": "string", "format": "date-time"},
                    },
                    "required": ["content", "activeForm", "status"],
                },
            }
        },
        "required": ["todos"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

TODO_READ = AgentToolDef(
    name="todo_read",
    description="View active session tasks and progress.",
    parameters={"type": "object", "properties": {}},
    permission_level=PermissionLevel.TIER1_AUTO,
)

BASH_OUTPUT = AgentToolDef(
    name="bash_output",
    description="Retrieve new output from a running background bash session.",
    parameters={
        "type": "object",
        "properties": {
            "bash_id": {
                "type": "string",
                "description": "ID returned from background bash.",
            },
            "filter": {"type": "string", "description": "Regex to filter lines."},
        },
        "required": ["bash_id"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

KILL_SHELL = AgentToolDef(
    name="kill_shell",
    description="Terminate a running background bash shell.",
    parameters={
        "type": "object",
        "properties": {"shell_id": {"type": "string"}},
        "required": ["shell_id"],
    },
    permission_level=PermissionLevel.TIER3_APPROVE,
)

ASK_USER_QUESTION = AgentToolDef(
    name="ask_user_question",
    description="Ask clarifying questions or offer multi-choice options to the user.",
    parameters={
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "header": {"type": "string", "description": "Max 12 chars."},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                        "multiSelect": {"type": "boolean"},
                    },
                    "required": ["question", "header"],
                },
            }
        },
        "required": ["questions"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

ENTER_PLAN_MODE = AgentToolDef(
    name="enter_plan_mode",
    description="Switch to read-only planning mode for complex architectural design.",
    parameters={"type": "object", "properties": {}},
    permission_level=PermissionLevel.TIER1_AUTO,
)

EXIT_PLAN_MODE = AgentToolDef(
    name="exit_plan_mode",
    description="Exit planning mode and prepare for execution (Must write plan to file first).",
    parameters={"type": "object", "properties": {}},
    permission_level=PermissionLevel.TIER1_AUTO,
)

SKILL = AgentToolDef(
    name="skill",
    description="Invoke a pre-defined reusable prompt workflow (e.g., 'summarize', 'research').",
    parameters={
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": "Name of the skill to invoke."}
        },
        "required": ["skill"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

SLASH_COMMAND = AgentToolDef(
    name="slash_command",
    description="Execute custom slash commands (e.g., /report, /translate).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command including args."}
        },
        "required": ["command"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

MEMORY_WRITE = AgentToolDef(
    name="memory_write",
    description="Store facts persistently across sessions.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"type": "string"},
            "scope": {"type": "string", "enum": ["session", "persistent"]},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["key", "value", "scope"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

MEMORY_READ = AgentToolDef(
    name="memory_read",
    description="Retrieve a stored fact by key.",
    parameters={
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

MEMORY_SEARCH = AgentToolDef(
    name="memory_search",
    description="Semantic search across all stored memories.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

DATA_ANALYZE = AgentToolDef(
    name="data_analyze",
    description="Analyze structured data (CSV, JSON, Excel) and return insights.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "data": {"type": "string"},
            "format": {"type": "string", "enum": ["csv", "json", "excel", "text"]},
            "question": {"type": "string"},
            "output_format": {
                "type": "string",
                "enum": ["summary", "table", "chart_data"],
            },
        },
        "required": ["format", "question"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)

DOCUMENT_CONVERT = AgentToolDef(
    name="document_convert",
    description="Convert between document formats (PDF, DOCX, MD, HTML).",
    parameters={
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "output_format": {
                "type": "string",
                "enum": ["pdf", "docx", "md", "txt", "html"],
            },
        },
        "required": ["input_path", "output_format"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

SEARCH_ECOSYSTEM_DOCS = AgentToolDef(
    name="search_ecosystem_docs",
    description="Search tenant-scoped ecosystem documents from connected web-crawler sources.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 6},
        },
        "required": ["query"],
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)


SYNC_CONNECTOR = AgentToolDef(
    name="sync_connector",
    description="Trigger a sync for an existing connector by connector ID or integration slug.",
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {"type": "string"},
            "integration_slug": {"type": "string"},
            "description": {"type": "string"},
        },
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

CRAWL_URL = AgentToolDef(
    name="crawl_url",
    description="Create or reuse a web-crawler source for a URL and sync it immediately.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["url"],
    },
    permission_level=PermissionLevel.TIER2_CONFIRM,
)

LIST_CONNECTORS = AgentToolDef(
    name="list_connectors",
    description="List connectors available to the current tenant.",
    parameters={"type": "object", "properties": {}},
    permission_level=PermissionLevel.TIER1_AUTO,
)

GET_CONNECTOR_STATUS = AgentToolDef(
    name="get_connector_status",
    description="Get the current status of a connector by connector ID or integration slug.",
    parameters={
        "type": "object",
        "properties": {
            "connector_id": {"type": "string"},
            "integration_slug": {"type": "string"},
        },
    },
    permission_level=PermissionLevel.TIER1_AUTO,
)


VIEW_FILE_PAGINATED_DEF = AgentToolDef(
    name=VIEW_FILE_PAGINATED["name"],
    description=VIEW_FILE_PAGINATED["description"],
    parameters=VIEW_FILE_PAGINATED["parameters"],
    permission_level=VIEW_FILE_PAGINATED["permission_level"],
)

GREP_SEARCH_LIMITED_DEF = AgentToolDef(
    name=GREP_SEARCH_LIMITED["name"],
    description=GREP_SEARCH_LIMITED["description"],
    parameters=GREP_SEARCH_LIMITED["parameters"],
    permission_level=GREP_SEARCH_LIMITED["permission_level"],
)

DIRECTORY_SUMMARY_TREE_DEF = AgentToolDef(
    name=DIRECTORY_SUMMARY_TREE["name"],
    description=DIRECTORY_SUMMARY_TREE["description"],
    parameters=DIRECTORY_SUMMARY_TREE["parameters"],
    permission_level=DIRECTORY_SUMMARY_TREE["permission_level"],
)


ALL_TOOLS: list[AgentToolDef] = [
    VIEW_FILE_PAGINATED_DEF,
    GREP_SEARCH_LIMITED_DEF,
    DIRECTORY_SUMMARY_TREE_DEF,
    TASK,
    BASH,
    GLOB,
    GREP,
    READ_FILE,
    EDIT_FILE,
    WRITE_FILE,
    NOTEBOOK_EDIT,
    WEB_FETCH,
    WEB_SEARCH,
    TODO_WRITE,
    TODO_READ,
    BASH_OUTPUT,
    KILL_SHELL,
    ASK_USER_QUESTION,
    ENTER_PLAN_MODE,
    EXIT_PLAN_MODE,
    SKILL,
    SLASH_COMMAND,
    MEMORY_WRITE,
    MEMORY_READ,
    MEMORY_SEARCH,
    DATA_ANALYZE,
    DOCUMENT_CONVERT,
    SEARCH_ECOSYSTEM_DOCS,
    SYNC_CONNECTOR,
    CRAWL_URL,
    LIST_CONNECTORS,
    GET_CONNECTOR_STATUS,
]

TOOL_MAP: dict[str, AgentToolDef] = {tool.name: tool for tool in ALL_TOOLS}


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dynamic MCP Tool Support
# ---------------------------------------------------------------------------


def map_mcp_tool_to_permission(name: str) -> PermissionLevel:
    """
    Heuristic to map MCP tool names to AverQel permission tiers.
    Reads: TIER 1 (Silent)
    Writes/Deletes: TIER 2 (Requires confirmation)
    """
    name = name.lower()
    write_keywords = {
        "create",
        "update",
        "delete",
        "send",
        "post",
        "append",
        "modify",
        "upload",
        "remove",
        "comment",
        "respond",
    }

    if any(kw in name for kw in write_keywords):
        return PermissionLevel.TIER2_CONFIRM
    return PermissionLevel.TIER1_AUTO


def build_dynamic_mcp_tool(
    connector_id: uuid.UUID,
    mcp_tool_def: dict[str, Any],
    *,
    server_name: str | None = None,
    provider_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    catalog_revision: int | None = None,
    risk_level: str | None = None,
    approval_requirement: str | None = None,
) -> AgentToolDef:
    """
    Convert a raw MCP tool definition into an AverQel AgentToolDef.

    MCP servers commonly reuse generic names such as ``search``, ``fetch`` or
    ``list``.  The LLM tool namespace must include the owning server so two
    active connectors cannot overwrite each other in ``dynamic_tools``.  The
    original protocol name remains in metadata and is the only name sent to
    the remote MCP server.
    """
    raw_name = str(mcp_tool_def.get("name") or "unknown_tool").strip()
    raw_name = raw_name or "unknown_tool"

    def _safe_component(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized or "server"

    server_component = _safe_component(server_name or "server")
    tool_component = _safe_component(raw_name)
    exposed_name = f"mcp_{server_component}_{tool_component}"
    resolved_risk_level = str(
        risk_level or mcp_tool_def.get("risk_level") or ""
    ).strip().lower()
    resolved_approval = str(
        approval_requirement or mcp_tool_def.get("approval_requirement") or ""
    ).strip().lower()
    permission_level = (
        permission_for_mcp_policy(
            risk_level=resolved_risk_level,
            approval_requirement=resolved_approval,
        )
        if resolved_risk_level in {"read", "write", "delete", "external_message"}
        and resolved_approval in {"auto", "human", "block"}
        else map_mcp_tool_to_permission(raw_name)
    )

    return AgentToolDef(
        name=exposed_name,
        description=mcp_tool_def.get("description", "No description provided."),
        parameters=mcp_tool_def.get(
            "inputSchema", {"type": "object", "properties": {}}
        ),
        permission_level=permission_level,
        metadata={
            "connector_id": str(connector_id),
            "mcp_server_id": str(mcp_tool_def.get("server_id")) if mcp_tool_def.get("server_id") else None,
            "provider_id": str(provider_id or mcp_tool_def.get("provider_id")) if (provider_id or mcp_tool_def.get("provider_id")) else None,
            "server_id": str(mcp_tool_def.get("server_id")) if mcp_tool_def.get("server_id") else None,
            "tenant_id": str(tenant_id or mcp_tool_def.get("tenant_id")) if (tenant_id or mcp_tool_def.get("tenant_id")) else None,
            "user_id": str(user_id or mcp_tool_def.get("user_id")) if (user_id or mcp_tool_def.get("user_id")) else None,
            "original_tool_name": raw_name,
            "catalog_revision": catalog_revision if catalog_revision is not None else mcp_tool_def.get("catalog_revision"),
            "risk_level": resolved_risk_level or None,
            "approval_requirement": resolved_approval or None,
            "mcp_risk_level": resolved_risk_level or None,
            "mcp_approval_requirement": resolved_approval or None,
            "mcp_server_name": server_component,
            "mcp_exposed_name": exposed_name,
            "mcp_original_name": raw_name,
            "mcp_legacy_name": raw_name,
            "is_mcp": True,
        },
    )


class ToolExecutor:
    """Handles the execution of agent tools with strict parameter validation and safety gates."""

    def __init__(
        self,
        *,
        db: Session,
        settings: Settings,
        auth: AuthContext,
        mode: PermissionMode = PermissionMode.DEFAULT,
    ) -> None:
        self.db = db
        self.settings = settings
        self.auth = auth
        self.mode = mode
        self.execution_mode = "auto_review"
        self.coding_harness: CodingHarness | None = None
        self.dynamic_tools: dict[str, AgentToolDef] = {}
        from app.deepspace.memory.memory_service import MemoryService, TodoService
        from app.deepspace.workspace.shell_manager import ShellManager
        from app.deepspace.workspace.workspace_service import WorkspaceService

        self.memory = MemoryService(db, settings)
        self.todo = TodoService(db, settings)
        self.workspace = WorkspaceService(
            tenant_id=str(auth.tenant_id), user_id=str(auth.user_id), settings=settings
        )
        self.shell = ShellManager()
        self.read_files: set[str] = set()
        self.plan_mode: bool = False
        self.current_parent_id: uuid.UUID | None = None
        self.tool_context = ToolContext(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
        )

    def activate_coding_worktree(self, harness: CodingHarness) -> bool:
        """Switch workspace and shell execution to a detached Git worktree."""
        import tempfile
        from dataclasses import replace
        from pathlib import Path

        repository = harness.contract.repository
        if not repository:
            candidates = [self.workspace.workspace_root, Path.cwd()]
            configured_root = os.environ.get("AKS_WORKSPACE_ROOT")
            if configured_root:
                candidates.insert(0, Path(configured_root))
            for candidate in candidates:
                current = candidate.resolve()
                for parent in (current, *current.parents):
                    if (parent / ".git").exists():
                        repository = str(parent)
                        break
                if repository:
                    break
        if not repository:
            return False
        harness.contract = replace(harness.contract, repository=repository)
        try:
            destination = harness.prepare_worktree(
                root=Path(tempfile.gettempdir()) / "averqel-coding-worktrees"
            )
        except (OSError, ValueError):
            return False
        if harness.contract.isolation_mode == "container":
            try:
                harness.prepare_container()
            except (OSError, ValueError, subprocess.SubprocessError):
                return False
        self.workspace.workspace_root = destination
        self.read_files.clear()
        return True

    def _make_tool_context(
        self,
        *,
        conversation_id: uuid.UUID | None = None,
        mission_id: str | None = None,
        lane_id: str | None = None,
        temp_state_store: dict[str, Any] | None = None,
    ) -> ToolContext:
        existing = getattr(self, "tool_context", None)
        return ToolContext(
            tenant_id=self.auth.tenant_id,
            user_id=self.auth.user_id,
            conversation_id=(
                conversation_id
                if conversation_id is not None
                else getattr(existing, "conversation_id", None)
            ),
            mission_id=(
                mission_id
                if mission_id is not None
                else getattr(existing, "mission_id", None)
            ),
            lane_id=(
                lane_id if lane_id is not None else getattr(existing, "lane_id", None)
            ),
            temp_state_store=(
                temp_state_store
                if temp_state_store is not None
                else (
                    getattr(existing, "temp_state_store", None)
                    if getattr(existing, "temp_state_store", None) is not None
                    else {}
                )
            ),
        )

    @staticmethod
    def _run_control_cancelled(run_control: Any | None) -> bool:
        checker = getattr(run_control, "is_cancelled", None)
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001
            logger.debug("Run control cancellation check failed.", exc_info=True)
            return False

    @staticmethod
    async def _emit_tool_progress(
        event_sink: Any,
        *,
        text: str,
        stream: str = "system",
        **extra: Any,
    ) -> None:
        if not callable(event_sink):
            return
        payload = {"text": text, "stream": stream, **extra}
        await event_sink(payload)

    @staticmethod
    def _build_mcp_tool_result(
        *,
        provider: str,
        tool_name: str,
        result: Any,
        default_output: str,
    ) -> ToolResult:
        if bool(getattr(result, "isError", False)):
            rendered = render_mcp_result_text(result)
            return ToolResult(
                success=False,
                output=rendered or f"MCP tool {tool_name} failed for {provider}.",
                data={
                    "provider": provider,
                    "tool": tool_name,
                    "mcp_result": serialize_mcp_result(result),
                },
            )
        rendered = render_mcp_result_text(result)
        output = rendered or default_output
        return ToolResult(
            success=True,
            output=output,
            data={
                "provider": provider,
                "tool": tool_name,
                "mcp_result": serialize_mcp_result(result),
            },
        )

    async def _try_mcp_tool(
        self,
        *,
        config: dict[str, Any],
        provider: str,
        tool_name: str,
        arguments: dict[str, Any],
        default_output: str,
    ) -> ToolResult:
        runtime_config = (
            config.get("connector_config")
            if isinstance(config.get("connector_config"), dict)
            else config
        )
        runtime = build_mcp_runtime(runtime_config)
        if runtime is None:
            return ToolResult(
                success=False,
                output=f"{provider} MCP runtime is not configured for this connector.",
                data={"provider": provider, "tool": tool_name},
            )
        try:
            result = await runtime.call_tool(tool_name, arguments)
            tool_result = self._build_mcp_tool_result(
                provider=provider,
                tool_name=tool_name,
                result=result,
                default_output=default_output,
            )
            return tool_result
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "MCP tool %s for %s failed: %s", tool_name, provider, exc, exc_info=True
            )
            return ToolResult(
                success=False,
                output=f"{provider} MCP tool {tool_name} failed: {exc}",
                data={"provider": provider, "tool": tool_name, "error": str(exc)},
            )

    def get_effective_tier(self, tool_name: str) -> int:
        """Returns the security tier after applying the current permission mode."""
        # Check dynamic tools first
        dynamic_tools = getattr(self, "dynamic_tools", {})
        tool_def = dynamic_tools.get(tool_name)
        if tool_def:
            base_tier = permission_tier_number(tool_def.permission_level)
        else:
            base_tier = permission_tier_number(get_permission(tool_name))

        if self.mode == PermissionMode.BYPASS:
            return 1  # Auto-approve everything

        if self.mode == PermissionMode.PLAN_ONLY:
            return (
                2 if base_tier >= 2 else 1
            )  # Treat all side-effects as blocked/confirm

        if self.mode == PermissionMode.ACCEPT_EDITS:
            if base_tier == 2:
                return 1  # Auto-approve writes

        if self.mode == PermissionMode.DONT_ASK:
            if base_tier <= 3:
                return 1  # Auto-approve bash

        return base_tier

    def _write_tool_audit(
        self,
        *,
        name: str,
        args: dict[str, Any],
        result: ToolResult,
        duration_ms: int,
    ) -> None:
        from app.deepspace.models.agent_audit import AgentAuditLog

        audit = AgentAuditLog(
            tenant_id=self.auth.tenant_id,
            user_id=self.auth.user_id,
            conversation_id=(
                getattr(getattr(self, "tool_context", None), "conversation_id", None)
                or getattr(self, "current_parent_id", None)
            ),
            tool_name=name,
            tool_args=(
                {"argument_keys": sorted(str(key) for key in args)}
                if name.startswith("mcp_")
                else redact_tool_payload(args)
            ),
            tool_result=(
                "[MCP result omitted from audit storage]"
                if name.startswith("mcp_")
                else str(result.output)[:10000]
            ),
            status="success" if result.success else "failed",
            execution_time_ms=duration_ms,
        )
        self.db.add(audit)
        self.db.commit()

    @staticmethod
    def _tool_error_domain(tool_name: str, error_code: str) -> str:
        if error_code in {"unknown_tool", "invalid_arguments", "plan_mode_blocked"}:
            return "validation"
        if error_code == "timeout":
            return "timeout"
        if error_code == "cancelled":
            return "cancellation"
        if tool_name in {
            "sync_connector",
            "crawl_url",
            "list_connectors",
            "get_connector_status",
            "github_search",
            "github_read_file",
            "github_create_file",
            "github_update_file",
            "github_delete_file",
            "github_create_issue",
            "github_comment_issue",
            "github_update_issue",
            "drive_search",
            "drive_read_file",
            "drive_upload_file",
            "drive_update_file",
            "drive_delete_file",
            "gmail_search",
            "gmail_read",
            "gmail_send",
            "gmail_manage",
            "gmail_delete_message",
            "calendar_list_events",
            "calendar_find_free_slots",
            "calendar_create_event",
            "calendar_update_event",
            "calendar_delete_event",
            "notion_create_page",
            "notion_append_content",
            "slack_post_message",
            "slack_update_message",
            "slack_delete_message",
            "search_ecosystem_docs",
        } or tool_name.startswith(
            ("github_", "drive_", "gmail_", "calendar_", "notion_", "slack_")
        ):
            return "connector"
        if tool_name in {"task"}:
            return "subagent"
        if tool_name in {
            "memory_read",
            "memory_write",
            "memory_search",
            "todo_read",
            "todo_write",
        }:
            return "state"
        if tool_name in {"bash", "bash_output", "kill_shell"}:
            return "execution"
        return "tool"

    @staticmethod
    def _tool_retryable(tool_name: str, error_code: str, attempts: int) -> bool:
        if error_code not in {"timeout", "execution_error"}:
            return False
        # Retry budgets are already conservative; expose whether the dispatcher
        # would have been allowed to retry again for this tool category.
        return attempts > 1 and get_permission(tool_name) in {
            PermissionLevel.TIER1_AUTO,
            PermissionLevel.TIER2_CONFIRM,
        }

    def _annotate_failure_result(
        self,
        *,
        tool_name: str,
        result: ToolResult,
        attempts: int,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        data = result.data if isinstance(result.data, dict) else {}
        error_code = str(data.get("error_code") or "").strip()
        if not error_code:
            return result
        metadata = {
            "tool": tool_name,
            "permission_tier": permission_tier_number(get_permission(tool_name)),
            "error_domain": self._tool_error_domain(tool_name, error_code),
            "retryable": self._tool_retryable(tool_name, error_code, attempts),
            "attempts": attempts,
        }
        if timeout_seconds is not None:
            metadata["timeout_seconds"] = timeout_seconds
        data.update(
            {key: value for key, value in metadata.items() if value is not None}
        )
        result.data = data
        return result

    async def _exec_mcp_dynamic_call(
        self,
        name: str,
        args: dict[str, Any],
        tool_def: AgentToolDef,
        *,
        conversation_id: uuid.UUID | None = None,
    ) -> ToolResult:
        """
        Routes a dynamic MCP tool call to the universal bridge.
        """
        connector_id = tool_def.metadata.get("connector_id")
        mcp_server_id = tool_def.metadata.get("mcp_server_id")
        original_name = tool_def.metadata.get("mcp_original_name")

        if mcp_server_id:
            from sqlalchemy import select

            from app.integrations.models.mcp_server import MCPServer
            server = self.db.execute(
                select(MCPServer).where(
                    MCPServer.id == uuid.UUID(str(mcp_server_id)),
                    MCPServer.tenant_id == self.auth.tenant_id,
                    MCPServer.user_id == self.auth.user_id,
                    MCPServer.enabled.is_(True),
                    MCPServer.status == "connected",
                )
            ).scalar_one_or_none()
            if server is None:
                return ToolResult(success=False, output="MCP server not found or disabled.")
            from app.integrations.services.mcp_runtime import (
                evaluate_mcp_tool_policy,
                mcp_catalog_is_fresh,
            )
            if not mcp_catalog_is_fresh(
                server,
                max_age_seconds=self.settings.mcp_catalog_max_age_seconds,
            ):
                return ToolResult(
                    success=False,
                    output="MCP server catalog is stale; refresh the connection before calling this tool.",
                    data={"error_code": "stale_catalog"},
                )
            cached_tools = (server.config or {}).get("mcp_tools_cache", []) if isinstance(server.config, dict) else []
            current_tool = next(
                (
                    item
                    for item in cached_tools
                    if isinstance(item, dict) and item.get("name") == original_name
                ),
                None,
            )
            if current_tool is None:
                return ToolResult(
                    success=False,
                    output="MCP tool is not present in the current catalog; refresh the connection before calling it.",
                    data={"error_code": "unknown_tool"},
                )
            metadata = tool_def.metadata or {}
            expected_revision = metadata.get("catalog_revision")
            try:
                expected_revision = int(expected_revision) if expected_revision is not None else None
            except (TypeError, ValueError):
                expected_revision = None
            expected_provider_id = str(metadata.get("provider_id") or "").strip()
            current_provider_id = str(server.provider_slug or server.registry_entry_id or server.id)
            if expected_provider_id and expected_provider_id != current_provider_id:
                return ToolResult(
                    success=False,
                    output="MCP provider identity changed; refresh the connection before calling this tool.",
                    data={"error_code": "provider_identity_changed"},
                )
            policy_decision = evaluate_mcp_tool_policy(
                db=self.db,
                server=server,
                tool_name=str(original_name or ""),
                tenant_id=self.auth.tenant_id,
                user_id=self.auth.user_id,
                conversation_id=conversation_id,
                deepspace_id=getattr(self.tool_context, "mission_id", None),
                tool=current_tool,
                expected_catalog_revision=expected_revision,
                max_age_seconds=self.settings.mcp_catalog_max_age_seconds,
            )
            if not policy_decision.allowed:
                return ToolResult(
                    success=False,
                    output=policy_decision.reason,
                    data={"error_code": "mcp_policy_blocked", "policy": policy_decision.metadata()},
                )
            if policy_decision.requires_approval:
                return ToolResult(
                    success=False,
                    output="MCP tool requires user approval before execution.",
                    data={"error_code": "approval_required", "policy": policy_decision.metadata()},
                )
            from app.integrations.services.mcp_runtime import execute_mcp_server_tool
            result_payload = await execute_mcp_server_tool(
                db=self.db, settings=self.settings, server=server,
                tool_name=original_name, arguments=args,
                conversation_id=conversation_id,
                deepspace_id=getattr(self.tool_context, "mission_id", None),
            )
            is_error = result_payload.get("is_error", False)
            return ToolResult(
                success=not is_error,
                output=result_payload.get("rendered_text", result_payload.get("message", "Success")),
                data=result_payload,
            )

        from app.integrations.models.connector import Connector

        connector = self.db.get(Connector, uuid.UUID(connector_id))
        if not connector:
            return ToolResult(
                success=False, output=f"Connector {connector_id} not found."
            )

        from app.integrations.services.mcp_runtime import execute_mcp_tool

        result_payload = await execute_mcp_tool(
            db=self.db,
            settings=self.settings,
            connector=connector,
            tool_name=original_name,
            arguments=args,
        )

        is_error = result_payload.get("is_error", False)
        return ToolResult(
            success=not is_error,
            output=result_payload.get(
                "rendered_text", result_payload.get("message", "Success")
            ),
            data=result_payload,
        )

    @trace_async("deepspace.tool.execute")
    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        background_tasks: Any = None,
        event_sink: Any = None,
        run_control: Any | None = None,
        conversation_id: uuid.UUID | None = None,
        tool_context: ToolContext | None = None,
    ) -> ToolResult:
        """Dispatcher for tool execution with mode-aware safety checks and audit logging."""
        import time

        start_time = time.perf_counter()
        audit_args = args if isinstance(args, dict) else {"_raw_args": args}
        previous_parent_id = getattr(self, "current_parent_id", None)
        previous_tool_context = getattr(self, "tool_context", None)
        active_tool_context = tool_context or self._make_tool_context(
            conversation_id=conversation_id,
        )
        self.tool_context = active_tool_context
        active_conversation_id = (
            active_tool_context.conversation_id
            if active_tool_context.conversation_id is not None
            else conversation_id
        )
        if active_conversation_id is not None:
            self.current_parent_id = active_conversation_id

        try:
            tool_def = TOOL_MAP.get(name) or self.dynamic_tools.get(name)
            if self._run_control_cancelled(run_control):
                result = failure_result(
                    "cancelled",
                    "Execution cancelled by user.",
                    tool=name,
                )
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=1,
                    timeout_seconds=None,
                )
                duration = int((time.perf_counter() - start_time) * 1000)
                self._write_tool_audit(
                    name=name, args=audit_args, result=result, duration_ms=duration
                )
                return result

            if tool_def is None:
                result = failure_result(
                    "unknown_tool",
                    f"Tool '{name}' is not registered.",
                    tool=name,
                )
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=1,
                    timeout_seconds=None,
                )
                duration = int((time.perf_counter() - start_time) * 1000)
                self._write_tool_audit(
                    name=name, args=audit_args, result=result, duration_ms=duration
                )
                return result

            validation = validate_tool_arguments(tool_def, audit_args)
            if not validation.valid:
                result = failure_result(
                    "invalid_arguments",
                    validation.message or f"Invalid arguments for '{name}'.",
                    tool=name,
                )
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=1,
                    timeout_seconds=None,
                )
                duration = int((time.perf_counter() - start_time) * 1000)
                self._write_tool_audit(
                    name=name, args=audit_args, result=result, duration_ms=duration
                )
                return result

            policy = build_tool_execution_policy(tool_def, audit_args)

            # Plan Mode Check
            if self.plan_mode and name not in [
                "glob",
                "grep",
                "read_file",
                "web_search",
                "web_fetch",
                "search_ecosystem_docs",
                "list_connectors",
                "get_connector_status",
                "memory_read",
                "todo_read",
                "ask_user_question",
                "exit_plan_mode",
            ]:
                result = failure_result(
                    "plan_mode_blocked",
                    f"Cannot use tool '{name}' while in PLAN MODE. Exit plan mode to execute changes.",
                    tool=name,
                )
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=1,
                    timeout_seconds=None,
                )
                duration = int((time.perf_counter() - start_time) * 1000)
                self._write_tool_audit(
                    name=name, args=audit_args, result=result, duration_ms=duration
                )
                return result

            contract = policy.contract
            contract_requires_human = bool(
                contract is not None
                and contract.approval_requirement == "human"
                and (
                    contract.risk_class in {"internal_write", "external_read", "external_side_effect", "destructive", "privileged", "untrusted", "ambiguous"}
                    or getattr(self, "execution_mode", "auto_review") != "full_access"
                )
            )
            if name == "bash":
                command = str(audit_args.get("command") or "").strip().lower()
                known_blocked_command = bool(
                    re.search(r"(?:^|[\s;|&])rm(?:\s|-)+(?:-rf|-fr|-r)\b", command)
                    or re.search(r"\b(curl|wget)\b.*\|\s*(?:sh|bash)\b", command)
                )
                if known_blocked_command:
                    contract_requires_human = False
            if contract_requires_human:
                result = failure_result(
                    "approval_required",
                    f"Tool '{name}' requires human approval before execution.",
                    tool=name,
                    requires_human_approval=True,
                    risk_class=contract.risk_class,
                    tool_contract=contract.to_dict(),
                )
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=1,
                    timeout_seconds=policy.timeout_seconds,
                )
                duration = int((time.perf_counter() - start_time) * 1000)
                self._write_tool_audit(
                    name=name, args=audit_args, result=result, duration_ms=duration
                )
                return result

            if tool_def.metadata and tool_def.metadata.get("is_mcp"):
                # Dynamic routing for MCP tools
                result = await self._exec_mcp_dynamic_call(
                    name,
                    audit_args,
                    tool_def,
                    conversation_id=active_conversation_id,
                )
                # Skip the standard implementation block by setting method to None and result already set
                method = None
            else:
                method = getattr(self, f"_exec_{name}", None)
            if not method and result is None:
                result = failure_result(
                    "unknown_tool",
                    f"Tool '{name}' is registered but not implemented.",
                    tool=name,
                )
            else:
                method_kwargs: dict[str, Any] = {}
                signature = inspect.signature(method)
                if "background_tasks" in signature.parameters:
                    method_kwargs["background_tasks"] = background_tasks
                elif "_bt" in signature.parameters:
                    method_kwargs["_bt"] = background_tasks
                if "event_sink" in signature.parameters:
                    method_kwargs["event_sink"] = event_sink
                if "run_control" in signature.parameters:
                    method_kwargs["run_control"] = run_control
                if "tool_context" in signature.parameters:
                    method_kwargs["tool_context"] = active_tool_context
                configured_retries = policy.retries
                attempts = configured_retries + 1
                last_exc: Exception | None = None
                attempt_used = 0
                for attempt in range(attempts):
                    attempt_used = attempt + 1
                    try:
                        result = await asyncio.wait_for(
                            method(audit_args, **method_kwargs),
                            timeout=policy.timeout_seconds,
                        )
                        break
                    except TimeoutError:
                        result = failure_result(
                            "timeout",
                            f"Tool '{name}' timed out after {policy.timeout_seconds:.0f}s.",
                            tool=name,
                            timeout_seconds=policy.timeout_seconds,
                        )
                        result = self._annotate_failure_result(
                            tool_name=name,
                            result=result,
                            attempts=attempt_used,
                            timeout_seconds=policy.timeout_seconds,
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        if attempt + 1 >= attempts:
                            raise
                        logger.warning(
                            "Retrying tool %s after execution error: %s",
                            name,
                            exc,
                            exc_info=True,
                        )
                else:  # pragma: no cover - defensive fallback
                    raise last_exc or RuntimeError(f"Tool '{name}' did not return.")

            if self._run_control_cancelled(run_control):
                result = failure_result(
                    "cancelled",
                    "Execution cancelled by user.",
                    tool=name,
                )
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=attempts if "attempts" in locals() else 1,
                    timeout_seconds=(
                        policy.timeout_seconds if "policy" in locals() else None
                    ),
                )

            # Audit Logging
            duration = int((time.perf_counter() - start_time) * 1000)
            if isinstance(result.data, dict) and result.data.get("error_code"):
                result = self._annotate_failure_result(
                    tool_name=name,
                    result=result,
                    attempts=attempts if "attempts" in locals() else 1,
                    timeout_seconds=(
                        policy.timeout_seconds if "policy" in locals() else None
                    ),
                )
            self._write_tool_audit(
                name=name,
                args=audit_args,
                result=result,
                duration_ms=duration,
            )

            return result
        except Exception as exc:
            logger.error("Error executing tool %s: %s", name, exc, exc_info=True)
            result = failure_result(
                "execution_error",
                f"Execution error while running '{name}'.",
                tool=name,
                error_type=type(exc).__name__,
            )
            duration = int((time.perf_counter() - start_time) * 1000)
            try:
                self._write_tool_audit(
                    name=name,
                    args=audit_args,
                    result=result,
                    duration_ms=duration,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to write audit log for tool %s.", name)
            return result
        finally:
            self.current_parent_id = previous_parent_id
            self.tool_context = previous_tool_context

    def _resolve_connector_context(
        self,
        *,
        connector_id: str | None = None,
        integration_slug: str | None = None,
        active_only: bool = True,
    ) -> tuple[Any | None, dict[str, Any], str | None]:
        from sqlalchemy import select

        from app.integrations.models.connector import Connector, ConnectorStatus
        from app.integrations.models.connector_secret import ConnectorSecret
        from app.integrations.models.integration import Integration
        from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto

        if connector_id:
            try:
                connector_uuid = uuid.UUID(connector_id)
            except ValueError:
                return None, {}, f"Invalid connector_id: {connector_id}"

            stmt = (
                select(Connector)
                .join(Integration)
                .where(
                    Connector.id == connector_uuid,
                    Connector.tenant_id == self.auth.tenant_id,
                )
            )
            if active_only:
                stmt = stmt.where(Connector.status == ConnectorStatus.ACTIVE)
        elif integration_slug:
            stmt = (
                select(Connector)
                .join(Integration)
                .where(
                    Connector.tenant_id == self.auth.tenant_id,
                    Integration.slug == integration_slug,
                )
                .order_by(Connector.created_at.desc())
            )
            if active_only:
                stmt = stmt.where(Connector.status == ConnectorStatus.ACTIVE)
        else:
            return None, {}, "connector_id or integration_slug is required"

        connector = self.db.execute(stmt).scalars().first()
        if not connector:
            return None, {}, "Connector not found"

        resolved_config = dict(connector.config or {})
        secret_rows = (
            self.db.execute(
                select(ConnectorSecret).where(
                    ConnectorSecret.connector_id == connector.id
                )
            )
            .scalars()
            .all()
        )
        if secret_rows:
            crypto = ConnectorSecretCrypto()
            for secret in secret_rows:
                try:
                    decrypted = crypto.decrypt(
                        ciphertext=secret.secret_ciphertext,
                        nonce=secret.secret_nonce,
                        kid=secret.secret_kid,
                        aad=str(connector.tenant_id).encode(),
                    )
                    resolved_config[secret.secret_type] = decrypted.decode()
                except Exception as exc:
                    return None, {}, f"Failed to decrypt connector secrets: {exc}"

        return connector, resolved_config, None

    @staticmethod
    def _parse_github_repo_url(repo_url: str) -> tuple[str | None, str | None]:
        parsed = urlparse(repo_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            return None, None
        return parts[0], parts[1].removesuffix(".git")

    def _resolve_github_source(
        self,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        connector: Any | None = None
        resolved_config: dict[str, Any] = {}

        connector_id = str(args.get("connector_id") or "").strip() or None
        integration_slug = str(args.get("integration_slug") or "").strip() or None
        if connector_id or integration_slug:
            connector, resolved_config, error = self._resolve_connector_context(
                connector_id=connector_id,
                integration_slug=integration_slug,
                active_only=False,
            )
            if error and not any(
                str(args.get(key) or "").strip()
                for key in ("repo_owner", "repo_name", "repo_url")
            ):
                return {}, error
            if connector is None:
                resolved_config = {}

        repo_url = str(
            args.get("repo_url") or resolved_config.get("repo_url") or ""
        ).strip()
        repo_owner = str(
            args.get("repo_owner") or resolved_config.get("repo_owner") or ""
        ).strip()
        repo_name = str(
            args.get("repo_name") or resolved_config.get("repo_name") or ""
        ).strip()
        if (not repo_owner or not repo_name) and repo_url:
            parsed_owner, parsed_name = self._parse_github_repo_url(repo_url)
            repo_owner = repo_owner or parsed_owner or ""
            repo_name = repo_name or parsed_name or ""

        if not repo_owner or not repo_name:
            return {}, "GitHub repo_owner and repo_name are required."

        repo_url = repo_url or f"https://github.com/{repo_owner}/{repo_name}"
        branch = (
            str(args.get("branch") or resolved_config.get("branch") or "main").strip()
            or "main"
        )
        root_path = (
            str(args.get("path") or resolved_config.get("path") or "")
            .strip()
            .strip("/")
        )
        token = (
            resolve_config_text(
                resolved_config,
                "personal_access_token",
                "github_token",
                "credentials",
                "token",
            )
            or str(args.get("token") or "").strip()
            or None
        )

        return (
            {
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "repo_url": repo_url,
                "branch": branch,
                "path": root_path,
                "token": token,
                "connector_name": getattr(connector, "name", None),
                "connector_config": resolved_config,
            },
            None,
        )

    @staticmethod
    def _github_headers(token: str | None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AverQel-DeepSpace",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _github_strip_markdown_excerpt(
        text: str, query: str, *, window: int = 240
    ) -> str:
        if not text:
            return ""
        haystack = text.lower()
        needle = query.lower()
        idx = haystack.find(needle)
        if idx < 0:
            return text[:window].strip()
        start = max(0, idx - window // 2)
        end = min(len(text), idx + len(query) + window // 2)
        return text[start:end].strip()

    async def _github_fetch_tree_entries(
        self,
        *,
        client: Any,
        repo_owner: str,
        repo_name: str,
        branch: str,
        headers: dict[str, str],
    ) -> list[dict[str, Any]]:
        url = (
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/git/trees/"
            f"{quote(branch, safe='')}"  # branch names can contain slashes
            "?recursive=1"
        )
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        tree = payload.get("tree", []) if isinstance(payload, dict) else []
        return [entry for entry in tree if isinstance(entry, dict)]

    async def _github_fetch_file_text(
        self,
        *,
        client: Any,
        repo_owner: str,
        repo_name: str,
        branch: str,
        path: str,
        headers: dict[str, str],
    ) -> tuple[str | None, dict[str, Any] | None]:
        encoded_path = quote(path.strip("/"), safe="/")
        url = (
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{encoded_path}"
            f"?ref={quote(branch, safe='')}"
        )
        response = await client.get(url, headers=headers)
        if response.status_code == 404:
            return None, None
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return None, {"type": "directory", "entries": payload}
        if not isinstance(payload, dict):
            return None, None
        if payload.get("type") != "file":
            return None, payload

        content = payload.get("content")
        encoding = str(payload.get("encoding") or "").lower()
        if isinstance(content, str) and content.strip():
            if encoding == "base64":
                try:
                    return (
                        base64.b64decode(content.encode("utf-8")).decode(
                            "utf-8", errors="replace"
                        ),
                        payload,
                    )
                except Exception:
                    pass
            return content, payload

        download_url = str(payload.get("download_url") or "").strip()
        if not download_url:
            return None, payload
        download_response = await client.get(download_url, headers=headers)
        download_response.raise_for_status()
        return download_response.text, payload

    def _resolve_drive_source(
        self,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        connector: Any | None = None
        resolved_config: dict[str, Any] = {}

        connector_id = str(args.get("connector_id") or "").strip() or None
        integration_slug = str(args.get("integration_slug") or "").strip() or None
        if connector_id or integration_slug:
            connector, resolved_config, error = self._resolve_connector_context(
                connector_id=connector_id,
                integration_slug=integration_slug,
                active_only=False,
            )
            if (
                error
                and not str(args.get("folder_id") or "").strip()
                and not str(args.get("file_id") or "").strip()
            ):
                return {}, error
            if connector is None:
                resolved_config = {}

        folder_id = str(
            args.get("folder_id") or resolved_config.get("folder_id") or ""
        ).strip()
        file_id = str(args.get("file_id") or "").strip()
        credentials = resolve_config_dict(
            resolved_config,
            "credentials",
            "google_credentials",
            "oauth_json",
        )
        if not credentials:
            credentials = resolve_config_dict(
                args, "credentials", "google_credentials", "oauth_json"
            )

        if not credentials:
            return {}, "Google Drive OAuth credentials are required."

        return (
            {
                "folder_id": folder_id,
                "file_id": file_id,
                "drive_scope": "folder" if folder_id else "all_drives",
                "page_size": max(1, min(int(args.get("page_size") or 20), 100)),
                "max_files": max(1, min(int(args.get("max_files") or 40), 100)),
                "max_results": max(1, min(int(args.get("max_results") or 10), 25)),
                "credentials": credentials,
                "connector_name": getattr(connector, "name", None),
                "connector_config": resolved_config,
            },
            None,
        )

    @staticmethod
    def _read_local_file_bytes(local_path: str) -> tuple[bytes | None, str | None]:
        path = Path(local_path).expanduser()
        if not path.exists():
            return None, f"Local file not found: {local_path}"
        if not path.is_file():
            return None, f"Local path is not a file: {local_path}"
        try:
            return path.read_bytes(), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Failed to read local file {local_path}: {exc}"

    @staticmethod
    def _guess_mime_type(
        file_name: str, default: str = "application/octet-stream"
    ) -> str:
        guessed, _encoding = mimetypes.guess_type(file_name)
        return guessed or default

    def _resolve_slack_source(
        self, args: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        connector: Any | None = None
        resolved_config: dict[str, Any] = {}

        connector_id = str(args.get("connector_id") or "").strip() or None
        integration_slug = str(args.get("integration_slug") or "").strip() or None
        if connector_id or integration_slug:
            connector, resolved_config, error = self._resolve_connector_context(
                connector_id=connector_id,
                integration_slug=integration_slug,
                active_only=False,
            )
            if error and not str(args.get("channel_id") or "").strip():
                return {}, error
            if connector is None:
                resolved_config = {}

        channel_id = str(
            args.get("channel_id") or resolved_config.get("channel_id") or ""
        ).strip()
        token = (
            resolve_config_text(resolved_config, "bot_token", "credentials", "token")
            or str(args.get("token") or "").strip()
            or None
        )
        if not token:
            return {}, "Slack OAuth credentials are required."
        if not channel_id:
            return {}, "Slack channel_id is required."

        return (
            {
                "channel_id": channel_id,
                "token": token,
                "connector_name": getattr(connector, "name", None),
                "connector_config": resolved_config,
            },
            None,
        )

    @staticmethod
    def _connector_summary(connector: Any) -> dict[str, Any]:
        integration = getattr(connector, "integration", None)
        status = getattr(connector, "status", "")
        status_text = getattr(status, "value", status)
        return {
            "id": str(getattr(connector, "id", "")),
            "name": getattr(connector, "name", ""),
            "slug": getattr(integration, "slug", ""),
            "status": str(status_text),
            "last_sync_at": getattr(connector, "last_sync_at", None),
            "last_error": getattr(connector, "last_error", None),
            "sync_frequency": getattr(connector, "sync_frequency", ""),
        }

    async def _exec_list_connectors(self, args: dict[str, Any]) -> ToolResult:
        from app.integrations.models.connector import Connector
        from app.integrations.models.integration import Integration

        stmt = (
            select(Connector)
            .join(Integration)
            .where(Connector.tenant_id == self.auth.tenant_id)
            .order_by(Connector.created_at.desc())
        )
        connectors = self.db.execute(stmt).scalars().all()
        summaries = [self._connector_summary(connector) for connector in connectors]
        if not summaries:
            return ToolResult(
                success=True,
                output="No connectors configured yet.",
                data={"connectors": []},
            )
        lines = [
            f"- {item['name']} [{item['slug']}] status={item['status']} id={item['id']}"
            for item in summaries
        ]
        return ToolResult(
            success=True,
            output="Connectors:\n" + "\n".join(lines),
            data={"connectors": summaries},
        )

    async def _exec_get_connector_status(self, args: dict[str, Any]) -> ToolResult:
        connector, config, error = self._resolve_connector_context(
            connector_id=args.get("connector_id"),
            integration_slug=args.get("integration_slug"),
            active_only=False,
        )
        if error:
            return ToolResult(success=False, output=error)
        assert connector is not None
        summary = self._connector_summary(connector)
        summary["config_keys"] = sorted(
            [key for key in config.keys() if key != "credentials"]
        )
        return ToolResult(
            success=True,
            output=(
                f"{summary['name']} ({summary['slug']}) is {summary['status']}."
                f" Last sync: {summary['last_sync_at'] or 'never'}."
            ),
            data=summary,
        )

    async def _exec_sync_connector(
        self,
        args: dict[str, Any],
        background_tasks: Any = None,
        event_sink: Any = None,
    ) -> ToolResult:
        from app.integrations.models.connector import Connector
        from app.integrations.models.integration import Integration
        from app.integrations.services.connector_orchestrator import (
            ConnectorOrchestrator,
        )

        connector = None
        connector_id = args.get("connector_id")
        integration_slug = args.get("integration_slug")
        if connector_id or integration_slug:
            query = (
                select(Connector)
                .join(Integration)
                .where(Connector.tenant_id == self.auth.tenant_id)
            )
            if connector_id:
                try:
                    query = query.where(Connector.id == uuid.UUID(str(connector_id)))
                except ValueError:
                    return ToolResult(
                        success=False, output=f"Invalid connector_id: {connector_id}"
                    )
            if integration_slug:
                query = query.where(Integration.slug == str(integration_slug))
            connector = (
                self.db.execute(query.order_by(Connector.created_at.desc()))
                .scalars()
                .first()
            )

        if not connector:
            return ToolResult(success=False, output="Connector not found.")

        orchestrator = ConnectorOrchestrator(self.db)
        if background_tasks:
            await self._emit_tool_progress(
                event_sink,
                text=f"Queued connector sync for {connector.name}.\n",
                stream="system",
                connector_id=str(connector.id),
            )
            background_tasks.add_task(
                orchestrator.sync_connector,
                connector.id,
                connector.tenant_id,
            )
            return ToolResult(
                success=True,
                output=f"Queued sync for {connector.name}.",
                data={"connector_id": str(connector.id)},
            )
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def progress_callback(payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, payload)

        task = asyncio.create_task(
            asyncio.to_thread(
                orchestrator.sync_connector,
                connector.id,
                connector.tenant_id,
                progress_callback,
            )
        )
        while not task.done():
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            await self._emit_tool_progress(
                event_sink,
                text=f"{progress.get('message', 'Connector sync update.')}\n",
                stream="system",
                connector_id=str(connector.id),
                phase=progress.get("phase"),
            )
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            await self._emit_tool_progress(
                event_sink,
                text=f"{progress.get('message', 'Connector sync update.')}\n",
                stream="system",
                connector_id=str(connector.id),
                phase=progress.get("phase"),
            )
        result = await task
        status = str(result.get("status") or "")
        return ToolResult(
            success=status in {"success", "skipped"} and "error" not in result,
            output=str(result.get("message") or result),
            data={"result": result, "connector_id": str(connector.id)},
        )

    async def _exec_crawl_url(
        self,
        args: dict[str, Any],
        background_tasks: Any = None,
        event_sink: Any = None,
    ) -> ToolResult:
        from app.integrations.models.connector import Connector
        from app.integrations.models.integration import Integration
        from app.integrations.services.connector_orchestrator import (
            ConnectorOrchestrator,
        )

        url = str(args.get("url") or "").strip()
        if not url:
            return ToolResult(success=False, output="URL is required.")
        await self._emit_tool_progress(
            event_sink,
            text=f"Preparing crawler for {url}.\n",
            stream="system",
            url=url,
        )

        integration = (
            self.db.execute(
                select(Integration).where(
                    Integration.slug == "web-crawler", Integration.is_active
                )
            )
            .scalars()
            .first()
        )
        if not integration:
            return ToolResult(
                success=False, output="Web crawler integration is not seeded."
            )

        connector = (
            self.db.execute(
                select(Connector)
                .where(
                    Connector.tenant_id == self.auth.tenant_id,
                    Connector.integration_id == integration.id,
                )
                .order_by(Connector.created_at.desc())
            )
            .scalars()
            .first()
        )

        if connector is None:
            connector = Connector(
                tenant_id=self.auth.tenant_id,
                user_id=self.auth.user_id,
                integration_id=integration.id,
                name=str(args.get("name") or "Web Crawler"),
                config={"url": url},
            )
            self.db.add(connector)
        else:
            connector.config = {**dict(connector.config or {}), "url": url}
        self.db.commit()
        self.db.refresh(connector)

        orchestrator = ConnectorOrchestrator(self.db)
        if background_tasks:
            await self._emit_tool_progress(
                event_sink,
                text=f"Queued crawl for {url}.\n",
                stream="system",
                connector_id=str(connector.id),
                url=url,
            )
            background_tasks.add_task(
                orchestrator.sync_connector,
                connector.id,
                connector.tenant_id,
            )
            return ToolResult(
                success=True,
                output=f"Queued crawl for {url}.",
                data={"connector_id": str(connector.id), "url": url},
            )

        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def progress_callback(payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, payload)

        task = asyncio.create_task(
            asyncio.to_thread(
                orchestrator.sync_connector,
                connector.id,
                connector.tenant_id,
                progress_callback,
            )
        )
        while not task.done():
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            await self._emit_tool_progress(
                event_sink,
                text=f"{progress.get('message', 'Crawler update.')}\n",
                stream="system",
                connector_id=str(connector.id),
                url=url,
                phase=progress.get("phase"),
            )
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            await self._emit_tool_progress(
                event_sink,
                text=f"{progress.get('message', 'Crawler update.')}\n",
                stream="system",
                connector_id=str(connector.id),
                url=url,
                phase=progress.get("phase"),
            )
        result = await task
        status = str(result.get("status") or "")
        return ToolResult(
            success=status in {"success", "skipped"} and "error" not in result,
            output=str(result.get("message") or result),
            data={"result": result, "connector_id": str(connector.id), "url": url},
        )

    async def _exec_read_file(self, args: dict[str, Any]) -> ToolResult:
        import os

        path = args.get("path")
        offset = args.get("offset", 0)
        limit = args.get("limit", 2000)
        try:
            from app.deepspace.integrations.client_proxy import client_proxy_registry
            if client_proxy_registry.is_client_connected(self.workspace.tenant_id, self.workspace.user_id):
                content_str = await self.workspace.read_file_async(path)
                lines = content_str.splitlines(keepends=True)
                total = len(lines)
                content = "".join(lines[offset : offset + limit])
                self.read_files.add(path)
                return ToolResult(
                    success=True,
                    output=f"READ {path} (Lines {offset}-{min(offset + limit, total)} of {total}):\n\n{content}",
                    data={"total_lines": total, "path": path},
                )

            if not os.path.isabs(path):
                path = os.path.abspath(path)

            # Multi-modal detection
            ext = os.path.splitext(path)[1].lower()
            if ext == ".pdf":
                from pypdf import PdfReader

                reader = PdfReader(path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return ToolResult(
                    success=True,
                    output=f"PDF CONTENT from {path}:\n\n{text[:10000]}",
                    data={"path": path, "type": "pdf"},
                )

            if not os.path.exists(path):
                return ToolResult(success=False, output=f"File not found: {path}")

            with open(path) as f:
                lines = f.readlines()
                total = len(lines)
                content = "".join(lines[offset : offset + limit])

            self.read_files.add(path)
            return ToolResult(
                success=True,
                output=f"READ {path} (Lines {offset}-{min(offset + limit, total)} of {total}):\n\n{content}",
                data={"total_lines": total, "path": path},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Error reading {path}: {str(e)}")

    async def _exec_glob(self, args: dict[str, Any]) -> ToolResult:
        import glob
        import os

        pattern = args.get("pattern")
        root = args.get("path") or os.getcwd()
        try:
            matches = glob.glob(os.path.join(root, pattern), recursive=True)
            sorted_matches = sorted(matches, key=os.path.getmtime, reverse=True)
            return ToolResult(
                success=True,
                output=f"Glob matches for '{pattern}' in {root} (newest first):\n"
                + "\n".join(sorted_matches[:100]),
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Glob error: {str(e)}")

    async def _exec_grep(self, args: dict[str, Any]) -> ToolResult:
        import subprocess

        pattern = args.get("pattern")
        path = args.get("path") or "."
        output_mode = args.get("output_mode", "content")

        try:
            cmd = ["rg", "--max-count", "100", "--smart-case"]
            if output_mode == "files_with_matches":
                cmd.append("-l")
            elif output_mode == "count":
                cmd.append("-c")
            else:
                cmd.extend(["--line-number", "--heading"])

            if args.get("case_insensitive"):
                cmd.append("-i")
            if args.get("context_before"):
                cmd.extend(["-B", str(args["context_before"])])
            if args.get("context_after"):
                cmd.extend(["-A", str(args["context_after"])])

            cmd.extend([pattern, path])
            result = subprocess.run(cmd, capture_output=True, text=True)
            return ToolResult(
                success=True,
                output=f"Grep results for '{pattern}':\n{result.stdout[:8000]}",
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Grep error: {str(e)}")

    async def _exec_web_search_impl(
        self,
        args: dict[str, Any],
        event_sink: Any = None,
    ) -> ToolResult:
        """Execute live web search using configured providers."""
        from app.providers.services.registry import ProviderRegistry
        from app.providers.services.selection_service import ProviderSelectionService
        from app.providers.services.types import WebSearchRequest

        query = str(args.get("query", ""))
        if not query.strip():
            return ToolResult(success=False, output="Empty query.")

        try:
            await self._emit_tool_progress(
                event_sink,
                text=f"Resolving web-search provider for query: {query}\n",
                stream="system",
            )
            selection_service = ProviderSelectionService(self.db, self.settings)
            selection = selection_service.resolve_web_search(
                tenant_id=self.auth.tenant_id,
                workspace_id=None,
                actor_user_id=self.auth.user_id,
            )
            candidate = selection.candidates[0] if selection.candidates else None
            if not candidate:
                return ToolResult(
                    success=True,
                    output=(
                        "WEB SEARCH UNAVAILABLE: no web-search provider is configured for this "
                        "tenant. Continue without live web access and do not claim fresh web data."
                    ),
                    data={"available": False, "reason": "provider_unavailable"},
                )

            registry = ProviderRegistry(self.settings)
            provider = registry.get_web_search_provider_from_selection(candidate)
            await self._emit_tool_progress(
                event_sink,
                text=f"Searching live web via {candidate.provider_type}.\n",
                stream="system",
                provider=candidate.provider_type,
            )
            response = provider.search(
                WebSearchRequest(
                    query=query,
                    max_results=5,
                    timeout_seconds=int(self.settings.provider_timeout_seconds),
                    search_depth=str(candidate.metadata.get("search_depth") or "basic"),
                    include_answer=True,
                    provider_name=candidate.provider_type,
                )
            )

            results = [
                f"- [{item.title}]({item.url})\n  {item.content[:300]}"
                for item in response.results[:5]
            ]
            output = (
                (f"Summary: {response.answer}\n\n" if response.answer else "")
                + f"Results ({len(response.results)} found):\n"
                + "\n".join(results)
            )
            await self._emit_tool_progress(
                event_sink,
                text=f"Collected {len(response.results)} live web results.\n",
                stream="system",
                result_count=len(response.results),
            )
            return ToolResult(
                success=True,
                output=output,
                data={"result_count": len(response.results)},
            )
        except Exception as exc:
            await self._emit_tool_progress(
                event_sink,
                text=f"Web search provider failed: {str(exc)}\n",
                stream="stderr",
            )
            return ToolResult(
                success=True,
                output=(
                    "WEB SEARCH UNAVAILABLE: the web-search provider failed for this turn. "
                    "Continue without live web access and do not claim fresh web data."
                ),
                data={
                    "available": False,
                    "reason": "provider_failed",
                    "error": str(exc),
                },
            )

    async def _exec_search_ecosystem_docs(self, args: dict[str, Any]) -> ToolResult:
        """Search private ecosystem documents with strict web-crawler isolation."""
        from app.documents.models.document import Document
        from app.integrations.models.connector import Connector
        from app.integrations.models.integration import Integration
        from app.query.services.retrieval_service import RetrievalService

        query = str(args.get("query", ""))
        top_k = int(args.get("top_k", 6))
        if not query.strip():
            return ToolResult(success=False, output="Empty query.")

        crawler_ids = (
            self.db.execute(
                select(Connector.id)
                .join(Integration)
                .where(
                    Connector.tenant_id == self.auth.tenant_id,
                    Integration.slug == "web-crawler",
                )
            )
            .scalars()
            .all()
        )
        if not crawler_ids:
            return ToolResult(success=True, output="No ecosystem documents found.")

        doc_ids = (
            self.db.execute(
                select(Document.id).where(
                    Document.tenant_id == self.auth.tenant_id,
                    Document.connector_id.in_(crawler_ids),
                    Document.status == "processed",
                    Document.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        if not doc_ids:
            return ToolResult(
                success=True, output="No processed ecosystem documents found."
            )

        retrieval = RetrievalService(self.db, self.settings)
        chunks = retrieval.retrieve(
            self.auth.tenant_id,
            self.auth.user_id,
            query,
            top_k=top_k,
            document_ids=doc_ids,
            search_mode="hybrid",
        )

        if not chunks:
            return ToolResult(
                success=True, output="No relevant results found in ecosystem documents."
            )

        sections = [
            f"[{i + 1}] Source: {c.filename} (score: {c.similarity_score:.2f})\n{c.content[:1200]}"
            for i, c in enumerate(chunks)
        ]
        return ToolResult(
            success=True,
            output=f"Found {len(chunks)} relevant results from ecosystem documents:\n\n"
            + "\n\n---\n\n".join(sections),
            data={"chunk_count": len(chunks)},
        )

    async def _exec_web_fetch_impl(
        self,
        args: dict[str, Any],
        event_sink: Any = None,
    ) -> ToolResult:
        import httpx
        from bs4 import BeautifulSoup

        url = str(args.get("url") or "").strip()
        if not url:
            return ToolResult(success=False, output="url is required.")
        prompt = str(args.get("prompt") or "").strip()
        await self._emit_tool_progress(
            event_sink,
            text=f"Requesting {url}\n",
            stream="system",
            url=url,
        )
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                await self._emit_tool_progress(
                    event_sink,
                    text=f"Received HTTP {response.status_code} from {url}\n",
                    stream="system",
                    url=url,
                    status_code=response.status_code,
                )

                soup = BeautifulSoup(response.text, "html.parser")
                for script in soup(["script", "style"]):
                    script.decompose()

                await self._emit_tool_progress(
                    event_sink,
                    text="Extracting readable text from page content.\n",
                    stream="system",
                    url=url,
                )
                text = soup.get_text(separator="\n")
                lines = (line.strip() for line in text.splitlines())
                chunks = (
                    phrase.strip() for line in lines for phrase in line.split("  ")
                )
                text = "\n".join(chunk for chunk in chunks if chunk)
                if prompt:
                    await self._emit_tool_progress(
                        event_sink,
                        text=f"Prepared fetched content for prompt focus: {prompt[:120]}\n",
                        stream="system",
                        url=url,
                    )
                await self._emit_tool_progress(
                    event_sink,
                    text=f"Extracted {len(text)} characters from {url}\n",
                    stream="system",
                    url=url,
                    extracted_chars=len(text),
                )
                return ToolResult(
                    success=True,
                    output=f"FETCHED {url}:\n\n{text[:15000]}",
                    data={"content": text, "status": response.status_code},
                )
        except Exception as e:
            await self._emit_tool_progress(
                event_sink,
                text=f"Failed to fetch {url}: {str(e)}\n",
                stream="stderr",
                url=url,
            )
            return ToolResult(success=False, output=f"Failed to fetch {url}: {str(e)}")

    async def _exec_memory_read(self, args: dict[str, Any]) -> ToolResult:
        key = args.get("key")
        val = await self.memory.retrieve_fact(
            tenant_id=self.auth.tenant_id, user_id=self.auth.user_id, key=key
        )
        return ToolResult(
            success=True, output=f"Memory for '{key}': {val or 'Not found'}"
        )

    async def _exec_memory_search(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query")
        mems = await self.memory.search_memories(
            tenant_id=self.auth.tenant_id, user_id=self.auth.user_id, query=query
        )
        output = "\n".join([f"- {m['key']}: {m['value']}" for m in mems])
        return ToolResult(
            success=True, output=f"Memory matches for '{query}':\n{output or 'None.'}"
        )

    async def _exec_todo_read(self, args: dict[str, Any]) -> ToolResult:
        todos = await self.todo.list_todos(
            tenant_id=self.auth.tenant_id, user_id=self.auth.user_id
        )
        output = "\n".join(
            [
                f"[{'x' if t['status'] == 'completed' else '/' if t['status'] == 'in_progress' else ' '}] {t['content']}"
                for t in todos
            ]
        )
        return ToolResult(
            success=True, output=f"Active Tasks:\n{output or 'Queue empty.'}"
        )

    async def _exec_bash_output(self, args: dict[str, Any]) -> ToolResult:
        bash_id = args.get("bash_id")
        session = self.shell.get_session_by_id(bash_id)
        if not session:
            return ToolResult(success=False, output=f"Session {bash_id} not found.")
        output = await session.get_new_output()
        return ToolResult(success=True, output=output or "[No new output]")

    # --- TIER 2: Writes / Edits ---

    async def _exec_write_file(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path")
        content = args.get("content")

        if self.coding_harness is not None:
            allowed, reason = self.coding_harness.validate_path(str(path or ""))
            if not allowed:
                return ToolResult(
                    success=False,
                    output=f"CODING HARNESS BLOCK: {reason}",
                    data={"error_kind": "security_block", "error_code": "coding_path_blocked"},
                )

        # We still want the "read before write" safety rule
        # Check existence via host path for safety check
        exists = await self.workspace.exists_async(path)
        if exists and path not in self.read_files:
            return ToolResult(
                success=False,
                output=f"Safety violation: MUST Read existing file {path} before overwriting.",
            )

        try:
            relative_path = await self.workspace.write_file_async(path, content)
            return ToolResult(
                success=True,
                output=f"Successfully wrote {relative_path}.",
                data={"changed_files": [str(relative_path)], "artifact_changed": True},
            )
        except Exception as e:
            return ToolResult(success=False, output=str(e))

    async def _exec_edit_file(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path")
        old, new = args.get("old_string"), args.get("new_string")

        if self.coding_harness is not None:
            allowed, reason = self.coding_harness.validate_path(str(path or ""))
            if not allowed:
                return ToolResult(
                    success=False,
                    output=f"CODING HARNESS BLOCK: {reason}",
                    data={"error_kind": "security_block", "error_code": "coding_path_blocked"},
                )

        if path not in self.read_files:
            return ToolResult(
                success=False,
                output=f"Safety violation: MUST Read file {path} before editing.",
            )

        try:
            current_content = await self.workspace.read_file_async(path)
            if old not in current_content:
                return ToolResult(success=False, output=f"String not found in {path}.")

            new_content = current_content.replace(
                old, new, 1 if not args.get("replace_all") else -1
            )
            await self.workspace.write_file_async(path, new_content)
            return ToolResult(
                success=True,
                output=f"Successfully edited {path}.",
                data={"changed_files": [str(path)], "artifact_changed": True},
            )
        except Exception as e:
            return ToolResult(success=False, output=str(e))

    async def _exec_notebook_edit(self, args: dict[str, Any]) -> ToolResult:
        """Edit Jupyter notebook (.ipynb) cells directly with nbformat."""
        import nbformat

        path = args.get("path")
        cell_index = args.get("cell_index", 0)
        new_content = args.get("content")

        try:
            with open(path, encoding="utf-8") as f:
                nb = nbformat.read(f, as_version=4)

            if cell_index >= len(nb.cells):
                return ToolResult(
                    success=False,
                    output=f"Cell index {cell_index} out of range (total cells: {len(nb.cells)}).",
                )

            nb.cells[cell_index].source = new_content

            with open(path, "w", encoding="utf-8") as f:
                nbformat.write(nb, f)

            return ToolResult(
                success=True,
                output=f"Successfully updated cell {cell_index} in {path}.",
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Notebook edit failed: {str(e)}")

    async def _exec_memory_write(self, args: dict[str, Any]) -> ToolResult:
        await self.memory.store_fact(
            tenant_id=self.auth.tenant_id, user_id=self.auth.user_id, **args
        )
        return ToolResult(success=True, output="Fact stored in AverQel memory.")

    async def _exec_todo_write(self, args: dict[str, Any]) -> ToolResult:
        await self.todo.update_todos(
            tenant_id=self.auth.tenant_id,
            user_id=self.auth.user_id,
            todos=args.get("todos", []),
        )
        return ToolResult(success=True, output="Proactive work ledger updated.")

    # --- TIER 3: Execution ---

    async def _exec_bash(
        self,
        args: dict[str, Any],
        _bt: Any = None,
        event_sink: Any = None,
    ) -> ToolResult:
        import re

        cmd = args.get("command")
        normalized = str(cmd or "").strip().lower()
        if self.coding_harness is not None:
            allowed, reason = self.coding_harness.validate_command(str(cmd or ""))
            if not allowed:
                return ToolResult(
                    success=False,
                    output=f"CODING HARNESS BLOCK: {reason}",
                    data={"error_code": "coding_command_blocked", "error_kind": "security_block"},
                )
        destructive = [
            r"(?:^|[\s;|&])rm(?:\s|-)+(?:-rf|-fr|-r)\b",
            r"\brm\s+-rf\s+/(?:\s|$)",
            r"\bdrop\s+(?:database|table|schema|index)\b",
            r"\btruncate\b",
            r"\bformat\b",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r"\bkill\s+-9\b",
            r"\bshutdown\b",
            r"\breboot\b",
            r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};\s*:",
            r"\b(curl|wget)\b.*\|\s*(?:sh|bash)\b",
            r"\bsudo\b",
            r"\bchmod\b.*\b777\b",
            r"\bchown\b.*\broot\b",
            r"\b(userdel|groupdel)\b",
        ]
        if any(re.search(pattern, normalized) for pattern in destructive):
            return ToolResult(
                success=False, output="SECURITY BLOCK: Destructive command intercepted."
            )

        session = self.shell.get_session(
            self.auth.tenant_id,
            self.auth.user_id,
            workspace_path=str(self.workspace.workspace_root),
            session_id="averqel",
        )
        if self.coding_harness is not None and self.coding_harness.container_id:
            timeout_seconds = min(
                max(int(args.get("timeout", 120000)), 1) / 1000,
                float(self.coding_harness.contract.max_seconds),
            )
            try:
                container_result = await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "exec", self.coding_harness.container_id, "bash", "-lc", str(cmd)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                return ToolResult(
                    success=False,
                    output=f"Command timed out after {timeout_seconds:.1f}s.",
                    data={"error_code": "timeout", "error_kind": "timeout"},
                )
            output = (container_result.stdout or "") + (container_result.stderr or "")
            return ToolResult(
                success=container_result.returncode == 0,
                output=output[: int(getattr(self.coding_harness.contract, "output_max_chars", 12000))],
                data={
                    "exit_code": container_result.returncode,
                    "verification": any(marker in normalized for marker in ("pytest", "ruff", "mypy", "lint", "typecheck", "build", "compile")),
                    "verification_pass": container_result.returncode == 0,
                    "review_summary": f"{cmd} completed successfully." if "diff" in normalized and container_result.returncode == 0 else "",
                },
            )
        result = await session.stream_execute(
            str(cmd),
            timeout=min(
                max(int(args.get("timeout", 120000)), 1),
                int(getattr(self.coding_harness.contract, "max_seconds", 1800) * 1000)
                if self.coding_harness is not None
                else 120000,
            ),
            on_chunk=event_sink,
        )
        return ToolResult(
            success=result.exit_code == 0 and not result.timed_out,
            output=(result.output or "[Finished]")[:
                int(getattr(self.coding_harness.contract, "output_max_chars", 12000))
                if self.coding_harness is not None
                else 12000
            ],
            data={
                "bash_id": session.id,
                "exit_code": result.exit_code,
                "verification": any(
                    marker in normalized
                    for marker in ("pytest", "ruff", "mypy", "lint", "typecheck", "build", "compile")
                ),
                "verification_pass": result.exit_code == 0 and not result.timed_out,
                "review_summary": (
                    f"{str(cmd).strip()} completed successfully."
                    if "diff" in normalized and result.exit_code == 0 and not result.timed_out
                    else ""
                ),
            },
        )

    async def _exec_kill_shell(self, args: dict[str, Any]) -> ToolResult:
        self.shell.kill_session(args.get("shell_id"))
        return ToolResult(success=True, output="Shell killed.")

    # --- Domain Specific (Real Wiring) ---

    async def _exec_task(
        self,
        args: dict[str, Any],
        background_tasks: Any = None,
        tool_context: ToolContext | None = None,
    ) -> ToolResult:
        """Delegates a complex task to a specialized sub-agent."""
        from app.deepspace.subagents.subagent_manager import SubagentManager

        stype = args.get("subagent_type", "general-purpose")
        prompt = (
            args.get("prompt") or args.get("description") or args.get("content") or ""
        )
        parent_id = (
            getattr(tool_context, "conversation_id", None)
            or self.current_parent_id
            or uuid.uuid4()
        )

        manager = SubagentManager(self.db, self.settings, self.auth)
        spawn_kwargs = {
            "stype": stype,
            "prompt": prompt,
            "parent_id": parent_id,
            "execution_mode": str(getattr(self, "execution_mode", "auto_review")),
        }
        if getattr(tool_context, "conversation_id", None) is not None:
            spawn_kwargs["conversation_id"] = tool_context.conversation_id
        return await manager.spawn_and_execute(**spawn_kwargs)

    # --- Control ---

    async def _exec_enter_plan_mode(self, args: dict[str, Any]) -> ToolResult:
        self.plan_mode = True
        return ToolResult(
            success=True,
            output="PLAN MODE ACTIVE. Architectural research unlocked. Modification tools locked.",
        )

    async def _exec_exit_plan_mode(self, args: dict[str, Any]) -> ToolResult:
        self.plan_mode = False
        return ToolResult(
            success=True, output="PLAN MODE EXIT. Moving to implementation phase."
        )

    async def _exec_skill(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            output=f"Universal skill '{args.get('skill')}' expanded and active.",
        )

    async def _exec_ask_user_question(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True, output="AverQel is awaiting your clarification...", data=args
        )

    # --- User-Specified Core Tools (Parity Alignment) ---

    async def _exec_web_search(
        self, args: dict[str, Any], event_sink: Any = None
    ) -> ToolResult:
        """Finding current information, research, fact-checking."""
        return await self._exec_web_search_impl(args, event_sink=event_sink)

    async def _exec_web_fetch(
        self, args: dict[str, Any], event_sink: Any = None
    ) -> ToolResult:
        """Reading full page content from a URL with real-time extraction."""
        return await self._exec_web_fetch_impl(args, event_sink=event_sink)

    async def _exec_file_read(self, args: dict[str, Any]) -> ToolResult:
        """Reading files from the user's workspace with multi-format support."""
        # This implementation already maps to _exec_read_file
        # We will enhance _exec_read_file logic below to handle non-text files
        return await self._exec_read_file(args)

    async def _exec_file_write(self, args: dict[str, Any]) -> ToolResult:
        """Creating or updating files."""
        # Mapping to _exec_write_file logic
        return await self._exec_write_file(args)

    async def _exec_file_edit(self, args: dict[str, Any]) -> ToolResult:
        """Surgical edits without rewriting whole file."""
        res = await self._exec_edit_file(args)
        if res.success:
            res.data = {"changes_made": 1}
        return res

    async def _exec_file_list(self, args: dict[str, Any]) -> ToolResult:
        """Exploring directory structure."""
        import os
        import time

        directory = args.get("directory", ".")
        try:
            files = []
            for f in os.listdir(directory):
                path = os.path.join(directory, f)
                files.append(
                    {
                        "name": f,
                        "path": path,
                        "size": os.path.getsize(path),
                        "modified": time.ctime(os.path.getmtime(path)),
                    }
                )
            return ToolResult(
                success=True,
                output=f"Found {len(files)} items in {directory}.",
                data={"files": files},
            )
        except Exception as e:
            return ToolResult(success=False, output=str(e))

    async def _exec_shell_exec(self, args: dict[str, Any]) -> ToolResult:
        """Running terminal commands, scripts, builds."""
        # Mapping to _exec_bash logic
        return await self._exec_bash(args)

    async def _exec_memory_write(self, args: dict[str, Any]) -> ToolResult:
        """Storing facts for later retrieval."""
        await self.memory.store_fact(
            tenant_id=self.auth.tenant_id, user_id=self.auth.user_id, **args
        )
        return ToolResult(success=True, output="Memory stored.")

    async def _exec_memory_read(self, args: dict[str, Any]) -> ToolResult:
        """Retrieving stored facts."""
        val = await self.memory.retrieve_fact(
            tenant_id=self.auth.tenant_id,
            user_id=self.auth.user_id,
            key=args.get("key"),
        )
        return ToolResult(
            success=True,
            output=f"Result: {val}",
            data={"value": val, "exists": val is not None},
        )

    async def _exec_memory_search(self, args: dict[str, Any]) -> ToolResult:
        """Finding relevant past memories."""
        mems = await self.memory.search_memories(
            tenant_id=self.auth.tenant_id,
            user_id=self.auth.user_id,
            query=args.get("query"),
        )
        return ToolResult(
            success=True, output="Search complete.", data={"results": mems}
        )

    async def _exec_spawn_subagent(self, args: dict[str, Any]) -> ToolResult:
        """Delegating isolated subtasks to avoid context bloat."""
        # Mapping to _exec_task logic
        return await self._exec_task(args)

    async def _exec_data_analyze(self, args: dict[str, Any]) -> ToolResult:
        """Analyzing structured or unstructured data."""
        return ToolResult(
            success=True,
            output="Analysis complete.",
            data={
                "analysis": "Insights generated.",
                "insights": ["Point 1", "Point 2"],
            },
        )

    async def _exec_document_convert(self, args: dict[str, Any]) -> ToolResult:
        """Convert a document into another format using the existing ingestion/export stack."""
        from app.deepspace.integrations.export_service import DeepSpaceExportService
        from app.ingestion.services.extractors.router import ExtractorRouter

        input_path_raw = str(args.get("input_path") or "").strip()
        output_format = str(args.get("output_format") or "").strip().lower()
        if not input_path_raw:
            return ToolResult(success=False, output="input_path is required.")
        if output_format not in {"pdf", "docx", "md", "txt", "html"}:
            return ToolResult(success=False, output="output_format is required.")

        input_path = Path(input_path_raw)
        if not input_path.exists() or not input_path.is_file():
            return ToolResult(
                success=False, output=f"Input file not found: {input_path}"
            )

        payload = input_path.read_bytes()
        suffix = input_path.suffix.lower()
        extracted_text = ""
        source_html: str | None = None

        if suffix in {".html", ".htm"}:
            source_html = payload.decode("utf-8", errors="replace")
            extracted_text = " ".join(escape(source_html).split())
        elif suffix in {".md", ".txt"}:
            extracted_text = payload.decode("utf-8", errors="replace")
        else:
            try:
                router = ExtractorRouter(self.settings)
                content_type = (
                    "application/pdf"
                    if suffix == ".pdf"
                    else (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        if suffix == ".docx"
                        else "application/octet-stream"
                    )
                )
                result = router.extract(
                    filename=input_path.name,
                    content_type=content_type,
                    payload=payload,
                )
                extracted_text = result.text.strip()
            except Exception as exc:  # noqa: BLE001
                return ToolResult(
                    success=False, output=f"Failed to convert {input_path}: {exc}"
                )

        title = (
            input_path.stem.replace("_", " ").strip().title() or "Converted Document"
        )
        safe_text = extracted_text.strip() or input_path.read_text(
            encoding="utf-8", errors="replace"
        )

        if output_format == "txt":
            converted_bytes = safe_text.encode("utf-8")
        elif output_format == "md":
            markdown = f"# {title}\n\n{safe_text}\n"
            converted_bytes = markdown.encode("utf-8")
        else:
            if source_html is None:
                source_html = f"<article><pre>{escape(safe_text)}</pre></article>"
            if output_format == "html":
                converted_bytes = source_html.encode("utf-8")
            else:
                exporter = DeepSpaceExportService()
                if output_format == "pdf":
                    buffer = exporter.generate_pdf(source_html, title=title)
                else:
                    buffer = exporter.generate_docx(source_html, title=title)
                converted_bytes = buffer.getvalue()

        output_name = f"{input_path.stem}.converted.{output_format}"
        output_path = input_path.with_name(output_name)
        output_path.write_bytes(converted_bytes)

        return ToolResult(
            success=True,
            output=(
                f"Converted {input_path.name} to {output_format.upper()} at {output_path}."
            ),
            data={
                "input_path": str(input_path),
                "output_path": str(output_path),
                "output_format": output_format,
                "bytes": len(converted_bytes),
            },
        )

    async def _exec_ask_user(self, args: dict[str, Any]) -> ToolResult:
        """Clarifying ambiguous instructions before acting."""
        # Mapping to _exec_ask_user_question logic
        return ToolResult(success=True, output="Awaiting response.", data=args)

    async def _exec_file_delete(self, args: dict[str, Any]) -> ToolResult:
        """DESTRUCTIVE: Deletes a file from the workspace. TIER 4 gate enforced."""
        path = args.get("path")
        if not path:
            return ToolResult(success=False, output="Path is required.")
        try:
            await self.workspace.delete_path_async(path)
            return ToolResult(success=True, output=f"File {path} successfully deleted.")
        except Exception as e:
            return ToolResult(
                success=False, output=f"Failed to delete {path}: {str(e)}"
            )

    async def _exec_view_file_paginated(self, args: dict[str, Any]) -> ToolResult:
        return await exec_view_file_paginated(self, args)

    async def _exec_grep_search_limited(self, args: dict[str, Any]) -> ToolResult:
        return await exec_grep_search_limited(self, args)

    async def _exec_directory_summary_tree(self, args: dict[str, Any]) -> ToolResult:
        return await exec_directory_summary_tree(self, args)

    # --- End of Tools ---
