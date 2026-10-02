"""Tenant-safe client for the isolated data/code executor.

The API never executes user code locally.  The executor is a separately
deployed, network-isolated service and this client applies a second policy
boundary before sending a request to it.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

SUPPORTED_LANGUAGES = {"python", "sql"}
MAX_CODE_BYTES = 100_000
MAX_INPUT_BYTES = 2_000_000
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILE_BUNDLE_BYTES = 20 * 1024 * 1024
MAX_GENERATED_FILE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SandboxResult:
    status: str
    language: str
    stdout: str
    stderr: str
    duration_ms: int
    files: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "language": self.language,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "files": self.files,
            "execution": "isolated_sandbox",
        }


class SandboxExecutorError(RuntimeError):
    """A safe, user-displayable execution error."""


async def execute_sandbox(
    *,
    code: str,
    language: str,
    settings: Any,
    input_data: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    normalized_language = language.strip().lower()
    if normalized_language not in SUPPORTED_LANGUAGES:
        raise SandboxExecutorError("Only Python and read-only SQL execution is supported.")
    if not isinstance(code, str) or not code.strip():
        raise SandboxExecutorError("Execution code is required.")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise SandboxExecutorError("Execution code exceeds the 100 KB safety limit.")
    payload = input_data if isinstance(input_data, dict) else {}
    if len(str(payload).encode("utf-8")) > MAX_INPUT_BYTES:
        raise SandboxExecutorError("Execution input exceeds the 2 MB safety limit.")
    safe_files: list[dict[str, Any]] = []
    bundle_bytes = 0
    for item in files or []:
        if not isinstance(item, dict):
            raise SandboxExecutorError("Sandbox file entries must be objects.")
        name = str(item.get("name") or "").strip()
        data = item.get("data_base64")
        if not name or not isinstance(data, str):
            raise SandboxExecutorError("Sandbox files require a name and binary payload.")
        try:
            decoded_size = len(base64.b64decode(data, validate=True))
        except (ValueError, TypeError) as exc:
            raise SandboxExecutorError("Sandbox file payload is invalid.") from exc
        if decoded_size > MAX_FILE_BYTES:
            raise SandboxExecutorError("A sandbox file exceeds the 10 MB safety limit.")
        bundle_bytes += decoded_size
        if bundle_bytes > MAX_FILE_BUNDLE_BYTES:
            raise SandboxExecutorError("Sandbox files exceed the 20 MB aggregate safety limit.")
        safe_files.append(
            {
                "name": name[:255],
                "content_type": str(item.get("content_type") or "application/octet-stream")[:127],
                "data_base64": data,
                "extracted_text": str(item.get("extracted_text") or "")[:200_000],
            }
        )
    if len(safe_files) > MAX_FILES:
        raise SandboxExecutorError(f"At most {MAX_FILES} Library files may be analyzed at once.")
    if not bool(getattr(settings, "deepspace_sandbox_enabled", False)):
        raise SandboxExecutorError("The isolated sandbox is not enabled on this deployment.")
    endpoint = str(getattr(settings, "deepspace_sandbox_url", "") or "").rstrip("/")
    if not endpoint:
        raise SandboxExecutorError("The isolated sandbox service is not configured.")
    token = str(getattr(settings, "deepspace_sandbox_token", "") or "")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = {
        "language": normalized_language,
        "code": code,
        "input": payload,
        "files": safe_files,
        "timeout_seconds": max(1, min(30, int(timeout_seconds))),
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(35.0, connect=3.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(f"{endpoint}/execute", json=request, headers=headers)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SandboxExecutorError("The isolated sandbox could not complete the request.") from exc
    if not isinstance(data, dict):
        raise SandboxExecutorError("The isolated sandbox returned an invalid response.")
    output_files: list[dict[str, Any]] = []
    output_total = 0
    raw_output_files = data.get("files")
    for item in raw_output_files if isinstance(raw_output_files, list) else []:
        if not hasattr(item, "get"):
            continue
        encoded = item.get("data_base64")
        if not isinstance(encoded, str):
            continue
        try:
            decoded_size = len(base64.b64decode(encoded, validate=True))
        except (ValueError, TypeError):
            continue
        if decoded_size <= 0 or decoded_size > MAX_GENERATED_FILE_BYTES:
            continue
        output_total += decoded_size
        if output_total > 1_500_000:
            break
        output_files.append(
            {
                "name": str(item.get("name") or "output")[:255],
                "content_type": str(item.get("content_type") or "text/plain")[:127],
                "data_base64": encoded,
                "size_bytes": decoded_size,
            }
        )
    return SandboxResult(
        status=str(data.get("status") or "failed"),
        language=normalized_language,
        stdout=str(data.get("stdout") or "")[:200_000],
        stderr=str(data.get("stderr") or "")[:50_000],
        duration_ms=max(0, int(data.get("duration_ms") or 0)),
        files=output_files[:10],
    ).as_dict()
