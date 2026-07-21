from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ShellExecutionResult:
    output: str
    exit_code: int
    timed_out: bool = False


class ShellSession:
    IDLE_TTL_SECONDS = 15 * 60

    def __init__(self, tenant_id: str, user_id: str, workspace_path: str | None = None):
        self.id = uuid.uuid4().hex
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.workspace_path = workspace_path or os.getcwd()
        if os.environ.get("AKS_DISABLE_SANDBOX") == "true":
            self.cwd = self.workspace_path
        else:
            self.cwd = "/workspace"
        self.process = None
        self.container_name = f"deepspace-shell-{self.id[:12]}"
        self._pending_output: list[str] = []
        self._lock = asyncio.Lock()
        self._last_used_at = time.monotonic()
        self._container_ready = False
        self.active_venv = None
        self.listeners: set[Callable[[dict[str, str]], Awaitable[None]]] = set()
    async def _broadcast_chunk(self, stream_name: str, text: str, on_chunk: Callable[[dict[str, str]], Awaitable[None]] | None) -> None:
        payload = {
            "bash_id": self.id,
            "stream": stream_name,
            "text": text,
        }
        if on_chunk is not None:
            try:
                await on_chunk(payload)
            except Exception:
                pass
        listeners = getattr(self, "listeners", None)
        if listeners:
            for listener in list(listeners):
                try:
                    await listener(payload)
                except Exception:
                    pass


    async def execute(self, command: str, timeout: int = 120000) -> str:
        result = await self.stream_execute(command, timeout=timeout)
        return result.output

    async def stream_execute(
        self,
        command: str,
        timeout: int = 120000,
        on_chunk: Callable[[dict[str, str]], Awaitable[None]] | None = None,
    ) -> ShellExecutionResult:
        async with self._lock:
            return await self._stream_execute_locked(
                command,
                timeout=timeout,
                on_chunk=on_chunk,
            )

    async def _stream_execute_proxy(
        self,
        command: str,
        *,
        timeout: int,
        on_chunk: Callable[[dict[str, str]], Awaitable[None]] | None,
    ) -> ShellExecutionResult:
        from app.deepspace.integrations.client_proxy import client_proxy_registry
        start_msg = f"[Proxy executing on user PC]: {command}\n"
        await self._broadcast_chunk("stdout", start_msg, on_chunk)
        
        try:
            result_payload = await client_proxy_registry.send_and_await_rpc(
                self.tenant_id,
                self.user_id,
                "shell.execute",
                {"command": command, "cwd": self.cwd, "timeout": timeout},
                timeout=max(float(timeout) / 1000.0 + 5.0, 10.0)
            )
            
            output = result_payload.get("output", "")
            exit_code = int(result_payload.get("exit_code", 0))
            new_cwd = result_payload.get("cwd")
            if new_cwd:
                self.cwd = new_cwd
            
            if output:
                await self._broadcast_chunk("stdout", output, on_chunk)
                
            return ShellExecutionResult(output=output, exit_code=exit_code)
        except Exception as e:
            error_text = f"Proxy Execution Error: {str(e)}"
            await self._broadcast_chunk("stderr", error_text, on_chunk)
            return ShellExecutionResult(output=error_text, exit_code=1)

    async def _stream_execute_locked(
        self,
        command: str,
        *,
        timeout: int,
        on_chunk: Callable[[dict[str, str]], Awaitable[None]] | None,
    ) -> ShellExecutionResult:
        from app.deepspace.integrations.client_proxy import client_proxy_registry
        if client_proxy_registry.is_client_connected(self.tenant_id, self.user_id):
            return await self._stream_execute_proxy(
                command,
                timeout=timeout,
                on_chunk=on_chunk,
            )

        import re
        # Detect virtual env activation
        activate_match = re.search(r'(?:source|\.)\s+(\S+)/bin/activate', command)
        if activate_match:
            path_str = activate_match.group(1)
            self.active_venv = os.path.basename(path_str)
        elif command.strip() == "deactivate":
            self.active_venv = None
        if os.environ.get("AKS_DISABLE_SANDBOX") == "true":
            return await self._stream_execute_host(
                command,
                timeout=timeout,
                on_chunk=on_chunk,
            )

        state_file = f"/tmp/deepspace-cwd-{self.id}"
        safe_cmd = self._wrap_command(command, state_file)
        stdout_task: asyncio.Task[None] | None = None
        stderr_task: asyncio.Task[None] | None = None

        try:
            await self._ensure_container()
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "exec",
                self.container_name,
                "bash",
                "-c",
                safe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.process = proc
            self._pending_output = []
            queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

            async def pump(stream: asyncio.StreamReader | None, label: str) -> None:
                if stream is None:
                    await queue.put((label, None))
                    return
                while True:
                    chunk = await stream.read(1024)
                    if not chunk:
                        break
                    await queue.put((label, chunk.decode(errors="replace")))
                await queue.put((label, None))

            try:
                stdout_task = asyncio.create_task(pump(proc.stdout, "stdout"))
                stderr_task = asyncio.create_task(pump(proc.stderr, "stderr"))
                timeout_seconds = max(float(timeout) / 1000.0, 0.1)
                deadline = asyncio.get_running_loop().time() + timeout_seconds
                completed_streams = 0

                while completed_streams < 2:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    stream_name, text = await asyncio.wait_for(
                        queue.get(), timeout=remaining
                    )
                    if text is None:
                        completed_streams += 1
                        continue
                    formatted = self._format_chunk(stream_name, text)
                    self._pending_output.append(formatted)
                    await self._broadcast_chunk(stream_name, formatted, on_chunk)

                exit_code = await asyncio.wait_for(
                    proc.wait(),
                    timeout=max(deadline - asyncio.get_running_loop().time(), 0.1),
                )
                await asyncio.gather(stdout_task, stderr_task)
                self.cwd = await self._read_cwd_state(state_file)
                self._last_used_at = time.monotonic()
                output = "".join(self._pending_output).strip() or "[Finished]"
                return ShellExecutionResult(output=output, exit_code=exit_code)
            except TimeoutError:
                proc.kill()
                with suppress(Exception):
                    await proc.wait()
                timeout_text = (
                    "Error: Command timed out. Docker sandbox command terminated."
                )
                self._pending_output.append(timeout_text)
                await self._broadcast_chunk("stderr", timeout_text, on_chunk)
                return ShellExecutionResult(
                    output=timeout_text, exit_code=124, timed_out=True
                )
            finally:
                for task in (stdout_task, stderr_task):
                    if task is not None:
                        task.cancel()
                await asyncio.gather(
                    *(task for task in (stdout_task, stderr_task) if task is not None),
                    return_exceptions=True,
                )
        except Exception as e:
            self._container_ready = False
            error_text = f"Sandbox Error: {str(e)}"
            self._pending_output.append(error_text)
            await self._broadcast_chunk("stderr", error_text, on_chunk)
            return ShellExecutionResult(output=error_text, exit_code=1)
        finally:
            self.process = None

    async def _stream_execute_host(
        self,
        command: str,
        *,
        timeout: int,
        on_chunk: Callable[[dict[str, str]], Awaitable[None]] | None,
    ) -> ShellExecutionResult:
        cwd = self.workspace_path
        if self.cwd and self.cwd != "/workspace":
            cwd = self.cwd
            
        if not os.path.exists(cwd):
            cwd = self.workspace_path

        state_file = f"/tmp/deepspace-host-cwd-{self.id}"
        venv_prefix = ""
        if hasattr(self, "active_venv") and self.active_venv:
            venv_path = os.path.join(self.workspace_path, self.active_venv)
            if not os.path.exists(venv_path):
                venv_path = os.path.join(cwd, self.active_venv)
            activate_script = os.path.join(venv_path, "bin/activate")
            venv_prefix = f"source {shlex.quote(activate_script)} && "
        safe_cmd = f"{venv_prefix}{command}; status=$?; pwd > {state_file}; exit $status"
        stdout_task: asyncio.Task[None] | None = None
        stderr_task: asyncio.Task[None] | None = None

        try:
            proc = await asyncio.create_subprocess_exec(
                "bash",
                "-c",
                safe_cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.process = proc
            self._pending_output = []
            queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

            async def pump(stream: asyncio.StreamReader | None, label: str) -> None:
                if stream is None:
                    await queue.put((label, None))
                    return
                while True:
                    chunk = await stream.read(1024)
                    if not chunk:
                        break
                    await queue.put((label, chunk.decode(errors="replace")))
                await queue.put((label, None))

            try:
                stdout_task = asyncio.create_task(pump(proc.stdout, "stdout"))
                stderr_task = asyncio.create_task(pump(proc.stderr, "stderr"))
                timeout_seconds = max(float(timeout) / 1000.0, 0.1)
                deadline = asyncio.get_running_loop().time() + timeout_seconds
                completed_streams = 0

                while completed_streams < 2:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    stream_name, text = await asyncio.wait_for(
                        queue.get(), timeout=remaining
                    )
                    if text is None:
                        completed_streams += 1
                        continue
                    formatted = self._format_chunk(stream_name, text)
                    self._pending_output.append(formatted)
                    await self._broadcast_chunk(stream_name, formatted, on_chunk)

                exit_code = await asyncio.wait_for(
                    proc.wait(),
                    timeout=max(deadline - asyncio.get_running_loop().time(), 0.1),
                )
                await asyncio.gather(stdout_task, stderr_task)
                
                if os.path.exists(state_file):
                    try:
                        with open(state_file) as f:
                            new_cwd = f.read().strip()
                            if new_cwd and os.path.exists(new_cwd):
                                self.cwd = new_cwd
                        os.unlink(state_file)
                    except Exception:
                        pass
                        
                self._last_used_at = time.monotonic()
                output = "".join(self._pending_output).strip() or "[Finished]"
                return ShellExecutionResult(output=output, exit_code=exit_code)
            except TimeoutError:
                proc.kill()
                with suppress(Exception):
                    await proc.wait()
                timeout_text = "Error: Command timed out."
                self._pending_output.append(timeout_text)
                await self._broadcast_chunk("stderr", timeout_text, on_chunk)
                return ShellExecutionResult(
                    output=timeout_text, exit_code=124, timed_out=True
                )
            finally:
                for task in (stdout_task, stderr_task):
                    if task is not None:
                        task.cancel()
                await asyncio.gather(
                    *(task for task in (stdout_task, stderr_task) if task is not None),
                    return_exceptions=True,
                )
        except Exception as e:
            error_text = f"Host Execution Error: {str(e)}"
            self._pending_output.append(error_text)
            await self._broadcast_chunk("stderr", error_text, on_chunk)
            return ShellExecutionResult(output=error_text, exit_code=1)
        finally:
            self.process = None

    async def get_new_output(self) -> str:
        output = "".join(self._pending_output)
        self._pending_output = []
        return output

    def kill(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.kill()
        if self.container_name:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self.container_name],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._container_ready = False
            except Exception:  # noqa: BLE001
                logger.debug("Failed to stop shell container.", exc_info=True)

    @staticmethod
    def _format_chunk(stream_name: str, text: str) -> str:
        if stream_name == "stderr":
            return f"[stderr] {text}"
        return text

    def is_idle(self) -> bool:
        return (time.monotonic() - self._last_used_at) >= self.IDLE_TTL_SECONDS

    def _wrap_command(self, command: str, state_file: str) -> str:
        quoted_state = shlex.quote(state_file)
        quoted_cwd = shlex.quote(self.cwd or "/workspace")
        
        venv_prefix = ""
        if hasattr(self, "active_venv") and self.active_venv:
            venv_path = os.path.join(self.workspace_path, self.active_venv)
            if not os.path.exists(venv_path):
                venv_path = os.path.join(self.cwd, self.active_venv)
            activate_script = os.path.join(venv_path, "bin/activate")
            venv_prefix = f"source {shlex.quote(activate_script)} && "

        return (
            f"cd {quoted_cwd} && {venv_prefix}{{ {command}; }}; "
            "status=$?; "
            f"pwd > {quoted_state}; "
            "exit $status"
        )

    async def _ensure_container(self) -> None:
        if self._container_ready:
            return

        inspect_proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            self.container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        inspect_stdout, _ = await inspect_proc.communicate()
        if inspect_proc.returncode == 0 and inspect_stdout.decode().strip() == "true":
            self._container_ready = True
            return

        engine = os.environ.get("DEEPSPACE_SANDBOX_ENGINE", "standard").strip().lower()
        docker_run_args = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            self.container_name,
        ]

        if engine == "dind":
            docker_run_args.extend([
                "--privileged",
                "-v", "/var/run/docker.sock:/var/run/docker.sock",
                "--network", "bridge",
            ])
        else:
            docker_run_args.extend([
                "--network", "none",
                "--security-opt", "no-new-privileges",
            ])

        docker_run_args.extend([
            "--memory", "512m",
            "--cpus", "1.0",
            "-v", f"{self.workspace_path}:/workspace",
            "-w", "/workspace",
            "averqel-executor:latest",
            "tail",
            "-f",
            "/dev/null",
        ])

        run_proc = await asyncio.create_subprocess_exec(
            *docker_run_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await run_proc.communicate()
        if run_proc.returncode != 0:
            error_text = (
                stderr.decode(errors="replace").strip()
                or stdout.decode(errors="replace").strip()
            )
            raise RuntimeError(
                f"Unable to start sandbox container '{self.container_name}': {error_text}"
            )
        self._container_ready = True

    async def _read_cwd_state(self, state_file: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            self.container_name,
            "cat",
            state_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        cwd = stdout.decode(errors="replace").strip()
        return cwd or self.cwd or "/workspace"


class ShellManager:
    _sessions: dict[str, ShellSession] = {}

    @classmethod
    def get_session(
        cls, tenant_id: str, user_id: str, workspace_path: str | None = None, session_id: str | None = None
    ) -> ShellSession:
        cls._cleanup_idle_sessions()
        key = f"{tenant_id}:{user_id}:{session_id or 'default'}"
        if key not in cls._sessions:
            cls._sessions[key] = ShellSession(
                tenant_id, user_id, workspace_path=workspace_path
            )
        return cls._sessions[key]

    @classmethod
    def get_session_by_id(cls, shell_id: str | None) -> ShellSession | None:
        if not shell_id:
            return None
        for session in cls._sessions.values():
            if session.id == shell_id:
                return session
        return None

    @classmethod
    def kill_session(cls, shell_id: str | None) -> None:
        session = cls.get_session_by_id(shell_id)
        if not session:
            return
        session.kill()
        cls._sessions = {
            key: existing
            for key, existing in cls._sessions.items()
            if existing.id != session.id
        }

    @classmethod
    def _cleanup_idle_sessions(cls) -> None:
        stale_session_ids = [
            session.id for session in cls._sessions.values() if session.is_idle()
        ]
        for shell_id in stale_session_ids:
            cls.kill_session(shell_id)
