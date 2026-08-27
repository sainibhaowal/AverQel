#!/usr/bin/env python3
"""Create a small, public release manifest from normalized desktop assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ASSET_NAMES = (
    "AverQel-linux-amd64.deb",
    "AverQel-linux-x86_64.rpm",
    "AverQel-windows-x64.exe",
    "AverQel-macos-universal.dmg",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--base-url",
        default="https://github.com/sainibhaowal/AverQel/releases/latest/download",
    )
    args = parser.parse_args()

    if not args.version.startswith("v"):
        raise SystemExit("release version must start with v")

    assets: dict[str, dict[str, object]] = {}
    for name in ASSET_NAMES:
        path = args.asset_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"missing or empty release asset: {path}")
        base_url = args.base_url.rstrip("/")
        asset_url = (
            f"{base_url}/{name}"
            if base_url.startswith(("http://", "https://"))
            else f"/{base_url.lstrip('/')}/{name}"
        )
        assets[name] = {
            "url": asset_url,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }

    manifest = {
        "product": "AverQel",
        "version": args.version,
        "git_sha": args.git_sha,
        "assets": assets,
    }
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
