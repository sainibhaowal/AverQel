from __future__ import annotations

import html
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

TASK_STATUSES = {"pending", "in_progress", "completed", "blocked", "failed"}
MAX_TASKS = 40
MAX_TASK_TEXT = 1000
MAX_NOTE_LENGTH = 100_000
MAX_WORKSPACE_FILE_LENGTH = 100_000
_SAFE_WORKSPACE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")


def _workspace_content_type(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "md": "text/markdown",
        "mdx": "text/markdown",
        "json": "application/json",
        "csv": "text/csv",
        "yaml": "application/yaml",
        "yml": "application/yaml",
        "xml": "application/xml",
        "html": "text/html",
        "htm": "text/html",
        "css": "text/css",
        "sql": "text/sql",
        "py": "text/x-python",
        "js": "text/javascript",
        "mjs": "text/javascript",
        "ts": "text/javascript",
        "tsx": "text/javascript",
        "diff": "text/x-diff",
        "patch": "text/x-diff",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "svg": "image/svg+xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
        "zip": "application/zip",
    }.get(extension, "text/plain")


def _now() -> datetime:
    return datetime.now(UTC)


def _markdown_to_safe_html(markdown: str) -> str:
    """Convert the small safe Markdown subset used by the note tool to HTML."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{'<br/>'.join(paragraph)}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                output.append(f"<pre><code>{'<br/>'.join(code_lines)}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(html.escape(raw_line))
            continue
        if not line:
            flush_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{html.escape(bullet.group(1))}</li>")
            continue
        close_list()
        paragraph.append(html.escape(line))
    if in_code:
        output.append(f"<pre><code>{'<br/>'.join(code_lines)}</code></pre>")
    flush_paragraph()
    close_list()
    return "\n".join(output)


class DeepSpaceTaskLoopStore:
    """Conversation-scoped, tenant-scoped state for DeepSpace task loops."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _thread_id(conversation_id: uuid.UUID) -> str:
        return str(conversation_id)

    def _tasks(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[AgentTodo]:
        stmt = (
            select(AgentTodo)
            .where(
                AgentTodo.tenant_id == str(tenant_id),
                AgentTodo.user_id == str(user_id),
                AgentTodo.thread_id == self._thread_id(conversation_id),
                AgentTodo.status != "deleted",
            )
            .order_by(AgentTodo.priority.asc(), AgentTodo.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    @staticmethod
    def _serialize(task: AgentTodo) -> dict[str, Any]:
        metadata = dict(task.metadata_json or {})
        return {
            "id": str(task.id),
            "content": task.content,
            "active_form": task.active_form,
            "status": task.status,
            "priority": int(task.priority or 0),
            "dependencies": list(metadata.get("dependencies") or []),
            "evidence": list(metadata.get("evidence") or []),
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    def read_tasks(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        return [
            self._serialize(task)
            for task in self._tasks(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
        ]

    def replace_tasks(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(tasks) > MAX_TASKS:
            raise ValueError(f"A DeepSpace plan may contain at most {MAX_TASKS} tasks.")
        existing = {
            str(task.id): task
            for task in self._tasks(
                tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
        }
        # AgentTodo.id is a global primary key, while models commonly emit
        # short local ids such as "1" or "2". Always allocate UUIDs for new
        # rows and translate dependencies through the request-local ids so a
        # plan can never collide with another conversation's task ledger.
        requested_id_map: dict[str, str] = {}
        retained: set[str] = set()
        requested_ids: set[str] = set()
        result: list[dict[str, Any]] = []
        normalized_tasks: list[tuple[dict[str, Any], str]] = []
        for index, raw in enumerate(tasks):
            if not isinstance(raw, dict):
                raise ValueError(f"Task {index + 1} must be an object.")
            task_id = str(raw.get("id") or "")
            if task_id:
                task_id = task_id[:120]
                if task_id in requested_ids:
                    raise ValueError(f"Task id '{task_id}' is duplicated.")
                requested_ids.add(task_id)
                requested_id_map.setdefault(
                    task_id,
                    task_id if task_id in existing else str(uuid.uuid4()),
                )
            normalized_tasks.append((raw, task_id))

        for index, (raw, requested_id) in enumerate(normalized_tasks):
            content = str(raw.get("content") or "").strip()[:MAX_TASK_TEXT]
            if not content:
                raise ValueError(f"Task {index + 1} is empty.")
            status = str(raw.get("status") or "pending")
            if status not in TASK_STATUSES:
                status = "pending"
            task_id = requested_id_map.get(requested_id, "") if requested_id else ""
            # Existing task ids are stable handles for updates. New tasks use
            # the request-local UUID allocated above, never a model id.
            existing_task_id = requested_id if requested_id in existing else task_id
            task = existing.get(existing_task_id)
            try:
                priority = max(0, min(int(raw.get("priority") or 0), 1000))
            except (TypeError, ValueError):
                priority = 0
            if task is None:
                task = AgentTodo(
                    id=task_id or str(uuid.uuid4()),
                    tenant_id=str(tenant_id),
                    user_id=str(user_id),
                    thread_id=self._thread_id(conversation_id),
                    content=content,
                    active_form=str(
                        raw.get("active_form") or raw.get("activeForm") or content
                    ).strip()[:MAX_TASK_TEXT],
                    status=status,
                    priority=priority,
                    metadata_json={},
                    automation_json={},
                )
                self.db.add(task)
            else:
                task.content = content
                task.active_form = str(
                    raw.get("active_form") or raw.get("activeForm") or content
                ).strip()[:MAX_TASK_TEXT]
                task.status = status
                task.priority = priority
            metadata = dict(task.metadata_json or {})
            dependencies = raw.get("dependencies") or raw.get("depends_on") or []
            metadata["dependencies"] = [
                requested_id_map.get(str(item), str(item))
                for item in dependencies
                if str(item).strip()
            ][:MAX_TASKS]
            if isinstance(raw.get("evidence"), list):
                metadata["evidence"] = [str(item)[:1000] for item in raw["evidence"][:10]]
            task.metadata_json = metadata
            retained.add(str(task.id))
            result.append(self._serialize(task))
        for task_id, task in existing.items():
            if task_id not in retained:
                task.status = "deleted"
        self.db.commit()
        return self.read_tasks(
            tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
        )

    def mark_task(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        task_id: str,
        status: str,
        evidence: str | None = None,
    ) -> dict[str, Any]:
        if status not in TASK_STATUSES:
            raise ValueError("Invalid task status.")
        tasks = self._tasks(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        task = next((item for item in tasks if str(item.id) == task_id), None)
        if task is None:
            raise ValueError("Task not found in this DeepSpace conversation.")
        if status in {"in_progress", "completed"}:
            task_map = {str(item.id): item for item in tasks}
            dependencies = list((task.metadata_json or {}).get("dependencies") or [])
            incomplete = [
                dependency
                for dependency in dependencies
                if dependency not in task_map or task_map[dependency].status != "completed"
            ]
            if incomplete:
                raise ValueError(f"Task dependencies are incomplete: {', '.join(incomplete[:5])}")
        if status == "completed" and not (
            evidence or list((task.metadata_json or {}).get("evidence") or [])
        ):
            raise ValueError("Completed tasks require evidence.")
        task.status = status
        metadata = dict(task.metadata_json or {})
        if evidence and evidence.strip():
            evidence_items = list(metadata.get("evidence") or [])
            evidence_items.append(evidence.strip()[:1000])
            metadata["evidence"] = evidence_items[-10:]
        task.metadata_json = metadata
        self.db.commit()
        return self._serialize(task)

    def check_tasks(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> dict[str, Any]:
        tasks = self._tasks(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        task_map = {str(item.id): item for item in tasks}
        serialized = [self._serialize(item) for item in tasks]
        dependency_issues: list[dict[str, Any]] = []
        for item in serialized:
            unresolved = [
                dependency
                for dependency in item["dependencies"]
                if dependency not in task_map or task_map[dependency].status != "completed"
            ]
            if unresolved:
                dependency_issues.append({"task_id": item["id"], "dependencies": unresolved})
        completed = [item for item in serialized if item["status"] == "completed"]
        remaining = [item for item in serialized if item["status"] != "completed"]
        blocked = [item for item in serialized if item["status"] in {"blocked", "failed"}]
        return {
            "complete": bool(tasks) and len(completed) == len(tasks),
            "task_count": len(tasks),
            "completed_count": len(completed),
            "remaining_count": len(remaining),
            "blocked_count": len(blocked),
            "dependency_issues": dependency_issues,
            "tasks": serialized,
        }

    def read_note(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> dict[str, Any]:
        conversation = self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == "deepspace",
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ValueError("DeepSpace conversation not found.")
        content = conversation.content_html or ""
        return {
            "conversation_id": str(conversation_id),
            "content_html": content,
            "length": len(content),
        }

    def write_note(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        markdown: str,
        mode: str = "replace",
    ) -> dict[str, Any]:
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("Markdown content is required.")
        if len(markdown) > MAX_NOTE_LENGTH:
            raise ValueError("Note content is too large.")
        conversation = self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == "deepspace",
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ValueError("DeepSpace conversation not found.")
        rendered = _markdown_to_safe_html(markdown)
        if mode == "append" and conversation.content_html:
            rendered = f"{conversation.content_html}\n{rendered}"
        elif mode != "replace":
            raise ValueError("Note mode must be replace or append.")
        conversation.content_html = rendered[:MAX_NOTE_LENGTH]
        conversation.updated_at = _now()
        self.db.commit()
        return self.read_note(tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)

    def write_workspace_file(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        filename: str,
        content: str,
        mode: str = "replace",
    ) -> dict[str, Any]:
        """Create or update a text file in the visible DeepSpace Library."""
        normalized_name = filename.strip()
        if not _SAFE_WORKSPACE_FILE_NAME.fullmatch(normalized_name) or normalized_name in {
            ".",
            "..",
        }:
            raise ValueError("Workspace file name is invalid.")
        if not isinstance(content, str) or len(content) > MAX_WORKSPACE_FILE_LENGTH:
            raise ValueError("Workspace file content is invalid or too large.")
        if mode not in {"replace", "append"}:
            raise ValueError("Workspace file mode must be replace or append.")
        conversation = self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.kind == "deepspace",
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ValueError("DeepSpace conversation not found.")
        file = self.db.execute(
            select(DeepSpaceWorkspaceFile).where(
                DeepSpaceWorkspaceFile.tenant_id == tenant_id,
                DeepSpaceWorkspaceFile.user_id == user_id,
                DeepSpaceWorkspaceFile.conversation_id == conversation_id,
                DeepSpaceWorkspaceFile.name == normalized_name,
            )
        ).scalar_one_or_none()
        if file is None:
            file = DeepSpaceWorkspaceFile(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                name=normalized_name,
                content_type=_workspace_content_type(normalized_name),
                content=content,
                source="agent",
                size_bytes=len(content.encode("utf-8")),
            )
            self.db.add(file)
        else:
            file.content = (
                f"{file.content}\n{content}" if mode == "append" and file.content else content
            )
            file.size_bytes = len(file.content.encode("utf-8"))
            file.source = "agent"
            file.updated_at = _now()
        self.db.commit()
        return {
            "id": str(file.id),
            "name": file.name,
            "content_type": file.content_type,
            "size_bytes": file.size_bytes,
            "source": file.source,
        }


def summarize_tasks(tasks: Iterable[dict[str, Any]]) -> str:
    items = list(tasks)
    if not items:
        return "No active task plan."
    complete = sum(item.get("status") == "completed" for item in items)
    return f"{complete}/{len(items)} tasks completed."
