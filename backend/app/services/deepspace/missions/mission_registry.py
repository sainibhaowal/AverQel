from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ids import generate_uuid7_with_fallback
from app.models.deepspace.agent_runtime_preference import AgentRuntimePreference
from app.models.deepspace.mission_snapshot import DeepSpaceMissionSnapshot
from app.services.system.cache_service import get_redis_client

logger = logging.getLogger(__name__)

MISSION_STATES = frozenset(
    {"planning", "ready", "running", "awaiting_approval", "blocked", "failed", "repairing", "verified", "completed", "cancelled", "terminating", "declined", "synthesizing", "degraded"}
)
MISSION_TRANSITIONS: dict[str, frozenset[str]] = {
    "planning": frozenset({"ready", "running", "failed", "cancelled"}),
    "ready": frozenset({"running", "awaiting_approval", "cancelled", "terminating"}),
    "running": frozenset({"awaiting_approval", "blocked", "failed", "verified", "repairing", "synthesizing", "declined", "completed", "cancelled"}),
    "awaiting_approval": frozenset({"ready", "running", "blocked", "declined", "cancelled", "terminating"}),
    "blocked": frozenset({"ready", "repairing", "cancelled", "terminating"}),
    "failed": frozenset({"repairing", "ready", "cancelled", "terminating"}),
    "repairing": frozenset({"running", "verified", "failed", "cancelled"}),
    "verified": frozenset({"completed", "repairing", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "terminating": frozenset({"cancelled", "completed"}),
    "declined": frozenset({"completed", "cancelled"}),
    "synthesizing": frozenset({"verified", "completed", "failed"}),
    "degraded": frozenset({"repairing", "completed", "failed"}),
}
LANE_STATES = frozenset(
    {"pending", "ready", "running", "awaiting_approval", "blocked", "repairing", "failed", "verified", "completed", "cancelled", "approved"}
)
LANE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"ready", "running", "failed", "cancelled"}),
    "ready": frozenset({"running", "awaiting_approval", "cancelled"}),
    "running": frozenset({"awaiting_approval", "blocked", "failed", "repairing", "verified", "completed", "cancelled"}),
    "awaiting_approval": frozenset({"ready", "running", "blocked", "cancelled"}),
    "blocked": frozenset({"ready", "repairing", "cancelled"}),
    "repairing": frozenset({"running", "verified", "failed", "cancelled"}),
    "failed": frozenset({"repairing", "ready", "cancelled"}),
    "verified": frozenset({"completed", "repairing", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "approved": frozenset({"ready", "running", "cancelled"}),
}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class MissionControl:
    registry: MissionRegistry
    mission_id: str

    def heartbeat(self, **updates: Any) -> None:
        self.registry.touch_mission(self.mission_id, **updates)

    def is_cancelled(self) -> bool:
        return self.registry.is_cancel_requested(self.mission_id)


class MissionRegistry:
    """Mission registry with DB-backed preferences and Redis live mission state."""

    RUN_KEY_PREFIX = "averqel:orchestration:run"
    INDEX_KEY_PREFIX = "averqel:orchestration:index"
    CANCEL_KEY_PREFIX = "averqel:orchestration:cancel"
    HEARTBEAT_KEY = "averqel:orchestration:heartbeat"
    CONTINUATION_LOCK_PREFIX = "averqel:orchestration:continuation"
    EXECUTION_MODE_KEY_PREFIX = "averqel:orchestration:execution-mode"
    RUNTIME_PREF_KEY_PREFIX = "averqel:orchestration:runtime-pref"
    EXECUTION_MODE_PREF_KEY = "execution_mode"
    PLANNER_MODE_PREF_KEY = "planner_mode"
    SUBAGENT_PROFILE_PREF_KEY = "subagent_profile"
    RUNTIME_HOOKS_ENABLED_PREF_KEY = "runtime_hooks_enabled"
    WORKSPACE_MODE_ENABLED_PREF_KEY = "workspace_mode_enabled"
    FULL_AUTONOMY_ENABLED_PREF_KEY = "full_autonomy_enabled"
    RUNTIME_PREFERENCE_DEFINITIONS: dict[str, dict[str, Any]] = {
        EXECUTION_MODE_PREF_KEY: {
            "values": {"auto_review", "full_access"},
            "default_setting": None,
            "default": "auto_review",
        },
        PLANNER_MODE_PREF_KEY: {
            "values": {"default", "structured"},
            "default_setting": "deepspace_default_planner_mode",
            "default": "default",
        },
        SUBAGENT_PROFILE_PREF_KEY: {
            "values": {
                "default",
                "research",
                "analysis",
                "writer",
                "executor",
                "planner",
                "support",
                "file",
            },
            "default_setting": "deepspace_default_subagent_profile",
            "default": "default",
        },
        RUNTIME_HOOKS_ENABLED_PREF_KEY: {
            "values": {"true", "false"},
            "default_setting": "deepspace_runtime_hooks_enabled",
            "default": "true",
        },
        WORKSPACE_MODE_ENABLED_PREF_KEY: {
            "values": {"true", "false"},
            "default_setting": "deepspace_workspace_mode_enabled",
            "default": "true",
        },
        FULL_AUTONOMY_ENABLED_PREF_KEY: {
            "values": {"true", "false"},
            "default_setting": "deepspace_full_autonomy_enabled",
            "default": "false",
        },
    }

    def __init__(
        self, settings: Settings | None = None, db: Session | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db
        self.redis = get_redis_client()

    @property
    def run_ttl_seconds(self) -> int:
        return max(
            300,
            int(getattr(self.settings, "deepspace_subagent_run_ttl_seconds", 86400)),
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

    def _run_key(self, mission_id: str) -> str:
        return f"{self.RUN_KEY_PREFIX}:{mission_id}"

    def _index_key(self, tenant_id: str, user_id: str) -> str:
        return f"{self.INDEX_KEY_PREFIX}:{tenant_id}:{user_id}"

    def _cancel_key(self, mission_id: str) -> str:
        return f"{self.CANCEL_KEY_PREFIX}:{mission_id}"

    def _execution_mode_key(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        suffix = f":{conversation_id}" if conversation_id else ""
        return f"{self.EXECUTION_MODE_KEY_PREFIX}:{tenant_id}:{user_id}{suffix}"

    def _runtime_preference_key(
        self,
        preference_key: str,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        suffix = f":{conversation_id}" if conversation_id else ""
        return f"{self.RUNTIME_PREF_KEY_PREFIX}:{preference_key}:{tenant_id}:{user_id}{suffix}"

    def _encode(self, payload: dict[str, Any]) -> dict[str, str]:
        return {
            key: json.dumps(value, ensure_ascii=False) for key, value in payload.items()
        }

    def _decode(self, payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if value in {"", None}:
                result[key] = None
                continue
            try:
                result[key] = json.loads(value)
            except Exception:
                result[key] = value
        return result

    def _write_payload(self, mission_id: str, payload: dict[str, Any]) -> None:
        key = self._run_key(mission_id)
        try:
            self.redis.hset(
                key,
                mapping=cast(
                    "dict[str | bytes, bytes | float | int | str]",
                    self._encode(payload),
                ),
            )
            self.redis.expire(key, self.run_ttl_seconds)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to persist orchestration mission payload.", exc_info=True
            )
        self._write_durable_snapshot(mission_id, payload)

    def _write_durable_snapshot(self, mission_id: str, payload: dict[str, Any]) -> None:
        """Persist a mission snapshot independently of Redis and request DB state."""
        if self.db is None or not payload.get("tenant_id") or not payload.get("user_id"):
            return
        try:
            from app.db.session import get_session_factory

            session = get_session_factory()()
            try:
                snapshot = session.get(DeepSpaceMissionSnapshot, mission_id)
                values = {
                    "tenant_id": payload["tenant_id"],
                    "user_id": payload["user_id"],
                    "conversation_id": payload.get("parent_id") or payload.get("conversation_id"),
                    "status": str(payload.get("status") or "planning"),
                    "payload": payload,
                    "updated_at": datetime.now(UTC),
                }
                if snapshot is None:
                    session.add(DeepSpaceMissionSnapshot(mission_id=mission_id, **values))
                else:
                    for key, value in values.items():
                        setattr(snapshot, key, value)
                session.commit()
            finally:
                session.close()
        except Exception:  # noqa: BLE001
            # Redis remains the hot path; deployments can apply the migration
            # independently without making an otherwise healthy mission fail.
            logger.debug("Failed to persist durable mission snapshot", exc_info=True)

    def _write_heartbeat(
        self,
        *,
        phase: str,
        mission_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        payload = {
            "phase": phase,
            "timestamp": timestamp or _now_iso(),
            "interval_seconds": self.daemon_interval_seconds,
        }
        if mission_id:
            payload["mission_id"] = mission_id
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if user_id:
            payload["user_id"] = user_id
        try:
            self.redis.set(
                self.HEARTBEAT_KEY,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                ex=max(self.daemon_interval_seconds * 3, 300),
            )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to persist orchestration heartbeat.", exc_info=True)

    def _preference_key(
        self,
        preference_key: str,
        conversation_id: str | None = None,
    ) -> str:
        return (
            preference_key
            if conversation_id is None
            else f"{preference_key}:{conversation_id}"
        )

    def _normalize_runtime_preference_value(
        self,
        preference_key: str,
        value: Any,
    ) -> str:
        definitions = self.RUNTIME_PREFERENCE_DEFINITIONS
        definition = definitions.get(preference_key)
        if definition is None:
            return str(value).strip().lower()
        allowed_values = {str(item).strip().lower() for item in definition["values"]}
        if preference_key in {
            self.RUNTIME_HOOKS_ENABLED_PREF_KEY,
            self.WORKSPACE_MODE_ENABLED_PREF_KEY,
            self.FULL_AUTONOMY_ENABLED_PREF_KEY,
        }:
            if isinstance(value, str):
                cleaned = value.strip().lower()
                normalized = (
                    "true" if cleaned in {"1", "true", "yes", "on"} else "false"
                )
            else:
                normalized = "true" if bool(value) else "false"
        else:
            normalized = str(value).strip().lower()
        if normalized in allowed_values:
            return normalized
        return str(definition["default"]).strip().lower()

    def _runtime_preference_default(self, preference_key: str) -> str:
        definition = self.RUNTIME_PREFERENCE_DEFINITIONS.get(preference_key)
        if definition is None:
            return ""
        default_setting = definition.get("default_setting")
        if default_setting:
            setting_value = getattr(self.settings, str(default_setting), None)
            normalized_setting = self._normalize_runtime_preference_value(
                preference_key,
                setting_value if setting_value is not None else definition["default"],
            )
            if normalized_setting:
                return normalized_setting
        return str(definition["default"]).strip().lower()

    def _upsert_runtime_preference(
        self,
        *,
        tenant_id: str,
        user_id: str,
        preference_key: str,
        value: Any,
        conversation_id: str | None = None,
    ) -> None:
        if self.db is None:
            return
        normalized = self._normalize_runtime_preference_value(preference_key, value)
        pref_key = self._preference_key(preference_key, conversation_id)
        stmt = select(AgentRuntimePreference).where(
            AgentRuntimePreference.tenant_id == tenant_id,
            AgentRuntimePreference.user_id == user_id,
            AgentRuntimePreference.preference_key == pref_key,
        )
        if conversation_id is None:
            stmt = stmt.where(AgentRuntimePreference.conversation_id.is_(None))
        else:
            stmt = stmt.where(AgentRuntimePreference.conversation_id == conversation_id)
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            row = AgentRuntimePreference(
                id=str(generate_uuid7_with_fallback()),
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                preference_key=pref_key,
                preference_value=normalized,
                source="orchestration",
            )
            self.db.add(row)
        else:
            row.preference_value = normalized
            row.source = "orchestration"
        try:
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            raise

    def _load_runtime_preference(
        self,
        *,
        tenant_id: str,
        user_id: str,
        preference_key: str,
        conversation_id: str | None = None,
    ) -> str | None:
        if self.db is None:
            return None
        preference_scopes = [conversation_id, None] if conversation_id else [None]
        for scope in preference_scopes:
            pref_key = self._preference_key(preference_key, scope)
            stmt = select(AgentRuntimePreference.preference_value).where(
                AgentRuntimePreference.tenant_id == tenant_id,
                AgentRuntimePreference.user_id == user_id,
                AgentRuntimePreference.preference_key == pref_key,
            )
            if scope is None:
                stmt = stmt.where(AgentRuntimePreference.conversation_id.is_(None))
            else:
                stmt = stmt.where(AgentRuntimePreference.conversation_id == scope)
            try:
                value = self.db.execute(stmt).scalar_one_or_none()
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Failed to read execution preference from DB.", exc_info=True
                )
                return None
            if value:
                normalized = self._normalize_runtime_preference_value(
                    preference_key,
                    value,
                )
                if normalized:
                    return normalized
        return None

    def set_runtime_preference(
        self,
        *,
        tenant_id: str,
        user_id: str,
        preference_key: str,
        value: Any,
        conversation_id: str | None = None,
    ) -> str:
        normalized = self._normalize_runtime_preference_value(preference_key, value)
        try:
            key = self._runtime_preference_key(
                preference_key,
                tenant_id,
                user_id,
                conversation_id,
            )
            if conversation_id:
                self.redis.set(key, normalized, ex=self.run_ttl_seconds)
            else:
                self.redis.set(key, normalized)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to persist runtime preference in Redis.",
                exc_info=True,
            )
        try:
            self._upsert_runtime_preference(
                tenant_id=tenant_id,
                user_id=user_id,
                preference_key=preference_key,
                value=normalized,
                conversation_id=conversation_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to persist runtime preference in DB.",
                exc_info=True,
            )
        return normalized

    def get_runtime_preference(
        self,
        *,
        tenant_id: str,
        user_id: str,
        preference_key: str,
        conversation_id: str | None = None,
    ) -> str:
        if preference_key == self.EXECUTION_MODE_PREF_KEY:
            return self.get_execution_mode(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        db_value = self._load_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=preference_key,
            conversation_id=conversation_id,
        )
        if db_value:
            return db_value

        keys: list[str] = []
        if conversation_id:
            keys.append(
                self._runtime_preference_key(
                    preference_key,
                    tenant_id,
                    user_id,
                    conversation_id,
                )
            )
        keys.append(self._runtime_preference_key(preference_key, tenant_id, user_id))
        for key in keys:
            try:
                raw = self.redis.get(key)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to read runtime preference.", exc_info=True)
                continue
            if not raw:
                continue
            normalized = self._normalize_runtime_preference_value(
                preference_key,
                raw,
            )
            if normalized:
                return normalized
        return self._runtime_preference_default(preference_key)

    def get_runtime_preferences(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> dict[str, str]:
        return {
            key: (
                self.get_execution_mode(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
                if key == self.EXECUTION_MODE_PREF_KEY
                else self.get_runtime_preference(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    preference_key=key,
                    conversation_id=conversation_id,
                )
            )
            for key in self.RUNTIME_PREFERENCE_DEFINITIONS
        }

    def set_full_autonomy_enabled(
        self, *, tenant_id: str, user_id: str, enabled: bool, conversation_id: str | None = None
    ) -> str:
        return self.set_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.FULL_AUTONOMY_ENABLED_PREF_KEY,
            value=enabled,
            conversation_id=conversation_id,
        )

    def get_full_autonomy_enabled(
        self, *, tenant_id: str, user_id: str, conversation_id: str | None = None
    ) -> bool:
        return self.get_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.FULL_AUTONOMY_ENABLED_PREF_KEY,
            conversation_id=conversation_id,
        ) == "true"

    def register_mission(
        self,
        *,
        mission_id: str,
        tenant_id: str,
        user_id: str,
        objective: str,
        plan: dict[str, Any],
        parent_id: str | None = None,
        status: str = "planning",
        execution_mode: str = "auto_review",
        full_autonomy: bool = False,
    ) -> dict[str, Any]:
        now = _now_iso()
        payload = {
            "mission_id": mission_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "parent_id": parent_id or "",
            "objective": objective,
            "execution_mode": execution_mode,
            "full_autonomy": bool(full_autonomy),
            "continuation_count": 0,
            "plan": plan,
            "mission_graph": plan.get("graph", {}),
            "status": status,
            "created_at": now,
            "started_at": now,
            "updated_at": now,
            "completed_at": "",
            "summary": "",
            "final_output": "",
            "error": "",
            "step_count": 0,
            "duration_ms": 0,
            "last_event_type": "start",
            "last_event_message": "Mission registered.",
            "heartbeat_at": now,
            "lane_results": [],
            "approval_queue": plan.get("approval_queue", []),
            "lane_states": plan.get("lanes", []),
            "events": [],
        }
        self._write_payload(mission_id, payload)
        self._write_heartbeat(
            phase=status,
            mission_id=mission_id,
            tenant_id=tenant_id,
            user_id=user_id,
            timestamp=now,
        )
        try:
            self.redis.zadd(
                self._index_key(tenant_id, user_id), {mission_id: time.time()}
            )
            self.redis.expire(self._index_key(tenant_id, user_id), self.run_ttl_seconds)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to index orchestration mission.", exc_info=True)
        return self.get_mission(mission_id) or payload

    def schedule_continuation(self, mission_id: str) -> bool:
        """Atomically mark one automatic continuation as scheduled."""
        payload = self.get_mission(mission_id)
        if not payload or not bool(payload.get("full_autonomy")):
            return False
        if str(payload.get("status") or "") not in {"blocked", "failed"}:
            return False
        if int(payload.get("continuation_count") or 0) >= 24:
            return False
        lock_key = f"{self.CONTINUATION_LOCK_PREFIX}:{mission_id}"
        try:
            if not self.redis.set(lock_key, "1", nx=True, ex=300):
                return False
        except Exception:  # noqa: BLE001
            return False
        payload["continuation_scheduled"] = True
        payload["updated_at"] = _now_iso()
        self._write_payload(mission_id, payload)
        return True

    def prepare_continuation(self, mission_id: str) -> dict[str, Any] | None:
        """Move blocked/failed work back to ready for a checkpoint resume."""
        payload = self.get_mission(mission_id)
        if not payload or not bool(payload.get("full_autonomy")):
            return None
        count = int(payload.get("continuation_count") or 0) + 1
        if count > 24:
            return None
        for lane in list(payload.get("lane_states") or []):
            if str(lane.get("status") or "") in {"blocked", "failed"}:
                lane["status"] = "ready"
                lane["updated_at"] = _now_iso()
        payload["continuation_count"] = count
        payload["continuation_scheduled"] = False
        payload["updated_at"] = _now_iso()
        self._write_payload(mission_id, payload)
        try:
            self.touch_mission(
                mission_id,
                status="ready",
                last_event_type="continuation_ready",
                last_event_message=f"Checkpoint continuation {count} is ready.",
            )
        except ValueError:
            return None
        return self.get_mission(mission_id)

    def touch_mission(self, mission_id: str, **updates: Any) -> None:
        payload = self.get_mission(mission_id)
        if not payload:
            return
        if "status" in updates and updates["status"] is not None:
            target = str(updates["status"])
            current = str(payload.get("status") or "planning")
            if target not in MISSION_STATES:
                raise ValueError(f"Unknown mission state: {target}")
            if target != current and target not in MISSION_TRANSITIONS.get(current, frozenset()):
                raise ValueError(f"Invalid mission transition: {current} -> {target}")
            payload["status"] = target
        if "objective" in updates and updates["objective"] is not None:
            payload["objective"] = updates["objective"]
        if "plan" in updates and updates["plan"] is not None:
            payload["plan"] = updates["plan"]
        if "execution_mode" in updates and updates["execution_mode"] is not None:
            payload["execution_mode"] = str(updates["execution_mode"])
        if "mission_graph" in updates and updates["mission_graph"] is not None:
            payload["mission_graph"] = updates["mission_graph"]
        if "summary" in updates and updates["summary"] is not None:
            payload["summary"] = updates["summary"]
        if "final_output" in updates and updates["final_output"] is not None:
            payload["final_output"] = updates["final_output"]
        if "error" in updates and updates["error"] is not None:
            payload["error"] = updates["error"]
        if "step_count" in updates and updates["step_count"] is not None:
            payload["step_count"] = int(updates["step_count"])
        if "duration_ms" in updates and updates["duration_ms"] is not None:
            payload["duration_ms"] = int(updates["duration_ms"])
        if "completed_at" in updates and updates["completed_at"] is not None:
            payload["completed_at"] = str(updates["completed_at"])
        if "last_event_type" in updates and updates["last_event_type"] is not None:
            payload["last_event_type"] = updates["last_event_type"]
        if (
            "last_event_message" in updates
            and updates["last_event_message"] is not None
        ):
            payload["last_event_message"] = updates["last_event_message"]
        if "lane_results" in updates and updates["lane_results"] is not None:
            payload["lane_results"] = updates["lane_results"]
        if "lane_states" in updates and updates["lane_states"] is not None:
            payload["lane_states"] = updates["lane_states"]
        if "approval_queue" in updates and updates["approval_queue"] is not None:
            payload["approval_queue"] = updates["approval_queue"]
        if "parent_id" in updates and updates["parent_id"] is not None:
            payload["parent_id"] = updates["parent_id"]
        if updates.get("last_event_type"):
            events = list(payload.get("events") or [])
            events.append(
                {
                    "type": str(updates["last_event_type"]),
                    "message": str(updates.get("last_event_message") or ""),
                    "status": str(payload.get("status") or ""),
                    "timestamp": _now_iso(),
                }
            )
            payload["events"] = events[-256:]
        payload["updated_at"] = _now_iso()
        payload["heartbeat_at"] = _now_iso()
        self._write_payload(mission_id, payload)
        self._write_heartbeat(
            phase=str(payload.get("status") or "running"),
            mission_id=mission_id,
            tenant_id=str(payload.get("tenant_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            timestamp=str(payload.get("heartbeat_at") or _now_iso()),
        )

    def transition_mission(self, mission_id: str, target: str, *, reason: str = "") -> None:
        """Apply a validated state transition and append an operator-visible event."""
        self.touch_mission(
            mission_id,
            status=target,
            last_event_type="state_transition",
            last_event_message=reason or f"Mission transitioned to {target}.",
        )

    def append_event(
        self,
        mission_id: str,
        *,
        event_type: str,
        data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        node_id: str | None = None,
        node_status: str | None = None,
    ) -> dict[str, Any] | None:
        """Append an event and optionally advance its graph node atomically-ish.

        Redis hashes are the mission source of truth in this runtime. Events are
        deduplicated by idempotency key so retries cannot duplicate side effects
        in the mission ledger.
        """
        payload = self.get_mission(mission_id)
        if not payload:
            return None
        events = list(payload.get("events") or [])
        if idempotency_key and any(
            str(item.get("idempotency_key") or "") == idempotency_key
            for item in events
            if isinstance(item, dict)
        ):
            return events[-1] if events else None
        event = {
            "event_id": str(generate_uuid7_with_fallback()),
            "type": str(event_type),
            "data": dict(data or {}),
            "idempotency_key": idempotency_key or "",
            "node_id": node_id or "",
            "timestamp": _now_iso(),
        }
        events.append(event)
        payload["events"] = events[-256:]
        if node_id and node_status:
            graph = payload.get("mission_graph") or {}
            nodes = graph.get("nodes") if isinstance(graph, dict) else None
            if isinstance(nodes, list):
                for node in nodes:
                    if str(node.get("id") or node.get("node_id") or node.get("ref") or "") == node_id:
                        current_node_status = str(node.get("status") or "pending")
                        if node_status not in LANE_STATES:
                            raise ValueError(f"Unknown node state: {node_status}")
                        if node_status != current_node_status and node_status not in LANE_TRANSITIONS.get(current_node_status, frozenset()):
                            raise ValueError(f"Invalid node transition: {current_node_status} -> {node_status}")
                        node["status"] = node_status
                        node["updated_at"] = event["timestamp"]
                        break
                payload["mission_graph"] = graph
        payload["last_event_type"] = str(event_type)
        payload["last_event_message"] = str((data or {}).get("message") or event_type)
        payload["updated_at"] = event["timestamp"]
        payload["heartbeat_at"] = event["timestamp"]
        self._write_payload(mission_id, payload)
        return event

    def save_checkpoint(
        self,
        mission_id: str,
        *,
        plan: dict[str, Any] | None = None,
        completed_tasks: list[Any] | None = None,
        pending_tasks: list[Any] | None = None,
        tool_results: list[Any] | None = None,
        changed_files: list[str] | None = None,
        test_results: list[Any] | None = None,
        failures: list[Any] | None = None,
        next_action: str | None = None,
        budget: dict[str, Any] | None = None,
        status: str | None = None,
        **extra: Any,
    ) -> None:
        """Persist resumable execution state after every meaningful turn."""
        payload = self.get_mission(mission_id)
        if not payload:
            return
        checkpoint = dict(payload.get("checkpoint") or {})
        values = {
            "plan": plan,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "tool_results": tool_results,
            "changed_files": changed_files,
            "test_results": test_results,
            "failures": failures,
            "next_action": next_action,
            "budget": budget,
            **extra,
        }
        checkpoint.update({key: value for key, value in values.items() if value is not None})
        checkpoint["updated_at"] = _now_iso()
        payload["checkpoint"] = checkpoint
        self._write_payload(mission_id, payload)
        self.append_event(
            mission_id,
            event_type="checkpoint",
            data={"next_action": next_action or "", "status": status or payload.get("status", "")},
            idempotency_key=f"{mission_id}:checkpoint:{checkpoint['updated_at']}",
        )

    def create_repair_node(
        self, mission_id: str, *, failed_node_id: str, reason: str
    ) -> str | None:
        """Add a bounded repair node instead of silently retrying the old branch."""
        payload = self.get_mission(mission_id)
        if not payload:
            return None
        graph = payload.get("mission_graph") or {"nodes": [], "edges": []}
        graph.setdefault("nodes", [])
        graph.setdefault("edges", [])
        for existing in graph["nodes"]:
            if (
                existing.get("kind") == "repair"
                and failed_node_id in list(existing.get("depends_on") or [])
            ):
                return str(existing.get("id"))
        repair_id = f"repair_{str(generate_uuid7_with_fallback())}"
        graph["nodes"].append(
            {
                "id": repair_id,
                "status": "pending",
                "kind": "repair",
                "depends_on": [failed_node_id],
                "reason": reason[:2000],
            }
        )
        graph["edges"].append(
            {"from": failed_node_id, "to": repair_id, "kind": "repair"}
        )
        payload["mission_graph"] = graph
        payload["updated_at"] = _now_iso()
        self._write_payload(mission_id, payload)
        self.append_event(
            mission_id,
            event_type="repair_node_created",
            data={"node_id": repair_id, "failed_node_id": failed_node_id, "reason": reason},
            idempotency_key=f"{mission_id}:repair:{failed_node_id}:{repair_id}",
            node_id=repair_id,
        )
        return repair_id

    def invalidate_plan_branch(
        self, mission_id: str, *, node_id: str, reason: str
    ) -> bool:
        """Mark a failed branch unusable so summaries cannot promote it to success."""
        payload = self.get_mission(mission_id)
        if not payload:
            return False
        graph = payload.get("mission_graph") or {}
        nodes = graph.get("nodes") if isinstance(graph, dict) else None
        found = False
        if isinstance(nodes, list):
            for node in nodes:
                if str(node.get("id") or node.get("node_id") or "") == node_id:
                    node["status"] = "failed"
                    node["invalidated"] = True
                    node["failure_reason"] = reason[:2000]
                    found = True
                    break
        if not found:
            return False
        payload["mission_graph"] = graph
        self._write_payload(mission_id, payload)
        self.append_event(
            mission_id,
            event_type="plan_branch_invalidated",
            data={"node_id": node_id, "reason": reason},
            idempotency_key=f"{mission_id}:invalidate:{node_id}:{reason[:80]}",
            node_id=node_id,
        )
        return True

    def update_lane(
        self,
        mission_id: str,
        lane_id: str,
        *,
        status: str | None = None,
        summary: str | None = None,
        final_output: str | None = None,
        error: str | None = None,
        step_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = self.get_mission(mission_id)
        if not payload:
            return
        lanes = list(payload.get("lane_states") or [])
        updated = False
        for lane in lanes:
            if str(lane.get("lane_id") or "") != lane_id:
                continue
            if status is not None:
                target_status = str(status)
                current_status = str(lane.get("status") or "pending")
                if target_status not in LANE_STATES:
                    raise ValueError(f"Unknown lane state: {target_status}")
                if target_status != current_status and target_status not in LANE_TRANSITIONS.get(current_status, frozenset()):
                    raise ValueError(f"Invalid lane transition: {current_status} -> {target_status}")
                lane["status"] = status
            if summary is not None:
                lane["summary"] = summary
            if final_output is not None:
                lane["final_output"] = final_output
            if error is not None:
                lane["error"] = error
            if step_count is not None:
                lane["step_count"] = step_count
            if metadata:
                lane_meta = dict(lane.get("metadata") or {})
                lane_meta.update(metadata)
                lane["metadata"] = lane_meta
            lane["updated_at"] = _now_iso()
            if status in {"completed", "failed", "cancelled"}:
                lane["completed_at"] = _now_iso()
            updated = True
            break
        if updated:
            payload["lane_states"] = lanes
            self._write_payload(mission_id, payload)

    def append_lane_result(self, mission_id: str, result: dict[str, Any]) -> None:
        payload = self.get_mission(mission_id)
        if not payload:
            return
        lane_results = list(payload.get("lane_results") or [])
        lane_results.append(result)
        payload["lane_results"] = lane_results
        self._write_payload(mission_id, payload)
        self.append_event(
            mission_id,
            event_type="lane_result",
            data={
                "lane_id": result.get("lane_id"),
                "status": result.get("status"),
                "summary": str(result.get("summary") or "")[:2000],
            },
            idempotency_key=f"{mission_id}:lane:{result.get('lane_id')}:{result.get('status')}",
            node_id=str(result.get("lane_id") or "") or None,
        )

    def request_approval(self, mission_id: str, data: dict[str, Any]) -> None:
        payload = self.get_mission(mission_id)
        if not payload:
            return
        approval_queue = list(payload.get("approval_queue") or [])
        approval_queue.append(data)
        payload["approval_queue"] = approval_queue
        payload["status"] = "awaiting_approval"
        payload["last_event_type"] = "approval_request"
        payload["last_event_message"] = str(data.get("message") or "Approval required.")
        payload["updated_at"] = _now_iso()
        self._write_payload(mission_id, payload)
        self._write_heartbeat(
            phase="awaiting_approval",
            mission_id=mission_id,
            tenant_id=str(payload.get("tenant_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            timestamp=str(payload.get("updated_at") or _now_iso()),
        )

    def resolve_approval(self, mission_id: str, lane_id: str, approved: bool) -> None:
        payload = self.get_mission(mission_id)
        if not payload:
            return
        approval_queue = [
            item
            for item in list(payload.get("approval_queue") or [])
            if str(item.get("lane_id") or "") != lane_id
        ]
        payload["approval_queue"] = approval_queue
        payload["status"] = "running" if approved else "declined"
        payload["last_event_type"] = "approval_resolved"
        payload["last_event_message"] = "Approved." if approved else "Declined."
        payload["updated_at"] = _now_iso()
        self._write_payload(mission_id, payload)
        self._write_heartbeat(
            phase=payload["status"],
            mission_id=mission_id,
            tenant_id=str(payload.get("tenant_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            timestamp=str(payload.get("updated_at") or _now_iso()),
        )

    def complete_mission(
        self,
        *,
        mission_id: str,
        status: str,
        summary: str | None = None,
        final_output: str | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any] | None:
        payload = self.get_mission(mission_id)
        if not payload:
            return None
        completed_at = _now_iso()
        self.touch_mission(
            mission_id,
            status=status,
            summary=summary,
            final_output=final_output,
            error=error,
            duration_ms=duration_ms,
            completed_at=completed_at,
            last_event_type=status,
            last_event_message=summary or f"Mission {status}.",
        )
        return self.get_mission(mission_id)

    def set_execution_mode(
        self,
        *,
        tenant_id: str,
        user_id: str,
        mode: str,
        conversation_id: str | None = None,
    ) -> str:
        normalized = self._normalize_runtime_preference_value(
            self.EXECUTION_MODE_PREF_KEY,
            mode,
        )
        try:
            key = self._execution_mode_key(tenant_id, user_id, conversation_id)
            if conversation_id:
                self.redis.set(key, normalized, ex=self.run_ttl_seconds)
            else:
                self.redis.set(key, normalized)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to persist execution mode in Redis.", exc_info=True)
        try:
            self._upsert_runtime_preference(
                tenant_id=tenant_id,
                user_id=user_id,
                preference_key=self.EXECUTION_MODE_PREF_KEY,
                value=normalized,
                conversation_id=conversation_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to persist execution mode in DB.", exc_info=True)
        return normalized

    def get_execution_mode(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        db_mode = self._load_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.EXECUTION_MODE_PREF_KEY,
            conversation_id=conversation_id,
        )
        if db_mode:
            return db_mode

        keys: list[str] = []
        if conversation_id:
            keys.append(self._execution_mode_key(tenant_id, user_id, conversation_id))
        keys.append(self._execution_mode_key(tenant_id, user_id))
        for key in keys:
            try:
                raw = self.redis.get(key)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to read execution mode.", exc_info=True)
                continue
            if not raw:
                continue
            normalized = str(raw).strip().lower()
            if normalized in {"auto_review", "full_access"}:
                return normalized
        return "auto_review"

    def set_planner_mode(
        self,
        *,
        tenant_id: str,
        user_id: str,
        mode: str,
        conversation_id: str | None = None,
    ) -> str:
        return self.set_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.PLANNER_MODE_PREF_KEY,
            value=mode,
            conversation_id=conversation_id,
        )

    def get_planner_mode(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        return self.get_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.PLANNER_MODE_PREF_KEY,
            conversation_id=conversation_id,
        )

    def set_subagent_profile(
        self,
        *,
        tenant_id: str,
        user_id: str,
        profile: str,
        conversation_id: str | None = None,
    ) -> str:
        return self.set_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.SUBAGENT_PROFILE_PREF_KEY,
            value=profile,
            conversation_id=conversation_id,
        )

    def get_subagent_profile(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        return self.get_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.SUBAGENT_PROFILE_PREF_KEY,
            conversation_id=conversation_id,
        )

    def set_runtime_hooks_enabled(
        self,
        *,
        tenant_id: str,
        user_id: str,
        enabled: bool,
        conversation_id: str | None = None,
    ) -> str:
        return self.set_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.RUNTIME_HOOKS_ENABLED_PREF_KEY,
            value=enabled,
            conversation_id=conversation_id,
        )

    def get_runtime_hooks_enabled(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> bool:
        return (
            self.get_runtime_preference(
                tenant_id=tenant_id,
                user_id=user_id,
                preference_key=self.RUNTIME_HOOKS_ENABLED_PREF_KEY,
                conversation_id=conversation_id,
            )
            == "true"
        )

    def set_workspace_mode_enabled(
        self,
        *,
        tenant_id: str,
        user_id: str,
        enabled: bool,
        conversation_id: str | None = None,
    ) -> str:
        return self.set_runtime_preference(
            tenant_id=tenant_id,
            user_id=user_id,
            preference_key=self.WORKSPACE_MODE_ENABLED_PREF_KEY,
            value=enabled,
            conversation_id=conversation_id,
        )

    def get_workspace_mode_enabled(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> bool:
        return (
            self.get_runtime_preference(
                tenant_id=tenant_id,
                user_id=user_id,
                preference_key=self.WORKSPACE_MODE_ENABLED_PREF_KEY,
                conversation_id=conversation_id,
            )
            == "true"
        )

    def request_cancellation(self, mission_id: str) -> dict[str, Any] | None:
        mission = self.get_mission(mission_id)
        if not mission:
            return None
        try:
            self.redis.set(self._cancel_key(mission_id), "1", ex=self.run_ttl_seconds)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to persist orchestration cancellation request.", exc_info=True
            )
        self.touch_mission(
            mission_id,
            status="terminating",
            last_event_type="termination_requested",
            last_event_message="Termination requested.",
        )
        return self.get_mission(mission_id)

    def get_heartbeat(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if tenant_id and user_id:
            missions = self.active_missions(
                tenant_id=tenant_id, user_id=user_id, limit=1
            )
            if missions:
                mission = missions[0]
                timestamp = str(
                    mission.get("heartbeat_at")
                    or mission.get("updated_at")
                    or mission.get("created_at")
                    or _now_iso()
                )
                return {
                    "phase": str(mission.get("status") or "running"),
                    "timestamp": timestamp,
                    "interval_seconds": self.daemon_interval_seconds,
                    "mission_id": str(mission.get("mission_id") or ""),
                }
        try:
            raw = self.redis.get(self.HEARTBEAT_KEY)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to read orchestration heartbeat.", exc_info=True)
            raw = None
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return payload
        return {
            "phase": "idle",
            "timestamp": _now_iso(),
            "interval_seconds": self.daemon_interval_seconds,
        }

    def is_cancel_requested(self, mission_id: str) -> bool:
        try:
            return bool(self.redis.exists(self._cancel_key(mission_id)))
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to read orchestration cancellation state.", exc_info=True
            )
            return False

    def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        try:
            payload = self.redis.hgetall(self._run_key(mission_id))
        except Exception:  # noqa: BLE001
            logger.debug("Failed to read orchestration mission payload.", exc_info=True)
            return None
        if payload:
            return self._decode(payload)
        if self.db is None:
            return None
        try:
            snapshot = self.db.get(DeepSpaceMissionSnapshot, mission_id)
            return dict(snapshot.payload) if snapshot is not None else None
        except Exception:  # noqa: BLE001
            logger.debug("Failed to load durable mission snapshot", exc_info=True)
            return None

    def list_missions(
        self,
        *,
        tenant_id: str,
        user_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        try:
            mission_ids = self.redis.zrevrange(
                self._index_key(tenant_id, user_id), 0, limit - 1
            )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to list orchestration missions.", exc_info=True)
            mission_ids = []
        missions: list[dict[str, Any]] = []
        for mission_id in mission_ids:
            payload = self.get_mission(str(mission_id))
            if not payload:
                continue
            if (
                str(payload.get("tenant_id") or "") != tenant_id
                or str(payload.get("user_id") or "") != user_id
            ):
                continue
            if status and str(payload.get("status") or "").lower() != status.lower():
                continue
            missions.append(payload)
        if not missions and self.db is not None:
            try:
                rows = (
                    self.db.query(DeepSpaceMissionSnapshot)
                    .filter(
                        DeepSpaceMissionSnapshot.tenant_id == tenant_id,
                        DeepSpaceMissionSnapshot.user_id == user_id,
                    )
                    .order_by(DeepSpaceMissionSnapshot.updated_at.desc())
                    .limit(limit)
                    .all()
                )
                for row in rows:
                    payload = dict(row.payload or {})
                    if status and str(payload.get("status") or "").lower() != status.lower():
                        continue
                    missions.append(payload)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to list durable mission snapshots", exc_info=True)
        return missions

    def active_missions(
        self,
        *,
        tenant_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        active_statuses = {
            "planning",
            "running",
            "awaiting_approval",
            "synthesizing",
            "blocked",
        }
        missions = self.list_missions(
            tenant_id=tenant_id,
            user_id=user_id,
            limit=limit,
        )
        return [
            mission
            for mission in missions
            if str(mission.get("status") or "").lower() in active_statuses
        ]
