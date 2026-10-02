from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.documents.models.organization import DocumentAutomationSchedule

TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
CADENCES = {"interval", "hourly", "daily", "weekly"}


def validate_schedule_settings(
    *, cadence: str, timezone_name: str, run_time: str | None, weekday: int | None
) -> None:
    if cadence not in CADENCES:
        raise ValueError("Cadence must be interval, hourly, daily, or weekly.")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Timezone is not recognized.") from exc
    if run_time is not None and not TIME_PATTERN.fullmatch(run_time):
        raise ValueError("Run time must use HH:MM format.")
    if cadence in {"daily", "weekly"} and not run_time:
        raise ValueError("Daily and weekly schedules require a run time.")
    if cadence == "weekly" and weekday is None:
        raise ValueError("Weekly schedules require a weekday.")
    if weekday is not None and not 0 <= weekday <= 6:
        raise ValueError("Weekday must be between 0 and 6.")


def next_schedule_run(
    schedule: DocumentAutomationSchedule, *, now: datetime | None = None
) -> datetime:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if schedule.cadence == "interval":
        return current + timedelta(seconds=schedule.interval_seconds)

    zone = ZoneInfo(schedule.timezone)
    local_now = current.astimezone(zone)
    if schedule.cadence == "hourly":
        candidate = local_now.replace(minute=0, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(hours=1)
        return candidate.astimezone(UTC)

    hour, minute = (int(value) for value in (schedule.run_time or "00:00").split(":"))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if schedule.cadence == "weekly":
        days_ahead = (
            (schedule.weekday if schedule.weekday is not None else 0) - local_now.weekday()
        ) % 7
        candidate += timedelta(days=days_ahead)
    if candidate <= local_now:
        candidate += timedelta(days=7 if schedule.cadence == "weekly" else 1)
    return candidate.astimezone(UTC)
