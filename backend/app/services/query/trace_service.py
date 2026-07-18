from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TraceCollector:
    """Collect retrieval and pipeline diagnostics for a single query execution."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    search_strategy: str = "hybrid"
    chunks_searched: int = 0
    chunks_evaluated: int = 0
    chunks_selected: int = 0
    chunks_rejected: int = 0
    rejection_reasons: list[str] = field(default_factory=list)
    timing_ms: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    _stage_starts: dict[str, float] = field(default_factory=dict, repr=False)

    def start_stage(self, name: str) -> None:
        """Start timing a named stage."""
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("stage name must not be empty")
        self._stage_starts[cleaned] = time.perf_counter()

    def end_stage(self, name: str) -> None:
        """End timing a named stage and accumulate elapsed milliseconds."""
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("stage name must not be empty")

        started_at = self._stage_starts.pop(cleaned, None)
        if started_at is None:
            return

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        self.timing_ms[cleaned] = round(
            self.timing_ms.get(cleaned, 0.0) + elapsed_ms, 2
        )

    def record_retrieval(
        self,
        *,
        searched: int,
        evaluated: int,
        selected: int,
        rejected: int = 0,
        reasons: list[str] | None = None,
        strategy: str = "hybrid",
    ) -> None:
        """Record retrieval-stage outcome statistics."""
        self.chunks_searched = max(0, searched)
        self.chunks_evaluated = max(0, evaluated)
        self.chunks_selected = max(0, selected)
        self.chunks_rejected = max(0, rejected)
        self.rejection_reasons = [
            reason.strip() for reason in (reasons or []) if reason.strip()
        ]
        self.search_strategy = strategy.strip() or "hybrid"

    def set_metadata(self, **values: Any) -> None:
        """Attach arbitrary trace metadata for downstream diagnostics."""
        for key, value in values.items():
            cleaned_key = str(key).strip()
            if cleaned_key:
                self.metadata[cleaned_key] = value

    def build_summary(self) -> str:
        """Generate a compact human-readable summary."""
        parts = [
            f"{self.search_strategy.title()} Search",
            f"{self.chunks_evaluated} chunks evaluated",
            f"{self.chunks_selected} selected",
        ]
        if self.chunks_rejected:
            parts.append(f"{self.chunks_rejected} rejected")
        return " · ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize trace data into a JSON-safe dictionary."""
        return {
            "trace_id": self.trace_id,
            "chunks_searched": self.chunks_searched,
            "chunks_evaluated": self.chunks_evaluated,
            "chunks_selected": self.chunks_selected,
            "chunks_rejected": self.chunks_rejected,
            "rejection_reasons": list(self.rejection_reasons),
            "search_strategy": self.search_strategy,
            "timing_ms": dict(self.timing_ms),
            "metadata": dict(self.metadata),
            "search_strategy_summary": self.build_summary(),
        }
