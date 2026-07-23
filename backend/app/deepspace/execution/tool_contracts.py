from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from app.deepspace.execution.agent_permissions import PermissionLevel

if TYPE_CHECKING:
    from app.deepspace.execution.agent_tools import AgentToolDef, ToolResult

ToolFailureCode = Literal[
    "unknown_tool",
    "invalid_arguments",
    "plan_mode_blocked",
    "timeout",
    "cancelled",
    "execution_error",
    "approval_required",
    "compensation_required",
]

RiskClass = Literal[
    "read_only",
    "internal_write",
    "execution",
    "external_read",
    "external_side_effect",
    "destructive",
    "privileged",
    "untrusted",
    "ambiguous",
]
ApprovalRequirement = Literal["auto", "human", "block"]


@dataclass(frozen=True, slots=True)
class ToolRetryPolicy:
    """Retry behavior is part of the contract, never inferred at execution time."""

    max_retries: int = 0
    retryable_errors: tuple[str, ...] = ("timeout", "execution_error")
    backoff_seconds: float = 0.25

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolContract:
    """Complete safety contract for one callable capability."""

    risk_class: RiskClass
    capabilities: tuple[str, ...]
    idempotency_support: bool
    retry_policy: ToolRetryPolicy
    timeout_seconds: float
    compensation_required: bool
    approval_requirement: ApprovalRequirement
    tenant_scope: str
    workspace_scope: str
    untrusted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["retry_policy"] = self.retry_policy.to_dict()
        return payload

    @property
    def has_side_effect(self) -> bool:
        return any(capability in {"write", "external", "destructive", "privilege", "execution"} for capability in self.capabilities)


_EXTERNAL_PREFIXES = ("github_", "drive_", "gmail_", "calendar_", "notion_", "slack_")
_EXTERNAL_READS = {
    "github_search", "github_read_file", "drive_search", "drive_read_file", "gmail_search", "gmail_read",
    "calendar_list_events", "calendar_find_free_slots", "list_connectors", "get_connector_status",
}
_EXTERNAL_WRITES = {
    "github_create_file", "github_update_file", "github_delete_file", "github_create_issue", "github_comment_issue", "github_update_issue",
    "drive_upload_file", "drive_update_file", "drive_delete_file", "gmail_send", "gmail_manage", "gmail_delete_message",
    "calendar_create_event", "calendar_update_event", "calendar_delete_event", "notion_create_page", "notion_append_content",
    "slack_post_message", "slack_update_message", "slack_delete_message", "sync_connector", "crawl_url",
}
_DESTRUCTIVE_NAMES = {
    "kill_shell", "github_delete_file", "drive_delete_file", "gmail_delete_message", "calendar_delete_event", "slack_delete_message",
}
_WORKSPACE_NAMES = {"read_file", "write_file", "edit_file", "notebook_edit", "glob", "grep", "bash", "bash_output", "kill_shell"}


def infer_tool_contract(*, name: str, permission_level: PermissionLevel, metadata: dict[str, Any] | None = None) -> ToolContract:
    """Build a conservative explicit contract for built-in and dynamic tools."""
    normalized = str(name or "").strip().lower()
    metadata = dict(metadata or {})
    is_mcp = bool(metadata.get("is_mcp")) or normalized == "mcp_call"
    tier = permission_level.value if isinstance(permission_level, PermissionLevel) else str(permission_level)
    if is_mcp:
        configured_risk = str(metadata.get("mcp_risk_level") or "").strip().lower()
        configured_approval = str(metadata.get("mcp_approval_requirement") or "").strip().lower()
        if configured_risk in {"read", "write", "delete", "external_message"}:
            risk_map: dict[str, RiskClass] = {
                "read": "external_read",
                "write": "external_side_effect",
                "delete": "destructive",
                "external_message": "external_side_effect",
            }
            risk = risk_map[configured_risk]
            capabilities = (
                ("read", "external", "untrusted")
                if configured_risk == "read"
                else ("external", "write", "untrusted")
            )
            retries = ToolRetryPolicy(max_retries=1) if configured_risk == "read" else ToolRetryPolicy()
            timeout = 60.0
            idempotent = configured_risk == "read"
            compensation = not idempotent
            approval = (
                configured_approval
                if configured_approval in {"auto", "human", "block"}
                else "human"
            )
        else:
            # Unclassified dynamic tools retain the historical fail-safe:
            # untrusted and human-approved with no retry.
            risk = "untrusted"
            capabilities = ("external", "untrusted")
            retries = ToolRetryPolicy()
            timeout = 60.0
            idempotent = False
            compensation = True
            approval = "human"
    elif normalized in _DESTRUCTIVE_NAMES:
        risk = "destructive"
        capabilities = ("write", "destructive")
        retries = ToolRetryPolicy()
        timeout = 90.0
        idempotent = False
        compensation = True
        approval = "human"
    elif normalized == "task" or "tier5" in tier:
        risk = "privileged"
        capabilities = ("privilege", "external")
        retries = ToolRetryPolicy()
        timeout = 120.0
        idempotent = False
        compensation = True
        approval = "human"
    elif normalized in _EXTERNAL_WRITES or normalized.startswith(_EXTERNAL_PREFIXES) and normalized not in _EXTERNAL_READS:
        risk = "external_side_effect"
        capabilities = ("external", "write")
        retries = ToolRetryPolicy()
        timeout = 60.0
        idempotent = False
        compensation = True
        approval = "human"
    elif normalized in _EXTERNAL_READS or normalized.startswith(_EXTERNAL_PREFIXES):
        risk = "external_read"
        capabilities = ("read", "external")
        retries = ToolRetryPolicy(max_retries=1)
        timeout = 60.0
        idempotent = True
        compensation = False
        approval = "auto"
    elif normalized in {"write_file", "edit_file", "notebook_edit", "memory_write", "todo_write", "data_analyze", "document_convert"} or "tier2" in tier:
        risk = "internal_write"
        capabilities = ("write",)
        retries = ToolRetryPolicy()
        timeout = 60.0
        idempotent = True
        compensation = False
        approval = "human"
    elif normalized == "bash_output":
        risk = "read_only"
        capabilities = ("read",)
        retries = ToolRetryPolicy(max_retries=1)
        timeout = 30.0
        idempotent = True
        compensation = False
        approval = "auto"
    elif normalized in {"bash", "kill_shell"} or "tier3" in tier:
        risk = "execution"
        capabilities = ("execution",)
        retries = ToolRetryPolicy()
        timeout = 120.0
        idempotent = False
        compensation = True
        approval = "human"
    else:
        risk = "read_only"
        capabilities = ("read",)
        retries = ToolRetryPolicy(max_retries=1)
        timeout = 30.0
        idempotent = True
        compensation = False
        approval = "auto"
    return ToolContract(
        risk_class=risk,
        capabilities=capabilities,
        idempotency_support=idempotent,
        retry_policy=retries,
        timeout_seconds=timeout,
        compensation_required=compensation,
        approval_requirement=approval,
        tenant_scope="tenant_user",
        workspace_scope="tenant_workspace" if normalized in _WORKSPACE_NAMES else "not_applicable",
        untrusted=is_mcp,
    )

_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|access[_-]?token|refresh[_-]?token|password|secret|credential|private[_-]?key)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ToolValidationResult:
    valid: bool
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionPolicy:
    timeout_seconds: float
    retries: int
    redacted_args: dict[str, Any]
    contract: ToolContract | None = None


def redact_tool_payload(value: Any) -> Any:
    """Redact secrets from nested tool payloads before audit persistence."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY_PATTERN.search(str(key)):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_tool_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_tool_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_tool_payload(item) for item in value]
    return value


def classify_tool_timeout(tool: AgentToolDef) -> float:
    """Return a conservative timeout budget for a tool definition."""
    contract = getattr(tool, "contract", None)
    if isinstance(contract, ToolContract):
        return contract.timeout_seconds
    name = tool.name
    if name in {"bash", "bash_output", "sync_connector", "crawl_url", "task"}:
        return 120.0
    if name.startswith(
        ("drive_", "github_", "gmail_", "calendar_", "notion_", "slack_")
    ):
        return 60.0
    if tool.permission_level in {
        PermissionLevel.TIER3_APPROVE,
        PermissionLevel.TIER4_WARN,
        PermissionLevel.TIER5_SPAWN,
    }:
        return 90.0
    return 30.0


def classify_tool_retries(tool: AgentToolDef) -> int:
    """Only retry read-only/network-ish tools by default."""
    contract = getattr(tool, "contract", None)
    if isinstance(contract, ToolContract):
        return contract.retry_policy.max_retries
    name = tool.name
    if name in {
        "web_fetch",
        "web_search",
        "search_ecosystem_docs",
        "github_search",
        "github_read_file",
        "drive_search",
        "drive_read_file",
        "gmail_search",
        "gmail_read",
        "calendar_list_events",
        "calendar_find_free_slots",
        "list_connectors",
        "get_connector_status",
    }:
        return 1
    return 0


def build_tool_execution_policy(
    tool: AgentToolDef, args: dict[str, Any]
) -> ToolExecutionPolicy:
    return ToolExecutionPolicy(
        timeout_seconds=classify_tool_timeout(tool),
        retries=classify_tool_retries(tool),
        redacted_args=redact_tool_payload(args),
        contract=getattr(tool, "contract", None),
    )


def validate_tool_arguments(tool: AgentToolDef, args: Any) -> ToolValidationResult:
    """Validate model-provided tool arguments against the declared JSON schema."""
    if not isinstance(args, dict):
        return ToolValidationResult(
            valid=False, message="Tool arguments must be an object."
        )
    try:
        Draft202012Validator.check_schema(tool.parameters)
        validator = Draft202012Validator(tool.parameters)
        normalized_args = _normalize_tool_arguments(tool.name, args)
        validator.validate(normalized_args)
    except SchemaError as exc:
        return ToolValidationResult(
            valid=False,
            message=f"Tool schema for '{tool.name}' is invalid: {exc.message}",
        )
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.path)
        suffix = f" at '{path}'" if path else ""
        return ToolValidationResult(
            valid=False,
            message=f"Invalid arguments for '{tool.name}'{suffix}: {exc.message}",
        )
    return ToolValidationResult(valid=True)


def _normalize_tool_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Patch up common model omissions before schema validation.

    Some models commonly omit fields that our runtime can safely infer. We only
    fill in low-risk defaults here so the tool call can proceed instead of
    failing repeatedly on the same shape.
    """
    normalized = dict(args)
    if tool_name == "todo_write":
        todos = normalized.get("todos")
        if isinstance(todos, list):
            normalized_todos: list[dict[str, Any]] = []
            for todo in todos:
                if not isinstance(todo, dict):
                    normalized_todos.append(todo)
                    continue
                item = dict(todo)
                item.setdefault("status", "pending")
                if not str(
                    item.get("activeForm") or item.get("active_form") or ""
                ).strip():
                    item["activeForm"] = str(item.get("content") or "").strip()
                normalized_todos.append(item)
            normalized["todos"] = normalized_todos
        return normalized

    if tool_name == "task":
        if not str(normalized.get("prompt") or "").strip():
            fallback_prompt = str(
                normalized.get("description") or normalized.get("content") or ""
            ).strip()
            if fallback_prompt:
                normalized["prompt"] = fallback_prompt
        if not str(normalized.get("description") or "").strip():
            fallback_description = str(normalized.get("prompt") or "").strip()
            if fallback_description:
                normalized["description"] = fallback_description[:120]
        return normalized

    return normalized


def failure_result(code: ToolFailureCode, message: str, **data: Any) -> ToolResult:
    from app.deepspace.execution.agent_tools import ToolResult

    return ToolResult(
        success=False,
        output=message,
        data={"error_code": code, **data},
    )
