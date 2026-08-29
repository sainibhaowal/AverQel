from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_workflow_contains_blocking_gates() -> None:
    workflow = _read(ROOT / ".github/workflows/ci.yml")
    gates = _read(ROOT / ".github/scripts/run-backend-gate.sh")
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
        assert gate in gates
    assert "ci-passed:" in workflow
    assert "if: always()" in workflow
    assert "continue-on-error: true" not in workflow


def test_ci_runs_only_for_pull_requests() -> None:
    workflow = _read(ROOT / ".github/workflows/ci.yml")
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" not in workflow
    assert "  push:" not in workflow


def test_semantic_release_is_manual_and_does_not_deploy() -> None:
    workflow = _read(ROOT / ".github/workflows/release-semantic.yml")
    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" not in workflow
    assert "release-please" not in workflow.lower()
    assert ".github/scripts/next-semver.sh" in workflow
    assert 'git push origin "$VERSION"' in workflow
    assert "VPS_HOST" not in workflow
    assert "docker build" not in workflow


def test_vps_deployment_is_manual_and_gated_by_image_tests() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")
    assert "workflow_dispatch:" in workflow
    assert "backend/Dockerfile.base" in workflow
    assert "release_build_images.sh" in workflow
    assert "Smoke-test built image contents" in workflow
    assert "Publish tested images to GHCR" in workflow
    assert "/opt/averqel/backend" in workflow
    assert "--no-build" in workflow
    assert "--remove-orphans" in workflow
    assert "MODELS_DIR" in workflow
    assert "Keep the previous release image so rollback is immediate." in workflow
    assert "AVERQEL_IMAGE_TAG" in workflow


def test_vps_trivy_scans_do_not_contend_for_a_shared_cache() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")

    assert "Scan API, worker, and frontend images sequentially" in workflow
    assert "--pkg-types os,library" in workflow
    assert "--vuln-type os,library" not in workflow
    assert "API_PID" not in workflow
    assert "WORKER_PID" not in workflow
    assert "FRONTEND_PID" not in workflow
    assert "scan api > trivy-api.log 2>&1 || API_STATUS=$?" in workflow
    assert "scan worker > trivy-worker.log 2>&1 || WORKER_STATUS=$?" in workflow
    assert "scan frontend > trivy-frontend.log 2>&1 || FRONTEND_STATUS=$?" in workflow


def test_release_download_monitor_follows_github_redirects() -> None:
    workflow = _read(ROOT / ".github/workflows/monitor-downloads.yml")

    assert workflow.count("curl --fail --location --silent --show-error") == 2
