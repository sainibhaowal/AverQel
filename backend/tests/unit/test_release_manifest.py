from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/create-release-manifest.py"
ASSET_NAMES = ("AverQel-linux-amd64.deb", "AverQel-windows-x64.exe")


def _run_manifest(
    tmp_path: Path,
    *,
    version: str = "v1.2.13",
    git_sha: str = "a" * 40,
    neosis_version: str = "0.2.0-rc.2",
    neosis_git_sha: str = "b" * 40,
) -> subprocess.CompletedProcess[str]:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir(exist_ok=True)
    for name in ASSET_NAMES:
        (asset_dir / name).write_bytes(f"test asset: {name}".encode())

    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--version",
            version,
            "--git-sha",
            git_sha,
            "--neosis-version",
            neosis_version,
            "--neosis-git-sha",
            neosis_git_sha,
            "--asset-dir",
            str(asset_dir),
            "--output",
            str(tmp_path / "release-manifest.json"),
            "--base-url",
            "https://github.com/sainibhaowal/AverQel/releases/latest/download",
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_manifest_records_asset_hashes_urls_and_component_provenance(
    tmp_path: Path,
) -> None:
    result = _run_manifest(tmp_path)

    assert result.returncode == 0, result.stderr
    manifest_path = tmp_path / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "v1.2.13"
    assert manifest["git_sha"] == "a" * 40
    assert manifest["components"] == {
        "averqel": {"version": "v1.2.13", "git_sha": "a" * 40},
        "neosis": {"version": "0.2.0-rc.2", "git_sha": "b" * 40},
    }
    assert set(manifest["assets"]) == set(ASSET_NAMES)
    for name in ASSET_NAMES:
        content = f"test asset: {name}".encode()
        asset = manifest["assets"][name]
        assert asset["url"].endswith(f"/{name}")
        assert asset["sha256"] == hashlib.sha256(content).hexdigest()
        assert asset["size_bytes"] == len(content)


@pytest.mark.parametrize(
    ("version", "git_sha", "message"),
    [
        ("1.2.13", "a" * 40, "canonical vMAJOR.MINOR.PATCH"),
        ("v1.2.13", "a" * 39, "full lowercase commit SHA"),
    ],
)
def test_manifest_rejects_invalid_release_identity(
    tmp_path: Path, version: str, git_sha: str, message: str
) -> None:
    result = _run_manifest(tmp_path, version=version, git_sha=git_sha)

    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize(
    ("neosis_version", "neosis_git_sha", "message"),
    [
        ("0.2", "b" * 40, "valid SemVer version"),
        ("0.2.0-rc.2", "b" * 39, "full lowercase commit SHA"),
    ],
)
def test_manifest_rejects_invalid_neosis_provenance(
    tmp_path: Path, neosis_version: str, neosis_git_sha: str, message: str
) -> None:
    result = _run_manifest(
        tmp_path,
        neosis_version=neosis_version,
        neosis_git_sha=neosis_git_sha,
    )

    assert result.returncode != 0
    assert message in result.stderr


def test_manifest_fails_when_a_required_package_is_missing(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / ASSET_NAMES[0]).write_bytes(b"Linux package")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--version",
            "v1.2.13",
            "--git-sha",
            "a" * 40,
            "--neosis-version",
            "0.2.0-rc.2",
            "--neosis-git-sha",
            "b" * 40,
            "--asset-dir",
            str(tmp_path / "assets"),
            "--output",
            str(tmp_path / "release-manifest.json"),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "missing or empty release asset" in result.stderr


def test_release_workflow_pins_neosis_and_limits_artifacts_to_linux_and_windows() -> None:
    workflow = (ROOT / ".github/workflows/release-semantic.yml").read_text(encoding="utf-8")

    assert "repository: sainibhaowal/AverQel_NeoSIS" in workflow
    assert "ref: main" in workflow
    assert "outputs.neosis_sha" in workflow
    assert "outputs.neosis_version" in workflow
    assert "platform: [ubuntu-22.04, windows-latest]" in workflow
    prepare_environment = "node applications/desktop/scripts/prepare-neosis-package-env.mjs neosis"
    assert prepare_environment in workflow
    assert workflow.index(prepare_environment) < workflow.index(
        "- name: Build Linux desktop package"
    )
    assert workflow.index(prepare_environment) < workflow.index(
        "- name: Build Windows desktop package"
    )
    assert "macos-latest" not in workflow
    assert "AverQel-linux-amd64.deb" in workflow
    assert "AverQel-windows-x64.exe" in workflow
    assert "AverQel-macos-universal.dmg" not in workflow
    assert "AverQel-linux-x86_64.rpm" not in workflow
    assert 'MAX_PACKAGE_BYTES: "167772160"' in workflow
    assert "VPS_HOST" not in workflow


def test_desktop_pnpm_approves_only_the_reviewed_installer_build_script() -> None:
    policy = (ROOT / "applications/desktop/pnpm-workspace.yaml").read_text(encoding="utf-8")
    config = yaml.safe_load(policy)

    assert config == {
        "packages": ["."],
        "allowBuilds": {"electron-winstaller": True},
    }


def test_manifest_contract_includes_only_current_assets_and_component_provenance() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert '"AverQel-linux-amd64.deb"' in script
    assert '"AverQel-windows-x64.exe"' in script
    assert '"AverQel-macos-universal.dmg"' not in script
    assert '"AverQel-linux-x86_64.rpm"' not in script
    assert '"neosis": {"version": args.neosis_version, "git_sha": args.neosis_git_sha}' in script
