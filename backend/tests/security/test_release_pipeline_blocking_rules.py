from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_backend_ci_workflow_contains_blocking_gates() -> None:
    workflow = _read(ROOT / ".github/workflows/backend-ci.yml")
    required = (
        "ruff check app tests alembic scripts",
        "black --check app tests alembic scripts",
        "mypy app tests",
        "pytest",
        "bandit -r app -q",
        "pip-audit -s osv -r requirements.txt -r requirements-dev.txt",
    )
    for gate in required:
        assert gate in workflow


def test_backend_release_workflow_has_preflight_and_build_steps() -> None:
    workflow = _read(ROOT / ".github/workflows/backend-release.yml")
    assert "preflight" in workflow
    assert "release_build_images.sh" in workflow
    assert "release_verify.sh --dry-run" in workflow
