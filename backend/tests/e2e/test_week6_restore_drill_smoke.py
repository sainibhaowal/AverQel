from __future__ import annotations

import gzip
import hashlib
import subprocess
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_backup_script_supports_dry_run(tmp_path: Path) -> None:
    out_dir = tmp_path / "backups"
    completed = subprocess.run(
        [
            "bash",
            "scripts/backup_postgres.sh",
            "--output-dir",
            str(out_dir),
            "--dry-run",
        ],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "DRY RUN:" in completed.stdout


def test_restore_script_supports_dry_run(tmp_path: Path) -> None:
    backup_file = tmp_path / "sample.sql.gz"
    payload = b"-- synthetic backup payload"
    with gzip.open(backup_file, "wb") as handle:
        handle.write(payload)

    checksum = hashlib.sha256(backup_file.read_bytes()).hexdigest()
    sha_file = backup_file.with_suffix(backup_file.suffix + ".sha256")
    sha_file.write_text(f"{checksum}  {backup_file.name}\n", encoding="utf-8")

    completed = subprocess.run(
        [
            "bash",
            "scripts/restore_postgres.sh",
            "--backup-file",
            str(backup_file),
            "--target-db",
            "knowledge_restore",
            "--drop-and-recreate",
            "--dry-run",
        ],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "DRY RUN:" in completed.stdout
