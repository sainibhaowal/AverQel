from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.system.schemas.notifications import NotificationPreferenceUpdate
from app.system.services.user_notifications import next_notification_delivery_at


def test_daily_digest_uses_local_time_zone_and_rolls_to_next_day() -> None:
    before_boundary = next_notification_delivery_at(
        frequency="daily",
        timezone_name="Europe/Berlin",
        now=datetime(2026, 1, 5, 6, 30, tzinfo=UTC),
    )
    after_boundary = next_notification_delivery_at(
        frequency="daily",
        timezone_name="Europe/Berlin",
        now=datetime(2026, 1, 5, 7, 30, tzinfo=UTC),
    )

    assert before_boundary == datetime(2026, 1, 5, 7, tzinfo=UTC)
    assert after_boundary == datetime(2026, 1, 6, 7, tzinfo=UTC)


def test_weekly_digest_is_next_monday_at_local_eight() -> None:
    result = next_notification_delivery_at(
        frequency="weekly",
        timezone_name="Europe/Berlin",
        now=datetime(2026, 1, 6, 12, tzinfo=UTC),
    )

    assert result == datetime(2026, 1, 12, 7, tzinfo=UTC)


def test_immediate_delivery_is_due_now_in_utc() -> None:
    now = datetime(2026, 1, 6, 12, tzinfo=UTC)
    assert (
        next_notification_delivery_at(frequency="none", timezone_name="Europe/Berlin", now=now)
        == now
    )


def test_preference_update_rejects_invalid_time_zones_and_null_values() -> None:
    with pytest.raises(ValidationError):
        NotificationPreferenceUpdate(timezone="Not/A_Real_Zone")
    with pytest.raises(ValidationError):
        NotificationPreferenceUpdate(email_enabled=None)
