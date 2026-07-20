from __future__ import annotations

from typing import Any

from app.services.system.metrics_service import read_durable_metrics_snapshot


def durable_observability_snapshot(*, run: Any, projection: dict[str, Any], inspection: dict[str, Any]) -> dict[str, Any]:
    """Redacted, operator-safe durable runtime view assembled from authoritative state."""
    return {
        "run_id": str(run.id),
        "trace_id": str(run.trace_id or ""),
        "status": str(run.status),
        "sequence": int(run.current_sequence or 0),
        "continuation_epoch": int(run.continuation_epoch or 0),
        "recovery_count": int(run.recovery_count or 0),
        "budget": inspection["budget"].usage,
        "trajectory": inspection["trajectory"],
        "evaluation": inspection["evaluation"],
        "decision": inspection["decision"].decision,
        "dead_letter": bool(getattr(run, "status", "") == "failed" and inspection["trajectory"].get("status") == "regressing"),
        "projection": projection,
        "metrics": read_durable_metrics_snapshot(),
    }
