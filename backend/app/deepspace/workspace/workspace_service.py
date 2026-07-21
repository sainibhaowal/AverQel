from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.deepspace.integrations.client_proxy import client_proxy_registry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkspaceFile:
    name: str
    path: str  # Relative to workspace root
    type: str  # "file" | "directory"
    size: int
    modified_at: str
    extension: str | None = None


class WorkspaceService:
    """
    Manages a sandboxed, tenant-isolated filesystem for agentic operations.
    Prevents path traversal and enforces strict isolation.
    """

    def __init__(self, tenant_id: str, user_id: str, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.tenant_id = tenant_id
        self.user_id = user_id

        # Base path for all workspaces - resolved relative to this file's location
        # (backend/app/services/deepspace/workspace_service.py -> backend/Runtime/workspaces)
        import os
        if os.environ.get("AKS_DISABLE_SANDBOX") == "true":
            root_env = os.environ.get("AKS_WORKSPACE_ROOT")
            if root_env:
                self.workspace_root = Path(root_env).resolve()
            else:
                try:
                    home_dir = Path.home()
                    default_proj = home_dir / "AverQel_Projects" / "Default_Project"
                    default_proj.mkdir(parents=True, exist_ok=True)
                    self.workspace_root = default_proj.resolve()
                except Exception:
                    if Path("/home/ravi/Projects/AverQel").exists():
                        self.workspace_root = Path("/home/ravi/Projects/AverQel").resolve()
                    else:
                        self.workspace_root = Path(os.getcwd()).resolve()
        else:
            resolved_parent = Path(__file__).resolve().parent.parent.parent.parent
            if str(resolved_parent).startswith("/app"):
                self.base_root = resolved_parent / "Runtime" / "workspaces"
            else:
                self.base_root = Path("/home/ravi/.cache/averqel/workspaces")
            self.workspace_root = self.base_root / tenant_id / user_id

        # Ensure workspace exists. A read-only host cache must not prevent the
        # agent from starting; fall back to an isolated process workspace.
        try:
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.workspace_root = (
                Path(tempfile.gettempdir())
                / "averqel-workspaces"
                / tenant_id
                / user_id
            )
            self.workspace_root.mkdir(parents=True, exist_ok=True)

        # Clean up any accidental nested paths from prior runs
        for accidental_dir in ["home", "users", "root"]:
            target_dir = self.workspace_root / accidental_dir
            if target_dir.exists() and target_dir.is_dir():
                try:
                    shutil.rmtree(target_dir)
                except Exception:
                    pass

    def _resolve_path(self, path: str) -> Path:
        """
        Resolves a path. Supports absolute host paths if they start with "/" or "~",
        otherwise falls back to the sandboxed workspace.
        """
        cleaned = str(path).replace("\\", "/")
        import re
        cleaned = re.sub(r"/{2,}", "/", cleaned)

        # If it is absolute on host system (e.g. starts with "/" or "~")
        # we resolve it directly on the host.
        if cleaned.startswith("/") or cleaned.startswith("~"):
            if cleaned.startswith("~"):
                import os
                resolved = Path(os.path.expanduser(cleaned)).resolve()
            else:
                resolved = Path(cleaned).resolve()
            return resolved

        # Convert home and workspace directories prefixes
        import re

        cleaned = re.sub(
            r"^/?home/ravi/Projects/AverQel/?", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"^/?home/ravi/Projects/AverQel/?", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(r"^/?home/ravi/?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^/?root/?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^/?users/?", "", cleaned, flags=re.IGNORECASE)

        if not cleaned.strip():
            cleaned = "."

        requested_path = Path(cleaned)
        if requested_path.is_absolute():
            relative_requested = requested_path.relative_to(requested_path.anchor)
            resolved = (self.workspace_root / relative_requested).resolve()
        else:
            resolved = (self.workspace_root / requested_path).resolve()

        if not str(resolved).startswith(str(self.workspace_root.resolve())):
            raise ValueError(f"Security Violation: Path traversal attempt: {path}")

        return resolved

    def _to_relative(self, path: Path) -> str:
        """Converts an absolute Path back to a workspace-relative string or absolute host path."""
        try:
            return str(path.relative_to(self.workspace_root))
        except ValueError:
            return str(path.resolve())

    def list_files(self, sub_path: str = ".") -> list[WorkspaceFile]:
        """Lists files and directories in a given sub-path."""
        target = self._resolve_path(sub_path)
        if not target.is_dir():
            return []

        results = []
        for entry in target.iterdir():
            stats = entry.stat()
            results.append(
                WorkspaceFile(
                    name=entry.name,
                    path=self._to_relative(entry),
                    type="directory" if entry.is_dir() else "file",
                    size=stats.st_size,
                    modified_at=datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    extension=entry.suffix if entry.is_file() else None,
                )
            )
        return sorted(results, key=lambda x: (x.type != "directory", x.name.lower()))

    def write_file(self, path: str, content: str | bytes) -> str:
        """Writes content to a file in the workspace."""
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(content, bytes) else "w"
        with open(target, mode) as f:
            f.write(content)

        logger.info(f"Workspace [{self.tenant_id}:{self.user_id}] Wrote file: {path}")
        return self._to_relative(target)

    def read_file(self, path: str) -> str:
        """Reads content from a file in the workspace."""
        target = self._resolve_path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        with open(target) as f:
            return f.read()

    def delete_path(self, path: str, recursive: bool = False) -> None:
        """Deletes a file or directory."""
        target = self._resolve_path(path)
        if not target.exists():
            return

        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
        else:
            target.unlink()

        logger.info(f"Workspace [{self.tenant_id}:{self.user_id}] Deleted: {path}")

    def move_path(self, old_path: str, new_path: str) -> str:
        """Moves or renames a path."""
        source = self._resolve_path(old_path)
        destination = self._resolve_path(new_path)

        if not source.exists():
            raise FileNotFoundError(f"Source not found: {old_path}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

        return self._to_relative(destination)

    def copy_path(self, source_path: str, destination_path: str) -> str:
        """Copies a file or directory."""
        source = self._resolve_path(source_path)
        destination = self._resolve_path(destination_path)

        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(str(source), str(destination))
        else:
            shutil.copy2(str(source), str(destination))

        return self._to_relative(destination)

    def create_directory(self, path: str) -> str:
        """Creates a directory."""
        target = self._resolve_path(path)
        target.mkdir(parents=True, exist_ok=True)
        return self._to_relative(target)

    def get_full_host_path(self, path: str) -> str:
        """Returns the absolute path on the host system. Internal use only."""
        return str(self._resolve_path(path))

    async def exists_async(self, path: str) -> bool:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            try:
                return await client_proxy_registry.send_and_await_rpc(
                    self.tenant_id, self.user_id, "fs.exists", {"path": path}, channel=channel
                )
            except Exception:
                return False
        return self._resolve_path(path).exists()

    async def read_file_async(self, path: str) -> str:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            return await client_proxy_registry.send_and_await_rpc(
                self.tenant_id, self.user_id, "fs.read_file", {"path": path}, channel=channel
            )
        return self.read_file(path)

    async def write_file_async(self, path: str, content: str | bytes) -> str:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            text_content = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
            return await client_proxy_registry.send_and_await_rpc(
                self.tenant_id, self.user_id, "fs.write_file", {"path": path, "content": text_content}, channel=channel
            )
        return self.write_file(path, content)

    async def delete_path_async(self, path: str, recursive: bool = False) -> None:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            await client_proxy_registry.send_and_await_rpc(
                self.tenant_id, self.user_id, "fs.delete_path", {"path": path, "recursive": recursive}, channel=channel
            )
            return
        self.delete_path(path, recursive)

    async def move_path_async(self, old_path: str, new_path: str) -> str:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            return await client_proxy_registry.send_and_await_rpc(
                self.tenant_id,
                self.user_id,
                "fs.move_path",
                {"old_path": old_path, "new_path": new_path},
                channel=channel,
            )
        return self.move_path(old_path, new_path)

    async def copy_path_async(self, source_path: str, destination_path: str) -> str:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            return await client_proxy_registry.send_and_await_rpc(
                self.tenant_id,
                self.user_id,
                "fs.copy_path",
                {"source_path": source_path, "destination_path": destination_path},
                channel=channel,
            )
        return self.copy_path(source_path, destination_path)

    async def create_directory_async(self, path: str) -> str:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            return await client_proxy_registry.send_and_await_rpc(
                self.tenant_id, self.user_id, "fs.create_directory", {"path": path}, channel=channel
            )
        return self.create_directory(path)

    async def list_dir_async(self, path: str) -> list[WorkspaceFile]:
        channel = "storage" if client_proxy_registry.is_storage_connected(self.tenant_id, self.user_id) else "workspace"
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id, channel=channel):
            data_list = await client_proxy_registry.send_and_await_rpc(
                self.tenant_id, self.user_id, "fs.list_dir", {"path": path}, channel=channel
            )
            results = []
            for item in data_list:
                results.append(
                    WorkspaceFile(
                        name=item["name"],
                        path=item["path"],
                        type=item["type"],
                        size=item.get("size", 0),
                        modified_at=item.get("modified_at", ""),
                        extension=item.get("extension"),
                    )
                )
            return results
        return self.list_files(path)
