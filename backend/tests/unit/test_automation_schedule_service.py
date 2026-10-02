from datetime import UTC, datetime

import pytest

from app.documents.models.organization import DocumentAutomationSchedule
from app.documents.services.schedule_service import next_schedule_run, validate_schedule_settings


def _schedule(**overrides: object) -> DocumentAutomationSchedule:
    values = {
        "interval_seconds": 3600,
        "cadence": "daily",
        "timezone": "UTC",
        "run_time": "09:00",
        "weekday": 0,
    }
    values.update(overrides)
    return DocumentAutomationSchedule(**values)


def test_daily_schedule_calculates_next_local_run() -> None:
    schedule = _schedule()
    current = datetime(2026, 9, 30, 8, 30, tzinfo=UTC)
    assert next_schedule_run(schedule, now=current) == datetime(2026, 9, 30, 9, 0, tzinfo=UTC)


def test_weekly_schedule_rolls_to_next_week_after_run_time() -> None:
    schedule = _schedule(cadence="weekly", weekday=2, run_time="09:00")
    current = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
    assert next_schedule_run(schedule, now=current) == datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def test_interval_schedule_preserves_existing_behavior() -> None:
    schedule = _schedule(cadence="interval", interval_seconds=600, run_time=None)
    current = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
    assert next_schedule_run(schedule, now=current) == datetime(2026, 9, 30, 10, 10, tzinfo=UTC)


def test_schedule_settings_reject_unknown_timezone_and_missing_weekday() -> None:
    with pytest.raises(ValueError, match="Timezone"):
        validate_schedule_settings(
            cadence="daily", timezone_name="Not/AZone", run_time="09:00", weekday=None
        )
    with pytest.raises(ValueError, match="weekday"):
        validate_schedule_settings(
            cadence="weekly", timezone_name="UTC", run_time="09:00", weekday=None
        )
