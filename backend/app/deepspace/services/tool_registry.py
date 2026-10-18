"""Typed native-tool catalogue for the DeepSpace provider boundary.

The catalogue deliberately does *not* own authorization, tenant scope, MCP
bindings, approvals, or execution.  Those are dynamic runtime concerns.  It
owns the stable part of a native capability: its name, model-facing schema,
typed input validator, execution mode, and deterministic schema digest.

The initial migration accepts the existing OpenAI-compatible definitions as a
compatibility input.  This keeps provider payloads byte-compatible while the
legacy definitions are progressively moved into typed contracts.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ToolMode = Literal["read", "write", "interactive"]


class ToolArguments(BaseModel):
    """Base native tool input: never silently accept unknown model arguments."""

    model_config = ConfigDict(extra="forbid")


class EmptyArguments(ToolArguments):
    pass


class GetToolResultArguments(ToolArguments):
    result_ref: str = Field(min_length=8, max_length=128)


class WebSearchArguments(ToolArguments):
    query: str = Field(min_length=2, max_length=512)
    max_results: int | None = Field(default=None, ge=1, le=10)
    domains: list[str] | None = Field(default=None, max_length=20)
    time_range: Literal["day", "week", "month", "year"] | None = None


class UrlReadArguments(ToolArguments):
    url: str = Field(min_length=8, max_length=2048)
    allowed_domains: list[str] | None = Field(default=None, max_length=20)


class SandboxExecuteArguments(ToolArguments):
    language: Literal["python", "sql"]
    code: str = Field(min_length=1, max_length=100_000)
    input: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    file_ids: list[str] | None = Field(default=None, max_length=5)


class ArtifactCreateArguments(ToolArguments):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=100_000)
    format: Literal["markdown", "csv", "json", "html", "text", "svg", "mermaid", "uml"] | None = (
        None
    )
    kind: Literal["document", "table", "chart", "diagram", "data", "code"] | None = None
    mode: Literal["replace", "append"] | None = None


class AskUserArguments(ToolArguments):
    question: str = Field(min_length=1, max_length=2_000)
    options: list[str] | None = Field(default=None, max_length=8)


class TaskArguments(ToolArguments):
    id: str | None = Field(default=None, min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1_000)
    active_form: str | None = Field(default=None, max_length=1_000)
    success_criteria: str | None = Field(default=None, max_length=1_000)
    verification: str | None = Field(default=None, max_length=1_000)
    status: Literal["pending", "in_progress", "completed", "blocked", "failed"] | None = None
    priority: int | None = Field(default=None, ge=0, le=1_000)
    dependencies: list[str] | None = Field(default=None, max_length=40)


class TodoWriteArguments(ToolArguments):
    """One durable task-ledger tool with explicit, validated operations."""

    operation: Literal["replace", "read", "update", "check"]
    tasks: list[TaskArguments] | None = Field(default=None, min_length=1, max_length=40)
    task_id: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["pending", "in_progress", "completed", "blocked", "failed"] | None = None
    evidence: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_operation(self) -> TodoWriteArguments:
        """Keep incomplete plans out of the execution loop.

        The task store repeats these checks as a persistence boundary. Doing
        the structural part here lets the provider correct its plan instead of
        beginning work from an ambiguous checklist.
        """

        if self.operation == "read" or self.operation == "check":
            return self
        if self.operation == "update":
            if not self.task_id or not self.status:
                raise ValueError("todo_write(update) requires task_id and status")
            if (
                self.status in {"completed", "blocked", "failed"}
                and not str(self.evidence or "").strip()
            ):
                raise ValueError("terminal todo_write(update) requires evidence")
            return self
        if not self.tasks:
            raise ValueError("todo_write(replace) requires a tasks array")
        if len(self.tasks) <= 1:
            return self

        task_ids = [str(task.id or "").strip() for task in self.tasks]
        if not all(task_ids):
            raise ValueError("multi-step plans require an id for every task")
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("multi-step plans require unique task ids")
        for task, task_id in zip(self.tasks, task_ids, strict=True):
            if not str(task.success_criteria or "").strip():
                raise ValueError(f"task {task_id!r} requires success_criteria")
            if not str(task.verification or "").strip():
                raise ValueError(f"task {task_id!r} requires verification")
            dependencies = [
                str(item).strip() for item in (task.dependencies or []) if str(item).strip()
            ]
            if task_id in dependencies:
                raise ValueError(f"task {task_id!r} cannot depend on itself")
            unknown = [item for item in dependencies if item not in task_ids]
            if unknown:
                raise ValueError(f"task {task_id!r} has unknown dependencies")

        dependencies_by_task = {
            task_id: [str(item).strip() for item in (task.dependencies or []) if str(item).strip()]
            for task, task_id in zip(self.tasks, task_ids, strict=True)
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise ValueError("task dependencies contain a cycle")
            visiting.add(task_id)
            for dependency in dependencies_by_task[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        return self


class AnalyzeArguments(ToolArguments):
    operation: Literal["compare_documents"] = "compare_documents"
    left_file_id: str | None = Field(default=None, max_length=80)
    right_file_id: str | None = Field(default=None, max_length=80)
    file_ids: list[str] | None = Field(default=None, min_length=2, max_length=5)
    max_characters: int | None = Field(default=None, ge=100, le=100_000)

    @model_validator(mode="after")
    def require_comparison_targets(self) -> AnalyzeArguments:
        if self.file_ids or (self.left_file_id and self.right_file_id):
            return self
        raise ValueError("analyze(compare_documents) requires file_ids or a left/right file pair")


class DiscoverToolsArguments(ToolArguments):
    query: str = Field(min_length=2, max_length=1_000)
    tool_names: list[str] | None = Field(default=None, min_length=1, max_length=8)


class ReadArguments(ToolArguments):
    target: Literal["note", "library", "memory", "chat", "project"]
    operation: Literal["read", "query"] = "read"
    file_id: str | None = Field(default=None, max_length=80)
    filename: str | None = Field(default=None, max_length=255)
    memory_key: str | None = Field(default=None, max_length=120)
    folder_id: str | None = Field(default=None, max_length=80)
    query: str | None = Field(default=None, min_length=1, max_length=1_000)
    limit: int | None = Field(default=None, ge=1, le=20)
    max_characters: int | None = Field(default=None, ge=100, le=200_000)

    @model_validator(mode="after")
    def validate_read_operation(self) -> ReadArguments:
        if self.operation == "query" and (self.target != "library" or not self.query):
            raise ValueError("read(query) requires target='library' and a query")
        return self


class FindArguments(ToolArguments):
    target: Literal["library", "memory", "chat"]
    query: str | None = Field(default=None, min_length=1, max_length=1_000)
    limit: int | None = Field(default=None, ge=1, le=50)
    folder_id: str | None = Field(default=None, max_length=80)


class WriteArguments(ToolArguments):
    target: Literal["note", "library", "memory"]
    content: str | None = Field(default=None, max_length=100_000)
    mode: Literal["replace", "append"] | None = None
    source: Literal["previous_assistant", "message"] | None = None
    source_message_id: str | None = Field(default=None, max_length=80)
    filename: str | None = Field(default=None, max_length=255)
    folder_name: str | None = Field(default=None, max_length=255)
    memory_key: str | None = Field(default=None, max_length=120)
    memory_scope: Literal["user", "session"] | None = None
    folder_id: str | None = Field(default=None, max_length=80)


class EditArguments(ToolArguments):
    target: Literal["note", "library"]
    operation: Literal["replace", "append", "rename", "move"]
    file_id: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=255)
    content: str | None = Field(default=None, max_length=100_000)
    folder_id: str | None = Field(default=None, max_length=80)
    new_folder_name: str | None = Field(default=None, max_length=255)


class DeleteArguments(ToolArguments):
    target: Literal["library", "memory"]
    file_id: str | None = Field(default=None, max_length=80)
    memory_key: str | None = Field(default=None, max_length=120)


class NativeToolValidationError(ValueError):
    """A model supplied syntactically valid JSON that fails a native contract."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    mode: ToolMode
    arguments_model: type[ToolArguments]
    provider_definition: dict[str, Any]
    schema_version: str = "1"
    concurrency: Literal["read_parallel", "write_serial", "interactive"] = "read_parallel"
    idempotency: Literal["safe", "guarded", "external"] = "safe"

    @property
    def schema_digest(self) -> str:
        encoded = json.dumps(
            self.provider_definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    def emit_openai_compatible(self) -> dict[str, Any]:
        """Return a defensive copy; callers may safely tailor lifecycle schemas."""

        return copy.deepcopy(self.provider_definition)

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.arguments_model.model_validate(arguments).model_dump(exclude_none=True)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}"
                for item in exc.errors(include_url=False)
            )
            raise NativeToolValidationError(details[:1_500]) from exc


class ToolRegistry:
    """Immutable-at-runtime catalogue of native DeepSpace capabilities."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or spec.name in self._specs:
            raise ValueError(f"Duplicate or empty DeepSpace tool name: {spec.name!r}")
        function = spec.provider_definition.get("function")
        if not isinstance(function, dict) or function.get("name") != spec.name:
            raise ValueError(f"Provider definition does not match tool {spec.name!r}")
        self._specs[spec.name] = spec

    def names(self) -> frozenset[str]:
        return frozenset(self._specs)

    def contains(self, name: str) -> bool:
        return name in self._specs

    def spec(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"Unknown DeepSpace native tool: {name}") from exc

    def emit(self, name: str) -> dict[str, Any]:
        return self.spec(name).emit_openai_compatible()

    def emit_many(self, names: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
        return [self.emit(name) for name in names]

    def validate(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.spec(name).validate(arguments)


_ARGUMENT_MODELS: dict[str, type[ToolArguments]] = {
    "get_tool_result": GetToolResultArguments,
    "discover_tools": DiscoverToolsArguments,
    "web_search": WebSearchArguments,
    "url_read": UrlReadArguments,
    "image_read": UrlReadArguments,
    "sandbox_execute": SandboxExecuteArguments,
    "artifact_create": ArtifactCreateArguments,
    "ask_user": AskUserArguments,
    "todo_write": TodoWriteArguments,
    "analyze": AnalyzeArguments,
    "read": ReadArguments,
    "find": FindArguments,
    "write": WriteArguments,
    "edit": EditArguments,
    "delete": DeleteArguments,
}

_TOOL_MODES: dict[str, ToolMode] = {
    "get_tool_result": "read",
    "discover_tools": "read",
    "web_search": "read",
    "url_read": "read",
    "image_read": "read",
    "analyze": "read",
    "read": "read",
    "find": "read",
    "todo_write": "write",
    "write": "write",
    "edit": "write",
    "delete": "write",
    "sandbox_execute": "write",
    "artifact_create": "write",
    "ask_user": "interactive",
}


def build_native_tool_registry(definitions: list[dict[str, Any]]) -> ToolRegistry:
    """Build the compatibility registry from the existing provider definitions.

    Requiring a complete mapping makes a missing typed validator a startup
    error rather than silently exposing an unvalidated native capability.
    """

    registry = ToolRegistry()
    for definition in definitions:
        function = definition.get("function") if isinstance(definition, dict) else None
        name = str(function.get("name") or "") if isinstance(function, dict) else ""
        model = _ARGUMENT_MODELS.get(name)
        mode = _TOOL_MODES.get(name)
        if model is None or mode is None:
            raise ValueError(f"Native tool {name!r} has no typed registry contract")
        registry.register(
            ToolSpec(
                name=name,
                description=str((function or {}).get("description") or ""),
                mode=mode,
                arguments_model=model,
                provider_definition=definition,
                concurrency=(
                    "interactive"
                    if mode == "interactive"
                    else ("write_serial" if mode == "write" else "read_parallel")
                ),
                idempotency=("external" if name in {"delete", "write", "edit"} else "safe"),
            )
        )
    return registry
