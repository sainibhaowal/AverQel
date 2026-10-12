from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.deepspace.schemas.chats import QueueTurnRequest, RegenerateRequest
from app.deepspace.services.chat_service import _normalize_reasoning_effort

pytestmark = pytest.mark.unit_no_db


def test_chat_requests_accept_bounded_model_advertised_effort_names() -> None:
    queued = QueueTurnRequest(message="Explain this", reasoning_effort="tier-5")
    regenerated = RegenerateRequest(reasoning_effort="ultra")

    assert queued.reasoning_effort == "tier_5"
    assert regenerated.reasoning_effort == "ultra"


@pytest.mark.parametrize("value", ["bad/value", "", "1-high", "a" * 21])
def test_chat_requests_reject_unsafe_or_oversized_effort_names(value: str) -> None:
    with pytest.raises(ValidationError):
        QueueTurnRequest(message="Explain this", reasoning_effort=value)


def test_chat_normalization_preserves_exact_advertised_levels_and_safe_legacy_fallback() -> None:
    assert (
        _normalize_reasoning_effort("ultra", ("minimal", "ultra"), capabilities_known=True)
        == "ultra"
    )
    assert _normalize_reasoning_effort("tier-5", ("tier_5",), capabilities_known=True) == "tier_5"
    assert _normalize_reasoning_effort("tier-5", ("low",), capabilities_known=True) is None
    assert (
        _normalize_reasoning_effort("vendor-level", (), capabilities_known=False) == "vendor_level"
    )


def test_standard_effort_downgrade_does_not_depend_on_catalog_order() -> None:
    assert (
        _normalize_reasoning_effort("high", ("ultra", "low", "medium"), capabilities_known=True)
        == "medium"
    )
    assert (
        _normalize_reasoning_effort("high", ("medium", "ultra", "low"), capabilities_known=True)
        == "medium"
    )
