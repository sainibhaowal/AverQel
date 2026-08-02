from __future__ import annotations

from app.system.services.rate_limit_service import resolve_request_priority


def test_dashboard_reads_are_not_background_work() -> None:
    assert resolve_request_priority("/api/v1/dashboard/overview") == "INTERACTIVE"
    assert resolve_request_priority("/api/v1/collections/notifications") == "INTERACTIVE"


def test_expensive_list_endpoints_remain_background_work() -> None:
    assert resolve_request_priority("/api/v1/documents") == "BACKGROUND"
    assert resolve_request_priority("/api/v1/metrics") == "BACKGROUND"
