"""Background continuation for explicitly enabled Full Autonomy missions."""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.deepspace.missions.mission_registry import MissionRegistry
from app.services.deepspace.orchestration.master_orchestrator import MasterOrchestrator
from app.system.services.metrics_service import DEEPSPACE_CONTINUATION_EVENTS_TOTAL
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="deepspace.continue_full_autonomy")  # type: ignore[misc]
def continue_full_autonomy_mission(mission_id: str) -> dict[str, str]:
    """Resume a checkpointed mission without requiring another user prompt.

    Approval queues, cancellation requests, isolation checks, and tool contracts
    are still enforced by the normal orchestrator/executor path.
    """
    settings = get_settings()
    db = get_session_factory()()
    try:
        registry = MissionRegistry(settings, db=db)
        mission = registry.get_mission(str(mission_id))
        if not mission or not mission.get("full_autonomy"):
            DEEPSPACE_CONTINUATION_EVENTS_TOTAL.labels(status="ignored").inc()
            return {"mission_id": str(mission_id), "status": "ignored"}
        if registry.is_cancel_requested(str(mission_id)):
            DEEPSPACE_CONTINUATION_EVENTS_TOTAL.labels(status="cancelled").inc()
            return {"mission_id": str(mission_id), "status": "cancelled"}
        if str(mission.get("status") or "") not in {"blocked", "failed"}:
            DEEPSPACE_CONTINUATION_EVENTS_TOTAL.labels(status="not_ready").inc()
            return {"mission_id": str(mission_id), "status": "not_ready"}
        prepared = registry.prepare_continuation(str(mission_id))
        if not prepared:
            DEEPSPACE_CONTINUATION_EVENTS_TOTAL.labels(status="budget_exhausted").inc()
            return {"mission_id": str(mission_id), "status": "budget_exhausted"}

        auth = AuthContext(
            user_id=uuid.UUID(str(prepared["user_id"])),
            tenant_id=uuid.UUID(str(prepared["tenant_id"])),
            roles=frozenset({"user"}),
            token_id=f"full-autonomy:{mission_id}",
            permissions=frozenset({"queries:run"}),
            auth_type="system",
        )
        orchestrator = MasterOrchestrator(db=db, auth=auth, settings=settings)

        async def drain() -> None:
            async for _event in orchestrator.stream_mission(
                objective=str(prepared.get("objective") or ""),
                conversation_id=(
                    uuid.UUID(str(prepared["parent_id"]))
                    if prepared.get("parent_id")
                    else None
                ),
                execution_mode=str(prepared.get("execution_mode") or "auto_review"),
                mission_id=str(mission_id),
            ):
                pass

        asyncio.run(drain())
        DEEPSPACE_CONTINUATION_EVENTS_TOTAL.labels(status="continued").inc()
        return {"mission_id": str(mission_id), "status": "continued"}
    except Exception:  # noqa: BLE001
        logger.exception("Full-autonomy continuation failed for %s", mission_id)
        DEEPSPACE_CONTINUATION_EVENTS_TOTAL.labels(status="failed").inc()
        return {"mission_id": str(mission_id), "status": "failed"}
    finally:
        db.close()
