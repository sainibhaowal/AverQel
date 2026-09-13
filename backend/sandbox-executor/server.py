"""Minimal isolated executor service.

This process is intentionally dependency-light and is expected to run in a
read-only container with no public network, no host mounts, dropped Linux
capabilities, and strict CPU/memory limits (see docker-compose.prod.yml).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 2_500_000
MAX_OUTPUT = 200_000
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
    if language == "python":
        _validate_python(code)
        script = code
    else:
        tables = payload.get("input")
        script = _sql_script(code, tables if isinstance(tables, dict) else {})
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="averqel-sandbox-") as workdir:
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
        return {
            "status": "completed" if proc.returncode == 0 else "failed",
            "stdout": proc.stdout[:MAX_OUTPUT],
            "stderr": proc.stderr[:50_000],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "files": [],
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
