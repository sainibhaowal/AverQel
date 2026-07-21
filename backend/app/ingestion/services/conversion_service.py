from __future__ import annotations

import shutil
import subprocess  # nosec: B404
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ApiError


@dataclass(slots=True)
class ConvertedArtifact:
    filename: str
    content_type: str
    payload: bytes
    warnings: list[str]


class ConversionService:
    _TARGET_MAP: dict[str, tuple[str, str]] = {
        ".doc": (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ".ppt": (
            "pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ".xls": (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def can_convert(self, filename: str) -> bool:
        extension = Path(filename).suffix.lower()
        return extension in self._TARGET_MAP

    def convert_legacy(self, *, filename: str, payload: bytes) -> ConvertedArtifact:
        extension = Path(filename).suffix.lower()
        if extension not in self._TARGET_MAP:
            raise ApiError(
                code="LEGACY_CONVERSION_UNSUPPORTED",
                message="File is not a supported legacy Office format.",
                status_code=400,
            )

        if not self.settings.legacy_conversion_enabled:
            raise ApiError(
                code="LEGACY_CONVERSION_DISABLED",
                message="Legacy Office conversion is disabled.",
                status_code=422,
            )

        target_extension, target_mime = self._TARGET_MAP[extension]
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice is None:
            raise ApiError(
                code="LEGACY_CONVERSION_UNAVAILABLE",
                message="LibreOffice headless binary is not available on worker host.",
                status_code=503,
            )

        safe_name = Path(filename).name
        stem = Path(safe_name).stem or "legacy-input"

        try:
            with tempfile.TemporaryDirectory(prefix="aks-legacy-convert-") as tmp_dir:
                input_path = Path(tmp_dir) / safe_name
                output_dir = Path(tmp_dir) / "out"
                output_dir.mkdir(parents=True, exist_ok=True)

                input_path.write_bytes(payload)
                cmd = [
                    soffice,
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--nofirststartwizard",
                    "--norestore",
                    "--convert-to",
                    target_extension,
                    "--outdir",
                    str(output_dir),
                    str(input_path),
                ]
                env = {
                    "HOME": tmp_dir,
                    "TMPDIR": tmp_dir,
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                }
                subprocess.run(  # nosec: B603
                    cmd,
                    check=True,
                    capture_output=True,
                    timeout=self.settings.legacy_conversion_timeout_seconds,
                    env=env,
                    cwd=tmp_dir,
                )

                output_path = output_dir / f"{stem}.{target_extension}"
                if not output_path.exists():
                    converted = list(output_dir.glob(f"*.{target_extension}"))
                    if converted:
                        output_path = converted[0]

                if not output_path.exists():
                    raise ApiError(
                        code="LEGACY_CONVERSION_FAILED",
                        message="Legacy Office conversion did not produce output.",
                        status_code=422,
                    )

                return ConvertedArtifact(
                    filename=output_path.name,
                    content_type=target_mime,
                    payload=output_path.read_bytes(),
                    warnings=["legacy_conversion_applied"],
                )
        except subprocess.TimeoutExpired as exc:
            raise ApiError(
                code="LEGACY_CONVERSION_TIMEOUT",
                message="Legacy Office conversion timed out.",
                status_code=503,
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ApiError(
                code="LEGACY_CONVERSION_FAILED",
                message="Legacy Office conversion failed.",
                status_code=422,
            ) from exc
