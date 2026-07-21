from app.deepspace.workspace.coding_harness import (
    CodingHarness,
    CodingMissionContract,
)


def test_harness_blocks_network_and_inline_scripts() -> None:
    harness = CodingHarness(CodingMissionContract(objective="fix test"))

    assert harness.validate_command("curl https://example.com")[0] is False
    assert harness.validate_command("python -c 'print(1)'")[0] is False
    assert harness.validate_command("git push origin main")[0] is False


def test_harness_allows_reviewed_local_verification() -> None:
    harness = CodingHarness(CodingMissionContract(objective="fix test"))

    allowed, reason = harness.validate_command("pytest tests/unit -q")

    assert allowed is True
    assert reason is None


def test_harness_enforces_tool_budget() -> None:
    harness = CodingHarness(CodingMissionContract(objective="fix", max_tool_calls=1))

    assert harness.validate_command("git diff --check")[0] is True
    assert harness.validate_command("git status --short") == (
        False,
        "coding tool-call budget exhausted",
    )


def test_harness_restricts_write_paths() -> None:
    harness = CodingHarness(
        CodingMissionContract(objective="fix", allowed_paths=("backend/app",))
    )

    assert harness.validate_path("backend/app/main.py")[0] is True
    assert harness.validate_path("backend/tests/test.py")[0] is False
    assert harness.validate_path("../secrets.env")[0] is False
