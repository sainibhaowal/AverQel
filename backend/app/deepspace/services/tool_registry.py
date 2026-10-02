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


class DocumentReadArguments(ToolArguments):
    file_id: str | None = Field(default=None, max_length=80)
    filename: str | None = Field(default=None, max_length=255)
    max_characters: int | None = Field(default=None, ge=100, le=200_000)


class DocumentCompareArguments(ToolArguments):
    left_file_id: str | None = Field(default=None, max_length=80)
    right_file_id: str | None = Field(default=None, max_length=80)
    file_ids: list[str] | None = Field(default=None, min_length=2, max_length=5)
    max_characters: int | None = Field(default=None, ge=100, le=100_000)

    @model_validator(mode="after")
    def require_comparison_targets(self) -> DocumentCompareArguments:
        if self.file_ids or (self.left_file_id and self.right_file_id):
            return self
        raise ValueError("document_compare requires file_ids or left_file_id and right_file_id")


class DocumentQueryArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=1_000)
    file_id: str | None = Field(default=None, max_length=80)
    limit: int | None = Field(default=None, ge=1, le=20)


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
    id: str | None = None
    content: str = Field(min_length=1, max_length=1_000)
    active_form: str | None = Field(default=None, max_length=1_000)
    status: Literal["pending", "in_progress", "completed", "blocked", "failed"] | None = None
    priority: int | None = Field(default=None, ge=0, le=1_000)
    dependencies: list[str] | None = Field(default=None, max_length=40)


class TodoWriteArguments(ToolArguments):
    tasks: list[TaskArguments] = Field(max_length=40)


class TodoMarkArguments(ToolArguments):
    task_id: str
    status: Literal["pending", "in_progress", "completed", "blocked", "failed"]
    evidence: str | None = Field(default=None, max_length=1_000)


class AnalyzeArguments(ToolArguments):
    focus: str | None = Field(default=None, max_length=1_000)


class FinalArguments(ToolArguments):
    answer: str = Field(max_length=100_000)
    summary: str | None = Field(default=None, max_length=1_000)


class ReadArguments(ToolArguments):
    target: Literal["note", "library", "memory", "chat", "tasks"]
    file_id: str | None = Field(default=None, max_length=80)
    filename: str | None = Field(default=None, max_length=255)
    memory_key: str | None = Field(default=None, max_length=120)
    folder_id: str | None = Field(default=None, max_length=80)


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
    "web_search": WebSearchArguments,
    "url_read": UrlReadArguments,
    "image_read": UrlReadArguments,
    "sandbox_execute": SandboxExecuteArguments,
    "document_read": DocumentReadArguments,
    "document_compare": DocumentCompareArguments,
    "document_query": DocumentQueryArguments,
    "artifact_create": ArtifactCreateArguments,
    "ask_user": AskUserArguments,
    "todo_write": TodoWriteArguments,
    "todo_read": EmptyArguments,
    "todo_check": EmptyArguments,
    "todo_mark": TodoMarkArguments,
    "observe": EmptyArguments,
    "analyze": AnalyzeArguments,
    "final": FinalArguments,
    "read": ReadArguments,
    "find": FindArguments,
    "write": WriteArguments,
    "edit": EditArguments,
    "delete": DeleteArguments,
}

_TOOL_MODES: dict[str, ToolMode] = {
    "get_tool_result": "read",
    "web_search": "read",
    "url_read": "read",
    "image_read": "read",
    "document_read": "read",
    "document_query": "read",
    "document_compare": "read",
    "todo_read": "read",
    "todo_check": "read",
    "observe": "read",
    "analyze": "read",
    "read": "read",
    "find": "read",
    "todo_write": "write",
    "todo_mark": "write",
    "write": "write",
    "edit": "write",
    "delete": "write",
    "sandbox_execute": "write",
    "artifact_create": "write",
    "final": "write",
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
