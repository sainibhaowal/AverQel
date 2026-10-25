from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.unit_no_db


def _yaml(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _workflow() -> dict:
    return _yaml(ROOT / ".github/workflows/deploy-vps.yml")


def _all_steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_deploy_uses_only_the_exact_current_main_commit() -> None:
    workflow = _workflow()
    resolve = workflow["jobs"]["resolve-source"]["steps"]
    resolve_script = next(
        step["run"]
        for step in resolve
        if step.get("name") == "Resolve current main version and build metadata"
    )

    assert 'test "$GITHUB_REF" = "refs/heads/main"' in resolve[0]["run"]
    assert 'MAIN_SHA="$(git rev-parse FETCH_HEAD)"' in resolve_script
    assert 'if [[ "$SHA" != "$MAIN_SHA" ]]' in resolve_script

    names = [step.get("name") for step in _all_steps(workflow)]
    assert (
        names.index("Publish tested images to GHCR")
        < names.index("Recheck main immediately before deployment")
        < names.index("SSH deploy without touching VPS-owned files")
    )
    recheck = next(
        step["run"]
        for step in _all_steps(workflow)
        if step.get("name") == "Recheck main immediately before deployment"
    )
    assert 'CURRENT_MAIN_SHA="$(git rev-parse FETCH_HEAD)"' in recheck
    assert 'if [[ "$CURRENT_MAIN_SHA" != "$EXPECTED_SHA" ]]' in recheck


def test_frontend_image_is_built_and_verified_for_the_selected_sha() -> None:
    workflow_text = (ROOT / ".github/workflows/deploy-vps.yml").read_text(encoding="utf-8")
    assert "GIT_VERSION=${{ needs.resolve-source.outputs.release_version }}" in workflow_text
    assert "GIT_SHA=${{ needs.resolve-source.outputs.sha }}" in workflow_text
    assert "org.opencontainers.image.revision" in workflow_text
    assert "/app/.next/server /app/.next/static" in workflow_text
    assert "docker inspect averqel-frontend --format" in workflow_text
    assert 'grep -Fq "${SHA:0:7}" <<< "$PUBLIC_FRONTEND_RESPONSE"' in workflow_text


def test_production_frontend_has_a_compose_readiness_check() -> None:
    compose = _yaml(ROOT / "backend/docker-compose.prod.yml")
    healthcheck = compose["services"]["frontend"]["healthcheck"]

    assert healthcheck["test"][0:3] == ["CMD", "node", "-e"]
    assert "http://127.0.0.1:1030/" in healthcheck["test"][3]
    assert healthcheck["start_period"] == "30s"
    assert healthcheck["retries"] == "12"


def test_cleanup_waits_for_public_health_and_never_prunes_volumes_or_images() -> None:
    workflow = _workflow()
    deploy = next(
        step["with"]["script"]
        for step in _all_steps(workflow)
        if step.get("name") == "SSH deploy without touching VPS-owned files"
    )

    assert (
        deploy.index("PUBLIC_FRONTEND_RESPONSE=")
        < deploy.index("--remove-orphans")
        < deploy.index("docker image rm")
    )
    for forbidden in (
        "docker system prune",
        "docker builder prune",
        "docker image prune",
        "docker volume prune",
    ):
        assert forbidden not in deploy


def test_deployment_shell_scripts_parse() -> None:
    workflow = _workflow()
    scripts = [
        step["run"]
        for step in _all_steps(workflow)
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
            for step in _all_steps(workflow)
            if step.get("name") == "SSH deploy without touching VPS-owned files"
        )
    )

    assert len(scripts) == 4
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n"], input=script, capture_output=True, check=False, text=True
        )
        assert result.returncode == 0, result.stderr
