from __future__ import annotations

import time
from dataclasses import dataclass


class CircuitOpenError(RuntimeError):
    """Raised when a provider has exceeded its transient-failure budget."""


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 3
    reset_after_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.reset_after_seconds:
            self.opened_at = None
            self.failures = 0
            return
        raise CircuitOpenError("provider circuit is open; retry later")

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= max(1, self.failure_threshold):
            self.opened_at = time.monotonic()
