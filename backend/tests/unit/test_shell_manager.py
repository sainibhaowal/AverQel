from __future__ import annotations

import asyncio
from collections import deque

import pytest

from app.services.deepspace.workspace.shell_manager import ShellManager, ShellSession


class _FakeStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = deque(chunks)

    async def read(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.popleft()


class _FakeProcess:
    def __init__(
        self,
        stdout_chunks: list[bytes],
        stderr_chunks: list[bytes],
        returncode: int = 0,
    ) -> None:
        self.stdout = _FakeStream(stdout_chunks)
        self.stderr = _FakeStream(stderr_chunks)
        self.returncode = returncode
        self._killed = False

    async def wait(self) -> int:
        if not self._killed and self.returncode is None:
            await asyncio.sleep(0.5)
        return self.returncode

    def kill(self) -> None:
        self._killed = True
        self.returncode = -9


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_shell_session_uses_warm_docker_exec_and_persists_cwd(monkeypatch):
    session = ShellSession("tenant-a", "user-a")
    cwd_values = iter(["/workspace/project-a", "/workspace/project-a/src"])
    seen_commands: list[tuple[object, ...]] = []
    progress: list[dict[str, str]] = []
    ensure_calls = 0

    async def fake_ensure_container() -> None:
        nonlocal ensure_calls
        ensure_calls += 1

    async def fake_read_cwd_state(_state_file: str) -> str:
        return next(cwd_values)

    async def fake_create_subprocess_exec(*cmd, **kwargs):  # noqa: ANN001
        seen_commands.append(cmd)
        assert kwargs["stdout"] is not None
        assert kwargs["stderr"] is not None
        return _FakeProcess([b"hello from shell\n"], [b"warn\n"])

    async def sink(payload: dict[str, str]) -> None:
        progress.append(payload)

    monkeypatch.setattr(session, "_ensure_container", fake_ensure_container)
    monkeypatch.setattr(session, "_read_cwd_state", fake_read_cwd_state)
    monkeypatch.setattr(
        "app.services.deepspace.workspace.shell_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    first = await session.stream_execute("pwd", on_chunk=sink)
    second = await session.stream_execute("ls", on_chunk=sink)

    assert first.exit_code == 0
    assert "hello from shell" in first.output
    assert "[stderr] warn" in first.output
    assert second.exit_code == 0
    assert ensure_calls == 2
    assert seen_commands[0][:3] == ("docker", "exec", session.container_name)
    assert "cd /workspace && { pwd; };" in str(seen_commands[0][-1])
    assert "cd /workspace/project-a && { ls; };" in str(seen_commands[1][-1])
    assert session.cwd == "/workspace/project-a/src"
    assert [item["stream"] for item in progress] == [
        "stdout",
        "stderr",
        "stdout",
        "stderr",
    ]


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_shell_session_times_out_and_emits_timeout_chunk(monkeypatch):
    session = ShellSession("tenant-timeout", "user-timeout")
    progress: list[dict[str, str]] = []

    async def fake_ensure_container() -> None:
        return None

    async def fake_read_cwd_state(_state_file: str) -> str:
        return "/workspace"

    async def fake_create_subprocess_exec(*cmd, **kwargs):  # noqa: ANN001
        assert kwargs["stdout"] is not None
        assert kwargs["stderr"] is not None
        return _FakeProcess([], [], returncode=None)

    async def sink(payload: dict[str, str]) -> None:
        progress.append(payload)

    monkeypatch.setattr(session, "_ensure_container", fake_ensure_container)
    monkeypatch.setattr(session, "_read_cwd_state", fake_read_cwd_state)
    monkeypatch.setattr(
        "app.services.deepspace.workspace.shell_manager.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await session.stream_execute("sleep 5", timeout=1, on_chunk=sink)

    assert result.timed_out is True
    assert result.exit_code == 124
    assert "timed out" in result.output.lower()
    assert any(
        item["text"].lower().startswith("error: command timed out") for item in progress
    )


@pytest.mark.unit_no_db
def test_shell_manager_cleans_idle_sessions(monkeypatch):
    stale_session = ShellSession("tenant-stale", "user-stale")
    fresh_session = ShellSession("tenant-fresh", "user-fresh")
    killed: list[str] = []

    def fake_kill() -> None:
        killed.append(stale_session.id)

    monkeypatch.setattr(stale_session, "is_idle", lambda: True)
    monkeypatch.setattr(fresh_session, "is_idle", lambda: False)
    monkeypatch.setattr(stale_session, "kill", fake_kill)

    ShellManager._sessions = {
        "tenant-stale:user-stale:default": stale_session,
        "tenant-fresh:user-fresh:default": fresh_session,
    }

    retained = ShellManager.get_session("tenant-fresh", "user-fresh")

    assert retained is fresh_session
    assert killed == [stale_session.id]
    assert "tenant-stale:user-stale:default" not in ShellManager._sessions
    assert "tenant-fresh:user-fresh:default" in ShellManager._sessions
    ShellManager._sessions = {}
