from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExtractionRequest:
    filename: str
    content_type: str
    payload: bytes


@dataclass(slots=True)
class ExtractionResult:
    text: str
    page_count: int | None
    extraction_method: str
    coverage_score: float
    ocr_used: bool = False
    vision_used: bool = False
    warnings: list[str] = field(default_factory=list)
    layout_blocks: list[dict[str, Any]] = field(default_factory=list)


class BaseExtractor(ABC):
    extraction_method: str
    supported_extensions: frozenset[str]
    supported_mime_types: frozenset[str]

    @abstractmethod
    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        raise NotImplementedError

    def can_handle(self, request: ExtractionRequest) -> bool:
        lowered = request.filename.lower()
        extension = ""
        if "." in lowered:
            extension = lowered[lowered.rfind(".") :]
        return (
            request.content_type in self.supported_mime_types
            or extension in self.supported_extensions
        )
