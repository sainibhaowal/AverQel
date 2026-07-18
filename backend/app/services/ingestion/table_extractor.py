"""Table Extractor — extracts tables from PDFs using pdfplumber."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTable:
    page_number: int
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def to_text(self) -> str:
        """Convert table to pipe-separated text for embedding."""
        lines = []
        if self.headers:
            lines.append(" | ".join(self.headers))
            lines.append(" | ".join("---" for _ in self.headers))
        for row in self.rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def to_json(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "headers": self.headers,
            "rows": self.rows,
        }


class TableExtractor:
    """Extracts tables from PDF bytes using pdfplumber."""

    def extract_tables(self, pdf_bytes: bytes) -> list[ExtractedTable]:
        """Extract all tables from a PDF.

        Returns a list of ExtractedTable with page number, headers, and rows.
        Falls back gracefully if pdfplumber is not installed.
        """
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed — table extraction skipped")
            return []

        tables: list[ExtractedTable] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = page.extract_tables() or []
                    for raw_table in page_tables:
                        if not raw_table or len(raw_table) < 2:
                            continue
                        # First row = headers, rest = data
                        headers = [str(cell or "").strip() for cell in raw_table[0]]
                        rows = [
                            [str(cell or "").strip() for cell in row]
                            for row in raw_table[1:]
                        ]
                        tables.append(
                            ExtractedTable(
                                page_number=page_num,
                                headers=headers,
                                rows=rows,
                            )
                        )
        except Exception as exc:
            logger.warning(f"Table extraction failed: {exc}")

        return tables
