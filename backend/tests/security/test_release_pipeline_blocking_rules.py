from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.unit_no_db


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


def test_ci_runs_safety_in_a_separate_environment() -> None:
    workflow = yaml.load(_read(ROOT / ".github/workflows/ci.yml"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["backend-quality"]["steps"]
    install = next(
        step["run"] for step in steps if step.get("name") == "Install Python dependencies"
    )
    run = next(
        step["run"]
        for step in steps
        if step.get("name") == "Run backend quality and security gates in parallel"
    )
    assert 'python -m venv "$RUNNER_TEMP/safety-venv"' in install
    assert (
        '"$RUNNER_TEMP/safety-venv/bin/pip" install --no-compile --prefer-binary safety==3.8.1'
        in install
    )
    assert 'if [[ "$gate" == safety ]]; then' in run
    assert 'export PATH="$RUNNER_TEMP/safety-venv/bin:$PATH"' in run
    assert 'run-backend-gate.sh" "$gate"' in run


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


def test_release_validates_packages_before_creating_the_tag() -> None:
    workflow = _read(ROOT / ".github/workflows/release-semantic.yml")

    assert workflow.count('python3 - "$PACKAGE_PATH" "$APPSTREAM_PATH"') == 1
    assert (
        workflow.index("Create checksummed release assets and manifest")
        < workflow.index("Create or verify release tag")
        < workflow.index("Create GitHub release with desktop downloads")
    )


def test_vps_deployment_is_manual_and_gated_by_image_tests() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")
    assert "workflow_dispatch:" in workflow
    assert "backend/Dockerfile.base" in workflow
    assert "release_build_images.sh" in workflow
    assert "Smoke-test built image contents" in workflow
    assert "Publish tested images to GHCR" in workflow
    assert "/opt/averqel/backend" in workflow
    assert "Encode checked-in production Compose" in workflow
    assert "COMPOSE_B64" in workflow
    assert '--project-directory "$VPS_BACKEND_DIR"' in workflow
    assert "DEPLOY_COMPOSE_FILE" in workflow
    assert "--no-build" in workflow
    assert "--remove-orphans" in workflow
    assert "MODELS_DIR" in workflow
    assert "Keep the previous release image so rollback is immediate." in workflow
    assert "AVERQEL_IMAGE_TAG" in workflow


def test_vps_secret_validation_uses_environment_values() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")
    validation_step = workflow.split("- name: Validate deployment secrets", 1)[1].split(
        "- name: Validate SSH private-key format", 1
    )[0]

    assert "VPS_HOST: ${{ secrets.VPS_HOST }}" in validation_step
    assert 'test -n "${VPS_HOST:-}"' in validation_step
    assert "${{ secrets.VPS_HOST }}" not in validation_step.split("run: |", 1)[1]
    assert "${{ secrets.VPS_SSH_KEY }}" not in validation_step.split("run: |", 1)[1]


def test_vps_deployment_rejects_stale_main_commits() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")

    assert 'MAIN_SHA="$(git rev-parse FETCH_HEAD)"' in workflow
    assert 'if [[ "$SHA" != "$MAIN_SHA" ]]' in workflow
    assert "re-running this older run would deploy stale frontend code" in workflow
    assert "Recheck main immediately before deployment" in workflow
    assert 'CURRENT_MAIN_SHA="$(git rev-parse FETCH_HEAD)"' in workflow
    assert 'if [[ "$CURRENT_MAIN_SHA" != "$EXPECTED_SHA" ]]' in workflow
    assert (
        workflow.index("Publish tested images to GHCR")
        < workflow.index("Recheck main immediately before deployment")
        < workflow.index("SSH deploy without touching VPS-owned files")
    )
    assert 'BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' in workflow
    assert "build_timestamp: ${{ steps.resolve.outputs.build_timestamp }}" in workflow


def test_vps_frontend_image_version_and_revision_are_verified() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")

    assert "GIT_VERSION=${{ needs.resolve-source.outputs.release_version }}" in workflow
    assert "GIT_SHA=${{ needs.resolve-source.outputs.sha }}" in workflow
    assert "org.opencontainers.image.revision" in workflow
    assert "/app/.next/server /app/.next/static" in workflow
    assert "docker inspect averqel-frontend --format" in workflow
    assert "Frontend is running $RUNNING_FRONTEND_VERSION from $RUNNING_FRONTEND_SHA" in workflow
    assert 'PUBLIC_FRONTEND_RESPONSE="$(curl --fail --location' in workflow
    assert 'grep -Fq "$VERSION" <<< "$PUBLIC_FRONTEND_RESPONSE"' in workflow
    assert 'grep -Fq "${SHA:0:7}" <<< "$PUBLIC_FRONTEND_RESPONSE"' in workflow
    assert 'SKIP_ROLLBACK="1"' in workflow
    assert "Built frontend served its homepage successfully" in workflow
    assert "did not serve its homepage within 60 seconds" in workflow
    assert "--publish 127.0.0.1::1030" in workflow
    assert 'docker exec "$FRONTEND_SMOKE_CONTAINER" node -e' in workflow
    assert "Built frontend loopback health check returned HTTP " in workflow
    assert "Built frontend cannot reach its own loopback listener" in workflow


def test_frontend_readiness_is_checked_before_compose_wait_completes() -> None:
    compose = yaml.load(_read(ROOT / "backend/docker-compose.prod.yml"), Loader=yaml.BaseLoader)
    frontend = compose["services"]["frontend"]
    healthcheck = frontend["healthcheck"]

    assert frontend["environment"]["HOSTNAME"] == "0.0.0.0"
    assert healthcheck["test"][0:3] == ["CMD", "node", "-e"]
    assert "http://127.0.0.1:1030/" in healthcheck["test"][3]
    assert "GET / returned HTTP " in healthcheck["test"][3]
    assert "GET / failed: " in healthcheck["test"][3]
    assert healthcheck["start_period"] == "30s"
    dockerfile = _read(ROOT / "frontend/Dockerfile")
    assert "HOSTNAME=0.0.0.0" in dockerfile
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")
    assert "compose up -d --no-build --wait --wait-timeout 180\n" in workflow


def test_failed_frontend_health_and_failed_rollback_are_reported() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")
    deploy_script = workflow.split("script: |", 1)[1]

    assert 'report_frontend_health "before rollback"' in deploy_script
    assert "State.Health.Log" in deploy_script
    assert "oom_killed={{.State.OOMKilled}}" in deploy_script
    assert "Automatic rollback did not restore a healthy release" in deploy_script
    assert 'report_frontend_health "after failed rollback"' in deploy_script
    assert deploy_script.index('report_frontend_health "before rollback"') < deploy_script.index(
        "Deployment failed; restoring previous release"
    )


def test_cleanup_happens_after_public_health_checks_without_prune_commands() -> None:
    workflow = _read(ROOT / ".github/workflows/deploy-vps.yml")
    deploy_script = workflow.split("script: |", 1)[1]

    assert (
        deploy_script.index("PUBLIC_FRONTEND_RESPONSE=")
        < deploy_script.index("--remove-orphans")
        < deploy_script.index("docker image rm")
    )
    for forbidden in (
        "docker system prune",
        "docker builder prune",
        "docker image prune",
        "docker volume prune",
    ):
        assert forbidden not in deploy_script


def test_vps_deployment_shell_scripts_parse() -> None:
    workflow = yaml.load(_read(ROOT / ".github/workflows/deploy-vps.yml"), Loader=yaml.BaseLoader)
    steps = [
        *workflow["jobs"]["resolve-source"]["steps"],
        *workflow["jobs"]["build-and-test-images"]["steps"],
        *workflow["jobs"]["deploy-vps"]["steps"],
    ]
    scripts = [
        step["run"]
        for step in steps
        if step.get("name")
        in {
            "Resolve current main version and build metadata",
            "Smoke-test built image contents",
            "Recheck main immediately before deployment",
        }
    ]
    scripts.append(
        next(
            step["with"]["script"]
            for step in steps
            if step.get("name") == "SSH deploy without touching VPS-owned files"
        )
    )

    assert len(scripts) == 4
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n"], input=script, capture_output=True, check=False, text=True
        )
        assert result.returncode == 0, result.stderr


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


def test_livekit_binary_uses_the_fixed_go_toolchain() -> None:
    rebuild = _read(ROOT / "backend/ops/livekit/rebuild.sh")
    build_docs = _read(ROOT / "backend/ops/livekit/BUILD.md")
    builder_image = (
        "golang:1.27.3-bookworm@sha256:"
        "972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5"
    )

    assert builder_image in rebuild
    assert "go version go1.27.3 linux/amd64" in rebuild
    assert "grep -Fq go1.27.3 /out/build-info.txt" in rebuild
    assert "CVE-2026-111943" in build_docs
    assert "Go `1.27.3`" in build_docs


def test_release_download_monitor_follows_github_redirects() -> None:
    workflow = _read(ROOT / ".github/workflows/monitor-downloads.yml")

    assert workflow.count("curl --fail --location --silent --show-error") == 2
