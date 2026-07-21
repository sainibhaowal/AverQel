from app.deepspace.autonomy import AutonomyController, GoalContract


def test_coding_goal_cannot_finish_without_artifact_and_verification() -> None:
    controller = AutonomyController(GoalContract.from_request("Fix the failing test in app.py"))
    controller.observe({"tool_name": "read_file", "success": True, "output": "source"})

    decision = controller.completion(final_text="I fixed it")

    assert decision.kind.value == "continue"
    assert "artifact" in decision.reason


def test_coding_goal_finishes_only_after_change_and_passing_test() -> None:
    controller = AutonomyController(GoalContract.from_request("Implement the parser"))
    controller.set_isolation_ready(True)
    controller.observe(
        {
            "tool_name": "edit_file",
            "success": True,
            "output": "Successfully edited parser.py",
            "changed_files": ["parser.py"],
            "artifact_changed": True,
        }
    )
    controller.observe(
        {
            "tool_name": "bash",
            "success": True,
            "output": "3 passed in 0.42s",
            "verification": True,
            "verification_pass": True,
        }
    )
    controller.observe(
        {
            "tool_name": "bash",
            "tool_input": {"command": "git diff --check"},
            "success": True,
            "output": "",
        }
    )

    assert controller.completion(final_text="Implemented and verified").kind.value == "finish"


def test_failed_verification_requests_repair_then_stops_after_budget() -> None:
    controller = AutonomyController(GoalContract.from_request("Fix the failing test"), max_repairs=1)

    first = controller.observe(
        {"tool_name": "bash", "success": False, "output": "1 failed, 2 passed"}
    )
    second = controller.observe(
        {"tool_name": "bash", "success": False, "output": "1 failed, 2 passed"}
    )

    assert first.kind.value == "repair"
    assert second.kind.value == "stop"


def test_repeated_action_without_new_evidence_requests_replan() -> None:
    controller = AutonomyController(GoalContract.from_request("Inspect the repository"))
    for _ in range(3):
        decision = controller.observe(
            {"tool_name": "read_file", "success": True, "output": "same content"}
        )

    assert decision.kind.value == "replan"


def test_unsafe_evidence_requires_human() -> None:
    controller = AutonomyController(GoalContract.from_request("Update the deployment"))

    decision = controller.observe(
        {
            "tool_name": "bash",
            "success": False,
            "output": "blocked",
            "error_kind": "security_block",
        }
    )

    assert decision.kind.value == "ask_human"


def test_declared_verification_command_is_required() -> None:
    controller = AutonomyController(
        GoalContract.from_request("Implement parser", verification_commands=("pytest tests/parser",))
    )
    controller.set_isolation_ready(True)
    controller.observe(
        {
            "tool_name": "edit_file",
            "success": True,
            "output": "edited",
            "changed_files": ["parser.py"],
            "artifact_changed": True,
        }
    )
    controller.observe(
        {
            "tool_name": "bash",
            "tool_input": {"command": "pytest tests/other -q"},
            "success": True,
            "output": "1 passed",
        }
    )

    assert "declared verification" in controller.completion(final_text="done").reason
