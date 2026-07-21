import pytest

from app.deepspace.execution.reliability import CircuitBreaker, CircuitOpenError


def test_circuit_opens_after_transient_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=60)
    breaker.record_failure()
    breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_success_closes_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure()
    breaker.record_success()

    breaker.before_call()
