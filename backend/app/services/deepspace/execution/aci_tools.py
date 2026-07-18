from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.deepspace.execution.agent_permissions import PermissionLevel

if TYPE_CHECKING:
    from app.services.deepspace.execution.agent_tools import ToolResult

# Dynamic Tool Definitions
VIEW_FILE_PAGINATED = {
    "name": "view_file_paginated",
    "description": "Read text files with pagination and compression to preserve context. Shows a specific page (default 100 lines) of a file.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file relative to the workspace."},
            "page": {"type": "integer", "default": 1, "description": "Page number to view (1-indexed)."},
            "page_size": {"type": "integer", "default": 100, "description": "Number of lines per page."},
        },
        "required": ["path"],
    },
    "permission_level": PermissionLevel.TIER1_AUTO,
}

GREP_SEARCH_LIMITED = {
    "name": "grep_search_limited",
    "description": "Search for regular expressions or text query across the workspace with a hard result cap of 50 matches.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Regex or string search query."},
            "path": {"type": "string", "description": "Optional search directory path relative to workspace."},
        },
        "required": ["query"],
    },
    "permission_level": PermissionLevel.TIER1_AUTO,
}

DIRECTORY_SUMMARY_TREE = {
    "name": "directory_summary_tree",
    "description": "Provides a shallow summary tree layout of a directory to prevent massive file path outputs.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Optional folder path to scan relative to workspace."},
            "max_depth": {"type": "integer", "default": 2, "description": "Max depth of the directory structure traversal."},
        },
    },
    "permission_level": PermissionLevel.TIER1_AUTO,
}


async def exec_view_file_paginated(executor: Any, args: dict[str, Any]) -> ToolResult:
    from app.services.deepspace.execution.agent_tools import ToolResult
    path = args.get("path")
    page = max(1, int(args.get("page", 1)))
    page_size = max(10, int(args.get("page_size", 100)))

    try:
        exists = await executor.workspace.exists_async(path)
        if not exists:
            return ToolResult(success=False, output=f"File not found: {path}")

        file_content = await executor.workspace.read_file_async(path)
        lines = file_content.splitlines(keepends=True)

        total_lines = len(lines)
        total_pages = (total_lines + page_size - 1) // page_size

        if page > total_pages and total_pages > 0:
            page = total_pages

        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_lines)
        page_content = "".join(lines[start_idx:end_idx])

        # Add pagination header/footer to the LLM observation window
        output_parts = [
            f"--- PAGE {page}/{total_pages} OF {path} ({total_lines} lines total) ---",
            page_content,
            f"--- END OF PAGE {page}/{total_pages} ---",
            f"To view other lines, call `view_file_paginated` with `page={page+1}` or `page={page-1}`."
        ]

        executor.read_files.add(str(path))
        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            data={
                "path": str(path),
                "page": page,
                "total_pages": total_pages,
                "total_lines": total_lines,
            }
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Error reading file: {str(e)}")


async def exec_grep_search_limited(executor: Any, args: dict[str, Any]) -> ToolResult:
    import re

    from app.services.deepspace.execution.agent_tools import ToolResult
    query = args.get("query", "")
    search_dir = args.get("path") or ""

    try:
        root_dir = executor.workspace._resolve_path(search_dir)
        if not root_dir.exists() or not root_dir.is_dir():
            return ToolResult(success=False, output=f"Search path not found: {search_dir}")

        pattern = re.compile(query, re.IGNORECASE)
        matches = []
        limit = 50
        truncated = False

        for root, dirs, files in os.walk(root_dir):
            # Prune hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                if file.startswith('.'):
                    continue
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                rel_path = os.path.relpath(file_path, executor.workspace.workspace_root)
                                matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                                if len(matches) >= limit:
                                    truncated = True
                                    break
                except Exception:
                    pass
                if truncated:
                    break
            if truncated:
                break

        header = f"--- Grep Search results for query '{query}' (limited to {limit}) ---"
        body = "\n".join(matches) if matches else "No matches found."
        footer = "\n--- Results truncated to 50 items. Refine your query for narrower matches. ---" if truncated else ""

        return ToolResult(
            success=True,
            output=f"{header}\n{body}{footer}",
            data={"matches_count": len(matches), "truncated": truncated}
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Error running search: {str(e)}")


async def exec_directory_summary_tree(executor: Any, args: dict[str, Any]) -> ToolResult:
    from app.services.deepspace.execution.agent_tools import ToolResult
    search_dir = args.get("path") or ""
    max_depth = int(args.get("max_depth", 2))

    try:
        from app.services.deepspace.integrations.client_proxy import client_proxy_registry
        if client_proxy_registry.is_client_connected(executor.workspace.tenant_id, executor.workspace.user_id):
            lines = []
            async def build_tree(current_dir: str, depth: int):
                if depth > max_depth:
                    return
                try:
                    entries = await executor.workspace.list_dir_async(current_dir)
                    indent = "  " * depth
                    for entry in entries:
                        if entry.name.startswith("."):
                            continue
                        if entry.type == "directory":
                            lines.append(f"{indent}📁 {entry.name}/")
                            await build_tree(entry.path, depth + 1)
                        else:
                            lines.append(f"{indent}  📄 {entry.name}")
                except Exception:
                    pass
            await build_tree(search_dir, 0)
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"depth": max_depth}
            )

        root_dir = executor.workspace._resolve_path(search_dir)
        if not root_dir.exists() or not root_dir.is_dir():
            return ToolResult(success=False, output=f"Directory path not found: {search_dir}")

        lines = []
        base_depth = len(root_dir.parts)

        for root, dirs, files in os.walk(root_dir):
            # Prune hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            current_path = Path(root)
            depth = len(current_path.parts) - base_depth
            if depth > max_depth:
                continue

            indent = "  " * depth
            lines.append(f"{indent}📁 {current_path.name}/")

            if depth < max_depth:
                for file in files:
                    if file.startswith('.'):
                        continue
                    lines.append(f"{indent}  📄 {file}")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"depth": max_depth}
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Error compiling tree: {str(e)}")
