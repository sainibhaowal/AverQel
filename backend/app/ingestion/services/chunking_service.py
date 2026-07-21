from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(slots=True)
class ChunkPart:
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    metadata: dict[str, int | str]


class ChunkingService:
    def chunk(
        self,
        text: str,
        *,
        chunk_size: int = 800,
        overlap: int = 100,
        min_length: int = 40,
        mode: str = "prose",
        source_metadata: dict[str, int | str] | None = None,
    ) -> list[ChunkPart]:
        if not text:
            return []
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")

        parts: list[ChunkPart] = []
        current_h1 = ""
        current_h2 = ""
        current_h3 = ""

        index = 0
        current_chunk_text = ""
        chunk_start = -1

        # Generator for paragraphs with exact original offsets
        def get_paragraphs(t: str) -> Iterator[tuple[int, int, str]]:
            start = 0
            for match in re.finditer(r"\n{2,}", t):
                end = match.start()
                yield start, end, t[start:end]
                start = match.end()
            if start < len(t):
                yield start, len(t), t[start:]

        for start, _end, p_text in get_paragraphs(text):
            stripped = p_text.strip()
            if not stripped:
                continue

            # Track Markdown Headers or common scientific section headers
            lines = stripped.split("\n")
            first_line = lines[0].strip()

            # 1. Traditional Markdown Headers
            if first_line.startswith("# "):
                current_h1 = first_line[2:].strip()
                current_h2 = ""
                current_h3 = ""
            elif first_line.startswith("## "):
                current_h2 = first_line[3:].strip()
                current_h3 = ""
            elif first_line.startswith("### "):
                current_h3 = first_line[4:].strip()
            # 2. Heuristic for Scientific Section Headers (e.g., "7 References" or "REFERENCES")
            else:
                header_match = re.search(
                    r"^(?:\d+\.?\s+)?(References|Bibliography|Appendix|Abstract|Introduction)$",
                    first_line,
                    re.IGNORECASE,
                )
                if header_match:
                    current_h1 = header_match.group(1).capitalize()
                    current_h2 = ""
                    current_h3 = ""

            if chunk_start == -1:
                chunk_start = start

            current_chunk_text += p_text + "\n\n"

            # Semantic Split Boundary OR Force split if too large
            while len(current_chunk_text) >= chunk_size:
                # 1. Try to find a logical split point within the chunk (e.g., period followed by newline or space)
                split_at = -1
                search_region = current_chunk_text[: chunk_size + overlap]

                # Look for sentence endings near the chunk_size
                for match in reversed(list(re.finditer(r"\.[\s\n]", search_region))):
                    if match.start() > chunk_size // 2:
                        split_at = match.end()
                        break

                # If no sentence ending, look for single newline
                if split_at == -1:
                    for match in reversed(list(re.finditer(r"\n", search_region))):
                        if match.start() > chunk_size // 2:
                            split_at = match.end()
                            break

                # If still no split at, just hard cut at chunk_size
                if split_at == -1:
                    split_at = chunk_size

                c_text = current_chunk_text[:split_at].strip()
                if len(c_text) >= min_length:
                    meta = self._build_metadata(
                        mode=mode,
                        base={"strategy": "semantic"},
                        source_metadata=source_metadata,
                    )
                    if current_h1 and not meta.get("header_1"):
                        meta["header_1"] = current_h1
                    if current_h2 and not meta.get("header_2"):
                        meta["header_2"] = current_h2
                    if current_h3 and not meta.get("header_3"):
                        meta["header_3"] = current_h3

                    parts.append(
                        ChunkPart(
                            chunk_index=index,
                            content=c_text,
                            char_start=chunk_start if chunk_start != -1 else start,
                            char_end=(chunk_start if chunk_start != -1 else start)
                            + len(c_text),
                            metadata=meta,
                        )
                    )
                    index += 1

                # Setup next chunk using overlap
                remainder = current_chunk_text[split_at:].strip()
                if overlap > 0 and len(c_text) > overlap:
                    current_chunk_text = c_text[-overlap:] + "\n" + remainder
                else:
                    current_chunk_text = remainder
                chunk_start = -1

        # Remainder
        if current_chunk_text:
            c_text = current_chunk_text.strip()
            if len(c_text) >= min_length or (not parts and c_text):
                meta = self._build_metadata(
                    mode=mode,
                    base={"strategy": "semantic"},
                    source_metadata=source_metadata,
                )
                if current_h1 and not meta.get("header_1"):
                    meta["header_1"] = current_h1
                if current_h2 and not meta.get("header_2"):
                    meta["header_2"] = current_h2
                if current_h3 and not meta.get("header_3"):
                    meta["header_3"] = current_h3

                parts.append(
                    ChunkPart(
                        chunk_index=index,
                        content=c_text,
                        char_start=chunk_start if chunk_start != -1 else start,
                        char_end=(chunk_start if chunk_start != -1 else start)
                        + len(c_text),
                        metadata=meta,
                    )
                )

        return parts

    def chunk_structured(
        self,
        *,
        blocks: list[dict[str, object]],
        chunk_size: int = 800,
        overlap: int = 100,
        min_length: int = 40,
    ) -> list[ChunkPart]:
        ordered: list[ChunkPart] = []
        index = 0
        char_cursor = 0

        current_h1 = ""
        current_h2 = ""
        current_h3 = ""

        for block in blocks:
            text = str(block.get("text", "")).strip()
            if not text:
                continue

            # Cross-block header tracking
            lines = text.split("\n")
            first_line = lines[0].strip()

            # 1. Traditional Markdown Headers
            if first_line.startswith("# "):
                current_h1 = first_line[2:].strip()
                current_h2 = ""
                current_h3 = ""
            elif first_line.startswith("## "):
                current_h2 = first_line[3:].strip()
                current_h3 = ""
            elif first_line.startswith("### "):
                current_h3 = first_line[4:].strip()
            # 2. Heuristic for Scientific Section Headers (e.g., "7 References" or "REFERENCES")
            else:
                header_match = re.search(
                    r"^(?:\d+\.?\s+)?(References|Bibliography|Appendix|Abstract|Introduction)$",
                    first_line,
                    re.IGNORECASE,
                )
                if header_match:
                    current_h1 = header_match.group(1).capitalize()
                    current_h2 = ""
                    current_h3 = ""

            block_type = str(block.get("block_type", "prose")).lower()
            mode = self._mode_from_block_type(block_type)
            coordinates = block.get("coordinates", {})
            page_number = block.get("page_number")

            base_meta: dict[str, int | str] = {"block_type": block_type}
            if current_h1:
                base_meta["header_1"] = current_h1
            if current_h2:
                base_meta["header_2"] = current_h2
            if current_h3:
                base_meta["header_3"] = current_h3

            if isinstance(page_number, int):
                base_meta["page_number"] = page_number
            if isinstance(coordinates, dict):
                for key in ("x", "y", "w", "h"):
                    value = coordinates.get(key)
                    if isinstance(value, int | float):
                        base_meta[f"coord_{key}"] = str(value)

            nested = self.chunk(
                text,
                chunk_size=chunk_size,
                overlap=overlap,
                min_length=min_length,
                mode=mode,
                source_metadata=base_meta,
            )
            for part in nested:
                ordered.append(
                    ChunkPart(
                        chunk_index=index,
                        content=part.content,
                        char_start=char_cursor + part.char_start,
                        char_end=char_cursor + part.char_end,
                        metadata=part.metadata,
                    )
                )
                index += 1
            char_cursor += len(text) + 1
        return ordered

    @staticmethod
    def _mode_from_block_type(block_type: str) -> str:
        if block_type in {"table", "spreadsheet"}:
            return "table"
        if block_type in {"slide", "title"}:
            return "slide"
        if block_type in {"code"}:
            return "code"
        return "prose"

    @staticmethod
    def _build_metadata(
        *,
        mode: str,
        base: dict[str, int | str],
        source_metadata: dict[str, int | str] | None,
    ) -> dict[str, int | str]:
        metadata = {**base, "mode": mode}
        if source_metadata:
            metadata.update(source_metadata)
        return metadata
