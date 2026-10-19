#!/usr/bin/env python3
"""Prune old AverQel backup archives and their sidecars from one directory."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

BACKUP_NAME_PATTERNS = (
    re.compile(r"^postgres_[A-Za-z0-9._-]+_\d{8}_\d{6}\.sql\.gz$"),
    re.compile(r"^minio_data_\d{8}_\d{6}\.tar\.gz$"),
    re.compile(r"^prod_config_\d{8}_\d{6}\.tar\.gz$"),
)


def is_managed_backup(path: Path) -> bool:
    return any(pattern.fullmatch(path.name) for pattern in BACKUP_NAME_PATTERNS)


def prune_backups(*, output_dir: Path, retention_days: int, apply: bool) -> list[Path]:
    resolved_dir = output_dir.resolve(strict=True)
    if not resolved_dir.is_dir():
        raise ValueError("backup output path must be a directory")
    if retention_days < 1:
        raise ValueError("retention days must be at least 1")

    cutoff = time.time() - retention_days * 24 * 60 * 60
    removed: list[Path] = []
    for backup in sorted(resolved_dir.iterdir()):
        if backup.is_symlink() or not backup.is_file() or not is_managed_backup(backup):
            continue
        if backup.stat().st_mtime >= cutoff:
            continue

        family = [backup, Path(f"{backup}.sha256"), Path(f"{backup}.metadata.json")]
        for member in family:
            if member.is_symlink() or not member.is_file():
                continue
            print(f"{'Pruning' if apply else 'Would prune'}: {member.name}")
            if apply:
                member.unlink()
            removed.append(member)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete expired managed backup files. Without this option, only report them.",
    )
    args = parser.parse_args()
    try:
        prune_backups(
            output_dir=args.output_dir,
            retention_days=args.retention_days,
            apply=args.apply,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
