import pytest

from app.deepspace.services.runtime_transitions import RuntimePhase, transition_checkpoint


def test_transition_checkpoint_is_sanitized_and_validated() -> None:
    checkpoint = transition_checkpoint(
        previous=RuntimePhase.MODEL_REQUESTED,
        next_phase=RuntimePhase.ACTIONS_VALIDATED,
        turn_index=2,
        details={"tool_count": 3, "secret": "never persisted"},
    )

    assert checkpoint["phase"] == "actions_validated"
    assert checkpoint["transition"] == {"tool_count": 3}


def test_transition_checkpoint_rejects_invalid_edge() -> None:
    with pytest.raises(ValueError, match="Illegal DeepSpace runtime transition"):
        transition_checkpoint(
            previous=RuntimePhase.CONTEXT_ASSEMBLED,
            next_phase=RuntimePhase.EXECUTING,
            turn_index=1,
        )
