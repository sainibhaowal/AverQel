from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ingestion.extractors.base import BaseExtractor, ExtractionRequest


@dataclass(slots=True)
class ExtractorRegistry:
    _extractors: list[BaseExtractor] = field(default_factory=list)

    def register(self, extractor: BaseExtractor) -> None:
        self._extractors.append(extractor)

    def resolve(self, request: ExtractionRequest) -> BaseExtractor | None:
        for extractor in self._extractors:
            if extractor.can_handle(request):
                return extractor
        return None

    @property
    def extractors(self) -> tuple[BaseExtractor, ...]:
        return tuple(self._extractors)
