import asyncio
import logging
import uuid
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.auth import AuthContext
from app.core.config import Settings
from app.services.deepspace.execution.agent_tools import ToolResult
from app.services.deepspace.missions.mission_registry import MissionRegistry
from app.services.deepspace.subagents.subagent_context_builder import build_subagent_context
from app.services.deepspace.subagents.subagent_profiles import resolve_subagent_profile
from app.services.deepspace.subagents.subagent_registry import (
    SubagentRegistry,
    SubagentRunControl,
)
from app.services.deepspace.subagents.subagent_result_normalizer import (
    SubagentResultAccumulator,
    normalize_subagent_result,
)

logger = logging.getLogger(__name__)


class _LocalSubagentRegistry:
    """In-process fallback when Redis-backed run state is unavailable."""

    _runs: dict[str, dict[str, object]] = {}
    _slots: dict[tuple[str, str, int], str] = {}

    def __init__(self, settings):
        self.settings = settings

    @property
    def max_concurrency(self) -> int:
        return max(
            1, int(getattr(self.settings, "deepspace_subagent_max_concurrency", 4))
        )

    def acquire_slot(self, *, tenant_id: str, user_id: str, run_id: str) -> int | None:
        for slot_index in range(1, self.max_concurrency + 1):
            key = (tenant_id, user_id, slot_index)
            if key in self._slots:
                continue
            self._slots[key] = run_id
            return slot_index
        return None

    def release_slot(
        self, *, tenant_id: str, user_id: str, slot_index: int, run_id: str
    ) -> None:
        key = (tenant_id, user_id, slot_index)
        if self._slots.get(key) == run_id:
            self._slots.pop(key, None)

    def register_run(self, **kwargs):
        run_id = str(kwargs["run_id"])
        payload = dict(kwargs)
        payload.setdefault("status", "running")
        payload.setdefault("slot_index", 0)
        payload.setdefault("last_event_type", "start")
        payload.setdefault("last_event_message", "Sub-agent registered.")
        payload.setdefault("summary", "")
        payload.setdefault("final_output", "")
        payload.setdefault("error", "")
        payload.setdefault("step_count", 0)
        payload.setdefault("duration_ms", 0)
        payload.setdefault("last_tool_name", "")
        payload.setdefault("last_tool_id", "")
        payload.setdefault("last_tool_output", "")
        payload.setdefault("heartbeat_at", "")
        self._runs[run_id] = payload
        return dict(payload)

    def touch_run(self, run_id: str, **updates: object) -> None:
        run = self._runs.get(run_id)
        if not run:
            return
        run.update(updates)

    def complete_run(
        self,
        *,
        run_id: str,
        status: str,
        summary: str | None = None,
        final_output: str | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ):  # noqa: E501
        run = self._runs.get(run_id)
        if not run:
            return None
        run.update(
            {
                "status": status,
                "summary": summary if summary is not None else run.get("summary", ""),
                "final_output": (
                    final_output
                    if final_output is not None
                    else run.get("final_output", "")
                ),
                "error": error if error is not None else run.get("error", ""),
                "duration_ms": (
                    duration_ms
                    if duration_ms is not None
                    else run.get("duration_ms", 0)
                ),
            }
        )
        return dict(run)

    def is_cancel_requested(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        return bool(run and run.get("cancel_requested"))

    def request_termination(self, run_id: str):
        run = self._runs.get(run_id)
        if not run:
            return None
        run["cancel_requested"] = 1
        run["status"] = "terminating"
        run["last_event_type"] = "termination_requested"
        run["last_event_message"] = "Termination requested."
        return dict(run)


class SubagentManager:
    """Orchestrates the spawning, execution, and summarization of specialized sub-agents."""

    DEFAULT_TIMEOUT_SECONDS = 300

    def __init__(self, db: Session, settings: Settings, auth: AuthContext):
        self.db = db
        self.settings = settings
        self.auth = auth
        self.registry = SubagentRegistry(settings)

    def _subagent_timeout_seconds(self) -> int:
        return max(
            30,
            int(
                getattr(
                    self.settings,
                    "deepspace_subagent_timeout_seconds",
                    self.DEFAULT_TIMEOUT_SECONDS,
                )
            ),
        )

    def _active_registry(self):
        if (
            hasattr(self.registry, "is_backend_available")
            and not self.registry.is_backend_available()
        ):
            logger.warning(
                "Sub-agent registry backend unavailable; using local fallback registry."
            )
            return _LocalSubagentRegistry(self.settings)
        return self.registry

    async def spawn_and_execute(
        self,
        stype: str,
        prompt: str,
        parent_id: uuid.UUID,
        execution_mode: str = "auto_review",
        conversation_id: uuid.UUID | None = None,
    ) -> ToolResult:
        prompt = str(prompt or "").strip()
        if not prompt:
            return ToolResult(
                success=False,
                output="REJECTION: A sub-agent mission prompt is required.",
            )
        requested_stype = str(stype or "").strip() or "general-purpose"
        resolved_stype = self._resolve_requested_subagent_type(
            requested_stype,
            conversation_id=conversation_id,
        )

        run_id = str(uuid.uuid4())
        registry = self._active_registry()
        slot_index = registry.acquire_slot(
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            run_id=run_id,
        )
        if slot_index is None:
            backend_unavailable = False
            if registry is self.registry and hasattr(
                self.registry, "is_backend_available"
            ):
                try:
                    backend_unavailable = not self.registry.is_backend_available()
                except Exception:
                    backend_unavailable = True
            if registry is self.registry and (
                backend_unavailable
                or (
                    hasattr(self.registry, "consume_backend_error")
                    and self.registry.consume_backend_error()
                )
            ):
                registry = _LocalSubagentRegistry(self.settings)
                slot_index = registry.acquire_slot(
                    tenant_id=str(self.auth.tenant_id),
                    user_id=str(self.auth.user_id),
                    run_id=run_id,
                )
            if slot_index is None:
                return ToolResult(
                    success=False,
                    output=(
                        "REJECTION: All sub-agent lanes are busy. "
                        "Wait for a running mission to complete or terminate one from the monitor."
                    ),
                )

        if registry is not self.registry:
            logger.info(
                "Sub-agent run %s started in degraded local-registry mode.", run_id
            )

        registry.register_run(
            run_id=run_id,
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            subagent_type=resolved_stype,
            prompt=prompt,
            parent_id=str(parent_id),
            slot_index=slot_index,
            status="running",
        )
        control = SubagentRunControl(registry=registry, run_id=run_id)
        try:
            start = perf_counter()
            try:
                if control.is_cancelled():
                    registry.complete_run(
                        run_id=run_id,
                        status="cancelled",
                        summary="Sub-agent cancelled before execution.",
                        final_output="Sub-agent cancelled before execution.",
                    )
                    return ToolResult(success=False, output="Sub-agent cancelled.")
                result = await self._run_subagent_loop(
                    requested_stype=requested_stype,
                    resolved_stype=resolved_stype,
                    prompt=prompt,
                    parent_id=parent_id,
                    run_id=run_id,
                    control=control,
                    execution_mode=execution_mode,
                )
                status = (
                    "cancelled"
                    if control.is_cancelled()
                    or "cancelled" in str(result.output).lower()
                    else ("completed" if result.success else "failed")
                )
                if status == "cancelled":
                    result = ToolResult(success=False, output="Sub-agent cancelled.")
                registry.complete_run(
                    run_id=run_id,
                    status=status,
                    summary=result.output[:4000],
                    final_output=result.output[:8000],
                    duration_ms=int((perf_counter() - start) * 1000),
                )
                return result
            except TimeoutError as exc:
                registry.complete_run(
                    run_id=run_id,
                    status="failed",
                    summary=str(exc)[:4000],
                    final_output=str(exc)[:8000],
                    error=str(exc)[:4000],
                    duration_ms=int((perf_counter() - start) * 1000),
                )
                return ToolResult(success=False, output=str(exc))
            except Exception as e:
                if control.is_cancelled():
                    registry.complete_run(
                        run_id=run_id,
                        status="cancelled",
                        summary="Sub-agent cancelled during retry handling.",
                        final_output="Sub-agent cancelled during retry handling.",
                        duration_ms=int((perf_counter() - start) * 1000),
                    )
                    return ToolResult(success=False, output="Sub-agent cancelled.")
                logger.warning(
                    f"Subagent {stype} failed, retrying once... Error: {str(e)}"
                )
                result = await self._run_subagent_loop(
                    requested_stype=requested_stype,
                    resolved_stype=resolved_stype,
                    prompt=prompt,
                    parent_id=parent_id,
                    run_id=run_id,
                    control=control,
                    execution_mode=execution_mode,
                )
                status = (
                    "cancelled"
                    if control.is_cancelled()
                    or "cancelled" in str(result.output).lower()
                    else ("completed" if result.success else "failed")
                )
                if status == "cancelled":
                    result = ToolResult(success=False, output="Sub-agent cancelled.")
                registry.complete_run(
                    run_id=run_id,
                    status=status,
                    summary=result.output[:4000],
                    final_output=result.output[:8000],
                    duration_ms=int((perf_counter() - start) * 1000),
                )
                return result
        except asyncio.CancelledError:
            registry.complete_run(
                run_id=run_id,
                status="cancelled",
                summary="Sub-agent cancelled.",
                final_output="Sub-agent cancelled.",
            )
            return ToolResult(success=False, output="Sub-agent cancelled.")
        except Exception as exc:
            registry.complete_run(
                run_id=run_id,
                status="failed",
                summary=str(exc)[:4000],
                error=str(exc)[:4000],
            )
            raise
        finally:
            registry.release_slot(
                tenant_id=str(self.auth.tenant_id),
                user_id=str(self.auth.user_id),
                slot_index=slot_index,
                run_id=run_id,
            )

    async def _run_subagent_loop(
        self,
        *,
        requested_stype: str,
        resolved_stype: str,
        prompt: str,
        parent_id: uuid.UUID,
        run_id: str,
        control: SubagentRunControl,
        execution_mode: str,
    ) -> ToolResult:
        """Isolated subagent loop with restricted tools."""
        from app.services.deepspace.execution.agent_executor import AgentExecutor

        profile = resolve_subagent_profile(resolved_stype)
        execution_context = build_subagent_context(
            profile=profile,
            prompt=prompt,
            execution_mode=execution_mode,
            parent_id=parent_id,
        )

        subagent_executor = AgentExecutor(
            self.db,
            self.auth,
            settings=self.settings,
            restricted_tools=list(profile.allowed_tools),
            run_control=control,
            execution_mode=execution_mode,
        )

        try:
            sub_conv_id = uuid.uuid4()

            async def _consume_subagent_stream() -> ToolResult:
                accumulator = SubagentResultAccumulator()
                async for event in subagent_executor.stream_agent_loop(
                    conversation_id=sub_conv_id,
                    user_message=execution_context.user_message,
                    thinking_enabled=execution_context.thinking_enabled,
                    web_search_enabled=execution_context.web_search_enabled,
                    is_subagent=True,
                ):
                    if control.is_cancelled():
                        control.heartbeat(
                            status="cancelled",
                            last_event_type="cancelled",
                            last_event_message="Cancellation requested.",
                        )
                        return ToolResult(success=False, output="Sub-agent cancelled.")
                    control.heartbeat(
                        last_event_type=event.type,
                        last_event_message=(
                            str(
                                event.data.get("message")
                                or event.data.get("text")
                                or event.data.get("output")
                                or ""
                            )
                        )[:1000],
                        last_tool_name=str(event.data.get("tool_name") or ""),
                        last_tool_id=str(event.data.get("tool_id") or ""),
                    )
                    accumulator.record_event(event.type, event.data)

                normalized_output, result_data = normalize_subagent_result(
                    profile=profile,
                    accumulator=accumulator,
                    prompt=prompt,
                    sub_conversation_id=sub_conv_id,
                    run_id=run_id,
                    parent_id=parent_id,
                )

                return ToolResult(
                    success=True,
                    output=normalized_output,
                    data={
                        **dict(result_data or {}),
                        "requested_subagent_type": requested_stype,
                        "resolved_subagent_type": resolved_stype,
                    },
                )

            timeout_seconds = self._subagent_timeout_seconds()
            try:
                return await asyncio.wait_for(
                    _consume_subagent_stream(),
                    timeout=float(timeout_seconds),
                )
            except TimeoutError:
                control.heartbeat(
                    status="failed",
                    last_event_type="timeout",
                    last_event_message=f"Sub-agent timed out after {timeout_seconds} seconds.",
                )
                raise TimeoutError(
                    f"Sub-agent timed out after {timeout_seconds} seconds."
                ) from None

        except Exception as e:
            raise e from None

    def _resolve_requested_subagent_type(
        self,
        requested_stype: str,
        *,
        conversation_id: uuid.UUID | None = None,
    ) -> str:
        normalized = str(requested_stype or "").strip() or "general-purpose"
        if normalized not in {"general", "general-purpose", "default", "assistant"}:
            return normalized
        if not bool(
            getattr(self.settings, "deepspace_subagent_profiles_rollout_enabled", True)
        ):
            return normalized
        preferred = MissionRegistry(self.settings, db=self.db).get_subagent_profile(
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            conversation_id=str(conversation_id) if conversation_id else None,
        )
        if preferred and preferred not in {"default", normalized}:
            return preferred
        return normalized
