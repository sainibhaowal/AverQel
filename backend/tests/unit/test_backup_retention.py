from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def test_backup_pruner_removes_only_expired_managed_backups_and_sidecars(
    tmp_path: Path,
) -> None:
    script = Path(__file__).parents[2] / "scripts" / "prune_backups.py"
    expired = tmp_path / "postgres_knowledge_test_20260901_010203.sql.gz"
    expired_sha = Path(f"{expired}.sha256")
    expired_metadata = Path(f"{expired}.metadata.json")
    recent = tmp_path / "minio_data_20261018_010203.tar.gz"
    unrelated = tmp_path / "do-not-delete.sql.gz"
    symlink_target = tmp_path.parent / "outside-sensitive-file"
    symlink_target.write_text("keep", encoding="utf-8")
    for path in (expired, expired_sha, expired_metadata, recent, unrelated):
        path.write_text("backup", encoding="utf-8")
    (tmp_path / "prod_config_20260901_010203.tar.gz").symlink_to(symlink_target)

    old_time = time.time() - 40 * 24 * 60 * 60
    for path in (expired, expired_sha, expired_metadata, unrelated):
        path.touch()
        os.utime(path, (old_time, old_time))

    dry_run = subprocess.run(
        [sys.executable, str(script), "--output-dir", str(tmp_path), "--retention-days", "30"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Would prune: postgres_knowledge_test_20260901_010203.sql.gz" in dry_run.stdout
    assert expired.exists()
    assert expired_sha.exists()
    assert expired_metadata.exists()

    applied = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output-dir",
            str(tmp_path),
            "--retention-days",
            "30",
            "--apply",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Pruning: postgres_knowledge_test_20260901_010203.sql.gz" in applied.stdout
    assert not expired.exists()
    assert not expired_sha.exists()
    assert not expired_metadata.exists()
    assert recent.exists()
    assert unrelated.exists()
    assert symlink_target.read_text(encoding="utf-8") == "keep"
