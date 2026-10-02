"""Minimal isolated executor service.

This process is intentionally dependency-light and is expected to run in a
read-only container with no public network, no host mounts, dropped Linux
capabilities, and strict CPU/memory limits (see docker-compose.prod.yml).
"""

from __future__ import annotations

import ast
import base64
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 25 * 1024 * 1024
MAX_OUTPUT = 200_000
MAX_INPUT_FILE_BYTES = 10 * 1024 * 1024
MAX_INPUT_FILES = 5
MAX_GENERATED_FILE_BYTES = 1 * 1024 * 1024
MAX_GENERATED_TOTAL_BYTES = 1_500_000
DENIED_IMPORTS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "ctypes",
    "multiprocessing",
    "pathlib",
    "shutil",
    "signal",
}


def _validate_python(code: str) -> None:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"syntax error: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
            if any(name in DENIED_IMPORTS for name in names):
                raise ValueError("imports that access the host or network are not allowed")


def _sql_script(query: str, tables: dict[str, object]) -> str:
    normalized = query.strip().lower()
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise ValueError("only read-only SELECT/WITH SQL is allowed")
    if any(
        token in normalized
        for token in (
            ";",
            "attach",
            "pragma",
            "vacuum",
            "insert",
            "update",
            "delete",
            "drop",
            "alter",
        )
    ):
        raise ValueError("only a single read-only SQL statement is allowed")
    encoded = json.dumps(tables, ensure_ascii=False)
    return (
        "import json,sqlite3\n"
        f"tables=json.loads({encoded!r})\n"
        "db=sqlite3.connect(':memory:')\n"
        "for name, rows in tables.items():\n"
        " rows = rows if isinstance(rows,list) else []\n"
        " if not rows: continue\n"
        " cols = list(rows[0].keys()) if isinstance(rows[0],dict) else []\n"
        " if not cols: continue\n"
        " db.execute('create table ' + ''.join(c for c in name if c.isalnum() or c=='_') + ' (' + ','.join(''.join(c for c in x if c.isalnum() or c=='_') + ' text' for x in cols) + ')')\n"
        " safe=''.join(c for c in name if c.isalnum() or c=='_')\n"
        " db.executemany('insert into '+safe+' values ('+','.join('?' for _ in cols)+')', [[r.get(c) for c in cols] for r in rows])\n"
        f"rows=db.execute({query.strip()!r}).fetchall()\n"
        "print(json.dumps(rows, ensure_ascii=False, default=str))\n"
    )


def _run(payload: dict[str, object]) -> dict[str, object]:
    language = str(payload.get("language") or "").lower()
    code = str(payload.get("code") or "")
    timeout = max(1, min(30, int(str(payload.get("timeout_seconds") or 20))))
    if language not in {"python", "sql"}:
        raise ValueError("unsupported language")
    if not code.strip() or len(code.encode()) > 100_000:
        raise ValueError("code is empty or exceeds the safety limit")
    raw_files = payload.get("files")
    if raw_files is not None and not isinstance(raw_files, list):
        raise ValueError("files must be an array")
    if len(raw_files or []) > MAX_INPUT_FILES:
        raise ValueError("too many input files")
    if language == "python":
        _validate_python(code)
        script = code
    else:
        tables = payload.get("input")
        script = _sql_script(code, tables if isinstance(tables, dict) else {})
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="averqel-sandbox-") as workdir:
        initial_files: set[str] = set()
        for item in raw_files or []:
            if not isinstance(item, dict):
                raise ValueError("invalid input file")
            raw_name = str(item.get("name") or "").strip()
            name = Path(raw_name).name
            if (
                not name
                or name in {".", ".."}
                or name != raw_name
                or "/" in raw_name
                or "\\" in raw_name
            ):
                raise ValueError("input file name must be a plain filename")
            encoded = item.get("data_base64")
            if not isinstance(encoded, str):
                raise ValueError("input file payload is invalid")
            try:
                file_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("input file payload is invalid") from exc
            if len(file_bytes) > MAX_INPUT_FILE_BYTES:
                raise ValueError("input file exceeds the 10 MB safety limit")
            Path(workdir, name).write_bytes(file_bytes)
            initial_files.add(name)
            extracted = str(item.get("extracted_text") or "")
            if extracted:
                Path(workdir, f"{name}.extracted.txt").write_text(
                    extracted[:200_000], encoding="utf-8"
                )
                initial_files.add(f"{name}.extracted.txt")
        env = {"PATH": "/usr/local/bin:/usr/bin", "HOME": workdir, "PYTHONNOUSERSITE": "1"}
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        generated: list[dict[str, object]] = []
        generated_total = 0
        for candidate in Path(workdir).rglob("*"):
            if not candidate.is_file() or candidate.name in initial_files:
                continue
            relative = candidate.relative_to(workdir).as_posix()
            if relative.startswith(".") or len(generated) >= 10:
                continue
            size = candidate.stat().st_size
            if size <= 0 or size > MAX_GENERATED_FILE_BYTES:
                continue
            if generated_total + size > MAX_GENERATED_TOTAL_BYTES:
                break
            generated.append(
                {
                    "name": relative[:255],
                    "content_type": mimetypes.guess_type(relative)[0] or "application/octet-stream",
                    "data_base64": base64.b64encode(candidate.read_bytes()).decode("ascii"),
                    "size_bytes": size,
                }
            )
            generated_total += size
        return {
            "status": "completed" if proc.returncode == 0 else "failed",
            "stdout": proc.stdout[:MAX_OUTPUT],
            "stderr": proc.stderr[:50_000],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "files": generated,
        }


class Handler(BaseHTTPRequestHandler):
    server_version = "AverQelSandbox/1.0"

    def _send(self, status: int, body: dict[str, object]) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        self._send(200 if self.path == "/health" else 404, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        expected = os.environ.get("SANDBOX_EXECUTOR_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if expected and supplied != f"Bearer {expected}":
            self._send(401, {"error": "unauthorized"})
            return
        if self.path != "/execute":
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("request body exceeds the safety limit")
            payload = json.loads(self.rfile.read(length))
            result = _run(payload if isinstance(payload, dict) else {})
            self._send(200, result)
        except subprocess.TimeoutExpired:
            self._send(
                408,
                {
                    "status": "timeout",
                    "stdout": "",
                    "stderr": "execution timed out",
                    "duration_ms": 0,
                    "files": [],
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._send(
                400,
                {
                    "status": "rejected",
                    "stdout": "",
                    "stderr": str(exc)[:1000],
                    "duration_ms": 0,
                    "files": [],
                },
            )

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3020"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
