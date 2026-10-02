from __future__ import annotations

import shutil
import subprocess  # nosec B404
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
    # Formats accepted by LibreOffice's Writer/Calc/Impress/Draw import
    # filters. Apple iWork and proprietary WPS binary formats are intentionally
    # not listed: LibreOffice cannot guarantee a faithful page render for them.
    _PDF_EXTENSIONS = frozenset(
        {
            ".doc",
            ".docx",
            ".docm",
            ".dot",
            ".dotx",
            ".dotm",
            ".odt",
            ".ott",
            ".odm",
            ".oth",
            ".rtf",
            ".ppt",
            ".pptx",
            ".pptm",
            ".pot",
            ".potx",
            ".potm",
            ".pps",
            ".ppsx",
            ".ppsm",
            ".odp",
            ".otp",
            ".xls",
            ".xlsx",
            ".xlsm",
            ".xlt",
            ".xltx",
            ".xltm",
            ".xlm",
            ".xla",
            ".xlw",
            ".xlsb",
            ".ods",
            ".ots",
            ".odg",
            ".otg",
            ".odc",
            ".otc",
            ".odf",
            ".otf",
            ".odi",
            ".oti",
        }
    )
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

    def can_render_pdf(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in self._PDF_EXTENSIONS

    def can_convert_to_pdf(self, filename: str) -> bool:
        return self.can_render_pdf(filename)

    @property
    def renderable_extensions(self) -> frozenset[str]:
        return self._PDF_EXTENSIONS

    def convert_to_pdf(self, *, filename: str, payload: bytes) -> bytes:
        """Convert a supported Office/ODF document to a PDF for visual preview."""
        if not self.can_render_pdf(filename):
            raise ApiError(
                code="PREVIEW_UNSUPPORTED",
                message="Visual preview is not available for this file type.",
                status_code=415,
            )
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice is None:
            raise ApiError(
                code="PREVIEW_RENDERER_UNAVAILABLE",
                message="The Office preview renderer is unavailable.",
                status_code=503,
            )
        safe_name = Path(filename).name
        try:
            with tempfile.TemporaryDirectory(prefix="aks-office-preview-") as tmp_dir:
                input_path = Path(tmp_dir) / safe_name
                output_dir = Path(tmp_dir) / "out"
                output_dir.mkdir()
                input_path.write_bytes(payload)
                subprocess.run(  # nosec B603
                    [
                        soffice,
                        "--headless",
                        "--nologo",
                        "--nodefault",
                        "--nofirststartwizard",
                        "--norestore",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(output_dir),
                        str(input_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=self.settings.legacy_conversion_timeout_seconds,
                    env={
                        "HOME": tmp_dir,
                        "TMPDIR": tmp_dir,
                        "LANG": "C.UTF-8",
                        "LC_ALL": "C.UTF-8",
                    },
                    cwd=tmp_dir,
                )
                output_path = output_dir / f"{Path(safe_name).stem}.pdf"
                if not output_path.exists():
                    matches = list(output_dir.glob("*.pdf"))
                    if matches:
                        output_path = matches[0]
                if not output_path.exists():
                    raise ApiError(
                        code="PREVIEW_RENDER_FAILED",
                        message="Office preview conversion produced no PDF.",
                        status_code=422,
                    )
                return output_path.read_bytes()
        except subprocess.TimeoutExpired as exc:
            raise ApiError(
                code="PREVIEW_RENDER_TIMEOUT",
                message="Office preview conversion timed out.",
                status_code=503,
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ApiError(
                code="PREVIEW_RENDER_FAILED",
                message="Office preview conversion failed.",
                status_code=422,
            ) from exc

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
                subprocess.run(  # nosec B603
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
