from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.core.config import Settings, get_settings
from app.services.system.cache_service import get_redis_client
from app.services.system.metrics_service import increment_subagent_stale_slot_reaped

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_str(value: Any) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("utf-8", errors="ignore")
    return str(value or "")


@dataclass(slots=True)
class SubagentRunControl:
    registry: SubagentRegistry
    run_id: str

    def is_cancelled(self) -> bool:
        return self.registry.is_cancel_requested(self.run_id)

    def heartbeat(self, **updates: Any) -> None:
        self.registry.touch_run(self.run_id, **updates)


class SubagentRegistry:
    """Redis-backed registry for active and historical sub-agent runs."""

    RUN_KEY_PREFIX = "averqel:subagents:run"
    INDEX_KEY_PREFIX = "averqel:subagents:index"
    SLOT_KEY_PREFIX = "averqel:subagents:slot"
    CANCEL_KEY_PREFIX = "averqel:subagents:cancel"
    HEARTBEAT_KEY = "averqel:daemon:heartbeat"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.redis = get_redis_client()
        self._backend_error = False

    def _mark_backend_error(self) -> None:
        self._backend_error = True

    def consume_backend_error(self) -> bool:
        had_error = self._backend_error
        self._backend_error = False
        return had_error

    def is_backend_available(self) -> bool:
        try:
            ping = getattr(self.redis, "ping", None)
            if callable(ping):
                return bool(ping())
            self.redis.exists(self.HEARTBEAT_KEY)
            return True
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Sub-agent registry backend probe failed.", exc_info=True)
            return False

    @property
    def max_concurrency(self) -> int:
        return max(
            1, int(getattr(self.settings, "deepspace_subagent_max_concurrency", 4))
        )

    @property
    def run_ttl_seconds(self) -> int:
        return max(
            300,
            int(getattr(self.settings, "deepspace_subagent_run_ttl_seconds", 86400)),
        )

    @property
    def lock_ttl_seconds(self) -> int:
        return max(
            60,
            int(getattr(self.settings, "deepspace_subagent_lock_ttl_seconds", 7200)),
        )

    @property
    def daemon_interval_seconds(self) -> int:
        return max(
            30,
            int(
                getattr(
                    self.settings, "deepspace_proactive_daemon_interval_seconds", 300
                )
            ),
        )

    @property
    def stale_heartbeat_seconds(self) -> int:
        return max(
            60,
            int(
                getattr(
                    self.settings, "deepspace_subagent_stale_heartbeat_seconds", 900
                )
            ),
        )

    def _run_key(self, run_id: str) -> str:
        return f"{self.RUN_KEY_PREFIX}:{run_id}"

    def _index_key(self, tenant_id: str, user_id: str) -> str:
        return f"{self.INDEX_KEY_PREFIX}:{tenant_id}:{user_id}"

    def _slot_key(self, tenant_id: str, user_id: str, slot_index: int) -> str:
        return f"{self.SLOT_KEY_PREFIX}:{tenant_id}:{user_id}:{slot_index}"

    def _cancel_key(self, run_id: str) -> str:
        return f"{self.CANCEL_KEY_PREFIX}:{run_id}"

    @staticmethod
    def _parse_iso_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _run_is_stale(self, run: dict[str, Any] | None) -> bool:
        if not run:
            return True
        last_seen = self._parse_iso_datetime(
            run.get("heartbeat_at") or run.get("updated_at") or run.get("started_at")
        )
        if last_seen is None:
            return True
        return datetime.now(tz=UTC) - last_seen > timedelta(
            seconds=self.stale_heartbeat_seconds
        )

    def _reap_stale_slot(
        self,
        *,
        tenant_id: str,
        user_id: str,
        slot_index: int,
        run_id: str,
    ) -> bool:
        run = self.get_run(run_id)
        if not self._run_is_stale(run):
            return False

        try:
            if run is not None:
                self.touch_run(
                    run_id,
                    status="stale",
                    last_event_type="stale_reaped",
                    last_event_message="Stale sub-agent slot reclaimed.",
                )
            self.release_slot(
                tenant_id=tenant_id,
                user_id=user_id,
                slot_index=slot_index,
                run_id=run_id,
            )
            increment_subagent_stale_slot_reaped()
            try:
                self.redis.delete(self._cancel_key(run_id))
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Failed to clear stale sub-agent cancellation key.", exc_info=True
                )
            return True
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to reap stale sub-agent slot.", exc_info=True)
            return False

    def _write_run_payload(self, run_id: str, payload: dict[str, Any]) -> None:
        key = self._run_key(run_id)
        mapping = {
            k: json.dumps(v) if isinstance(v, dict | list) else str(v)
            for k, v in payload.items()
        }
        try:
            self.redis.hset(
                key,
                mapping=cast("dict[str | bytes, bytes | float | int | str]", mapping),
            )
            self.redis.expire(key, self.run_ttl_seconds)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to persist sub-agent run payload.", exc_info=True)

    def acquire_slot(self, *, tenant_id: str, user_id: str, run_id: str) -> int | None:
        ttl = self.lock_ttl_seconds
        for slot_index in range(1, self.max_concurrency + 1):
            key = self._slot_key(tenant_id, user_id, slot_index)
            try:
                if self.redis.set(key, run_id, nx=True, ex=ttl):
                    return slot_index
                current_run_id = _to_str(self.redis.get(key))
                if current_run_id and self._reap_stale_slot(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    slot_index=slot_index,
                    run_id=current_run_id,
                ):
                    if self.redis.set(key, run_id, nx=True, ex=ttl):
                        return slot_index
            except Exception:  # noqa: BLE001
                self._mark_backend_error()
                logger.debug("Failed to acquire sub-agent slot.", exc_info=True)
                return None
        return None

    def release_slot(
        self, *, tenant_id: str, user_id: str, slot_index: int, run_id: str
    ) -> None:
        key = self._slot_key(tenant_id, user_id, slot_index)
        try:
            current = _to_str(self.redis.get(key))
            if current == run_id:
                self.redis.delete(key)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to release sub-agent slot.", exc_info=True)

    def register_run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        subagent_type: str,
        prompt: str,
        parent_id: str | None,
        slot_index: int | None,
        status: str = "running",
    ) -> dict[str, Any]:
        now = _now_iso()
        payload = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "parent_id": parent_id or "",
            "subagent_type": subagent_type,
            "prompt": prompt,
            "status": status,
            "slot_index": slot_index or 0,
            "created_at": now,
            "started_at": now,
            "updated_at": now,
            "completed_at": "",
            "cancel_requested": 0,
            "last_event_type": "start",
            "last_event_message": "Sub-agent registered.",
            "summary": "",
            "final_output": "",
            "error": "",
            "step_count": 0,
            "duration_ms": 0,
            "last_tool_name": "",
            "last_tool_id": "",
            "last_tool_output": "",
            "heartbeat_at": now,
        }
        self._write_run_payload(run_id, payload)
        try:
            self.redis.zadd(self._index_key(tenant_id, user_id), {run_id: time.time()})
            self.redis.expire(self._index_key(tenant_id, user_id), self.run_ttl_seconds)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to index sub-agent run.", exc_info=True)
        return self.get_run(run_id) or payload

    def touch_run(self, run_id: str, **updates: Any) -> None:
        payload: dict[str, Any] = {"updated_at": _now_iso(), "heartbeat_at": _now_iso()}
        if "status" in updates and updates["status"] is not None:
            payload["status"] = updates["status"]
        if "last_event_type" in updates and updates["last_event_type"] is not None:
            payload["last_event_type"] = updates["last_event_type"]
        if (
            "last_event_message" in updates
            and updates["last_event_message"] is not None
        ):
            payload["last_event_message"] = updates["last_event_message"]
        if "summary" in updates and updates["summary"] is not None:
            payload["summary"] = updates["summary"]
        if "final_output" in updates and updates["final_output"] is not None:
            payload["final_output"] = updates["final_output"]
        if "error" in updates and updates["error"] is not None:
            payload["error"] = updates["error"]
        if "step_count" in updates and updates["step_count"] is not None:
            payload["step_count"] = updates["step_count"]
        if "duration_ms" in updates and updates["duration_ms"] is not None:
            payload["duration_ms"] = updates["duration_ms"]
        if "last_tool_name" in updates and updates["last_tool_name"] is not None:
            payload["last_tool_name"] = updates["last_tool_name"]
        if "last_tool_id" in updates and updates["last_tool_id"] is not None:
            payload["last_tool_id"] = updates["last_tool_id"]
        if "last_tool_output" in updates and updates["last_tool_output"] is not None:
            payload["last_tool_output"] = updates["last_tool_output"]
        if "prompt" in updates and updates["prompt"] is not None:
            payload["prompt"] = updates["prompt"]
        if "parent_id" in updates and updates["parent_id"] is not None:
            payload["parent_id"] = updates["parent_id"]
        if "slot_index" in updates and updates["slot_index"] is not None:
            payload["slot_index"] = updates["slot_index"]
        if "cancel_requested" in updates and updates["cancel_requested"] is not None:
            payload["cancel_requested"] = 1 if updates["cancel_requested"] else 0

        try:
            existing = self.get_run(run_id)
            if existing:
                tenant_id = str(existing.get("tenant_id") or "")
                user_id = str(existing.get("user_id") or "")
                if tenant_id and user_id:
                    self.redis.zadd(
                        self._index_key(tenant_id, user_id), {run_id: time.time()}
                    )
            self._write_run_payload(run_id, payload)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to touch sub-agent run.", exc_info=True)

    def request_termination(self, run_id: str) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if not run:
            return None
        try:
            self.redis.set(self._cancel_key(run_id), "1", ex=self.run_ttl_seconds)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug(
                "Failed to persist sub-agent cancellation request.", exc_info=True
            )
        self.touch_run(
            run_id,
            status="terminating",
            cancel_requested=True,
            last_event_type="termination_requested",
            last_event_message="Termination requested.",
        )
        refreshed = self.get_run(run_id)
        return refreshed or run

    def is_cancel_requested(self, run_id: str) -> bool:
        try:
            return bool(self.redis.exists(self._cancel_key(run_id)))
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to read sub-agent cancellation state.", exc_info=True)
            return False

    def complete_run(
        self,
        *,
        run_id: str,
        status: str,
        summary: str | None = None,
        final_output: str | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if not run:
            return None
        now = _now_iso()
        slot_index = _to_int(run.get("slot_index"), 0)
        payload: dict[str, Any] = {
            "status": status,
            "updated_at": now,
            "completed_at": now,
            "last_event_type": status,
            "cancel_requested": (
                1 if status == "cancelled" else _to_int(run.get("cancel_requested"))
            ),
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
                else _to_int(run.get("duration_ms"), 0)
            ),
        }
        self._write_run_payload(run_id, payload)
        if slot_index > 0:
            self.release_slot(
                tenant_id=str(run.get("tenant_id") or ""),
                user_id=str(run.get("user_id") or ""),
                slot_index=slot_index,
                run_id=run_id,
            )
        try:
            self.redis.delete(self._cancel_key(run_id))
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to clear sub-agent cancellation key.", exc_info=True)
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        key = self._run_key(run_id)
        try:
            payload = self.redis.hgetall(key)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to load sub-agent run.", exc_info=True)
            return None
        if not payload:
            return None
        return self._decode_run_payload(payload)

    def list_runs(
        self,
        *,
        tenant_id: str,
        user_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        key = self._index_key(tenant_id, user_id)
        safe_limit = max(1, min(int(limit or 20), 100))
        try:
            run_ids = self.redis.zrevrange(key, 0, safe_limit - 1)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to enumerate sub-agent runs.", exc_info=True)
            return []

        runs: list[dict[str, Any]] = []
        for run_id in run_ids:
            run = self.get_run(str(run_id))
            if not run:
                continue
            if status and str(run.get("status") or "").lower() != status.lower():
                continue
            runs.append(run)
        return runs

    def active_runs(
        self, *, tenant_id: str, user_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        return [
            run
            for run in self.list_runs(tenant_id=tenant_id, user_id=user_id, limit=limit)
            if str(run.get("status") or "").lower() == "running"
        ]

    def record_daemon_heartbeat(self, *, phase: str = "running") -> None:
        try:
            self.redis.set(
                self.HEARTBEAT_KEY,
                json.dumps(
                    {
                        "phase": phase,
                        "timestamp": _now_iso(),
                        "interval_seconds": self.daemon_interval_seconds,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                ex=max(self.daemon_interval_seconds * 3, 300),
            )
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to write proactive daemon heartbeat.", exc_info=True)

    def get_daemon_heartbeat(self) -> dict[str, Any] | None:
        try:
            raw = self.redis.get(self.HEARTBEAT_KEY)
        except Exception:  # noqa: BLE001
            self._mark_backend_error()
            logger.debug("Failed to read proactive daemon heartbeat.", exc_info=True)
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _decode_run_payload(payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        int_fields = {"slot_index", "cancel_requested", "step_count", "duration_ms"}
        for field_name in int_fields:
            result[field_name] = _to_int(result.get(field_name), 0)
        for field_name in (
            "created_at",
            "started_at",
            "updated_at",
            "completed_at",
            "heartbeat_at",
        ):
            value = result.get(field_name)
            if value in {"", None}:
                result[field_name] = None
        for field_name in ("summary", "final_output", "error", "prompt", "parent_id"):
            value = result.get(field_name)
            result[field_name] = str(value or "")
        return result
