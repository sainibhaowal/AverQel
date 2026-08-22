from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_workflow_contains_blocking_gates() -> None:
    workflow = _read(ROOT / ".github/workflows/ci.yml")
    required = (
        "ruff check .",
        "black --check .",
        "mypy .",
        "pytest -q -m unit_no_db --dist=loadgroup",
        "bandit -r app -q",
        "pip-audit -s osv",
        "safety check --full-report",
    )
    for gate in required:
        assert gate in workflow
    assert "continue-on-error: true" not in workflow


def test_backend_release_workflow_has_tagged_build_and_vps_deploy() -> None:
    workflow = _read(ROOT / ".github/workflows/release-backend.yml")
    assert "workflow_run:" in workflow
    assert "CI - Mandatory Quality Gates" in workflow
    assert "release-please" not in workflow.lower()
    assert "backend/Dockerfile.base" in workflow
    assert "release_build_images.sh" in workflow
    assert "refs/tags/$VERSION^{commit}" in workflow
    assert "/opt/averqel/backend" in workflow
    assert "--no-build" in workflow
