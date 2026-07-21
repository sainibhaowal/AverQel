from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from app.core.config import Settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RenderedPdfPage:
    page_number: int
    image_bytes: bytes
    width: int
    height: int


class PdfRenderService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def render_pdf_pages(
        self,
        *,
        payload: bytes,
        page_numbers: list[int] | None = None,
    ) -> list[RenderedPdfPage]:
        try:
            import pypdfium2 as pdfium  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="OCR_UNAVAILABLE",
                message="pypdfium2 is required for PDF image rendering.",
                status_code=503,
            ) from exc

        try:
            pdf = pdfium.PdfDocument(payload)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="PDF_PARSE_FAILED",
                message="Failed to parse PDF for OCR rendering.",
                status_code=422,
            ) from exc

        try:
            total_pages = len(pdf)
            if total_pages <= 0:
                raise ApiError(
                    code="PDF_PARSE_FAILED",
                    message="PDF contains no renderable pages.",
                    status_code=422,
                )

            if total_pages > self.settings.ocr_max_pages and page_numbers is None:
                raise ApiError(
                    code="OCR_PAGE_LIMIT_EXCEEDED",
                    message="OCR page processing limit exceeded.",
                    status_code=422,
                    details={"max_pages": self.settings.ocr_max_pages},
                )

            if page_numbers is None:
                targets = list(range(1, total_pages + 1))
            else:
                seen: set[int] = set()
                targets = []
                for page_number in page_numbers:
                    if page_number not in seen:
                        seen.add(page_number)
                        targets.append(page_number)

            if len(targets) > self.settings.ocr_max_pages:
                raise ApiError(
                    code="OCR_PAGE_LIMIT_EXCEEDED",
                    message="OCR page processing limit exceeded.",
                    status_code=422,
                    details={"max_pages": self.settings.ocr_max_pages},
                )

            for page_number in targets:
                if page_number < 1 or page_number > total_pages:
                    raise ApiError(
                        code="PDF_PARSE_FAILED",
                        message="Requested page number is out of range.",
                        status_code=422,
                        details={
                            "page_number": page_number,
                            "total_pages": total_pages,
                        },
                    )

            rendered: list[RenderedPdfPage] = []
            scale = max(self.settings.pdf_image_dpi, 72) / 72.0

            for page_number in targets:
                page_idx = page_number - 1
                try:
                    page = pdf[page_idx]
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "PDF page render failed.",
                        exc_info=exc,
                        extra={"page_number": page_number},
                    )
                    raise ApiError(
                        code="PDF_PARSE_FAILED",
                        message="Failed to render PDF page.",
                        status_code=422,
                        details={"page_number": page_number},
                    ) from exc

                output = BytesIO()
                try:
                    image.save(output, format="PNG")
                    rendered.append(
                        RenderedPdfPage(
                            page_number=page_number,
                            image_bytes=output.getvalue(),
                            width=image.width,
                            height=image.height,
                        )
                    )
                finally:
                    output.close()

            return rendered
        finally:
            pdf.close()
