import io
import zipfile
from dataclasses import dataclass

from app.core.errors import ApiError


@dataclass(slots=True)
class ArchiveSecurityConfig:
    max_decompressed_size: int = 150 * 1024 * 1024  # 150MB
    max_decompression_ratio: float = 250.0


class ArchiveSecurityService:
    def __init__(self, config: ArchiveSecurityConfig | None = None) -> None:
        self.config = config or ArchiveSecurityConfig()

    def validate_payload(self, filename: str, payload: bytes) -> None:
        """Validates zipped payloads for zip-slip, archive bombs, and active content."""
        buffer = io.BytesIO(payload)
        if not zipfile.is_zipfile(buffer):
            return

        buffer.seek(0)
        try:
            with zipfile.ZipFile(buffer, "r") as zf:
                total_uncompressed = 0
                compressed_size = len(payload)

                for info in zf.infolist():
                    path_str = info.filename

                    # 1. Zip-Slip Check
                    if path_str.startswith("/") or path_str.startswith("\\") or ".." in path_str:
                        raise ApiError(
                            code="ZIP_SLIP_DETECTED",
                            message="Malicious archive path detected.",
                            status_code=422,
                            details={"path": path_str},
                        )

                    # 2. Active Content / Macro Check (OOXML)
                    lower_path = path_str.lower()
                    if (
                        lower_path.endswith("vbaproject.bin")
                        or "vba" in lower_path
                        or lower_path.endswith(".vbs")
                    ):
                        raise ApiError(
                            code="ACTIVE_CONTENT_DETECTED",
                            message="Office document contains macros or active content.",
                            status_code=422,
                        )

                    # 3. Archive Bomb Checks
                    total_uncompressed += info.file_size
                    if total_uncompressed > self.config.max_decompressed_size:
                        raise ApiError(
                            code="ARCHIVE_BOMB_DETECTED",
                            message="Decompressed archive exceeds maximum safe limits.",
                            status_code=422,
                        )

                if compressed_size > 0:
                    ratio = total_uncompressed / compressed_size
                    if ratio > self.config.max_decompression_ratio:
                        raise ApiError(
                            code="ARCHIVE_BOMB_DETECTED",
                            message="High compression ratio detected, possible archive bomb.",
                            status_code=422,
                        )
        except zipfile.BadZipFile as exc:
            raise ApiError(
                code="CORRUPTED_ARCHIVE",
                message="Archive file is corrupted.",
                status_code=422,
            ) from exc
