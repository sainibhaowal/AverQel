from __future__ import annotations

import re
from enum import Enum
from typing import Final


class QueryType(str, Enum):
    FACTUAL = "factual"
    COMPARISON = "comparison"
    SUMMARIZATION = "summarization"
    EXPLORATORY = "exploratory"
    ANALYTICAL = "exploratory"
    VERIFICATION = "verification"
    SYNTHESIS = "synthesis"
    ACTION = "action"


_ACTION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(crawl|index|sync|refresh|update|fetch|pull from|load data from|start indexing)\b"
    ),
    re.compile(
        r"\b(github|google drive|notion|slack|web crawler|website|url|http|https)\b"
    ),
)


_COMPARISON_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(compare|comparison|difference|differences|versus|vs\.?|better|worse|similarities|contrast)\b"
    ),
)

_SUMMARIZATION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(summarize|summary|tldr|tl;dr|overview|briefly|gist|short summary)\b"
    ),
    re.compile(r"^what is the main idea\b"),
    re.compile(r"^can you summarize\b"),
    re.compile(r"^give me a summary\b"),
)

_VERIFICATION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(is it true|verify|validate|prove|fact[- ]check|does the document say|is this correct)\b"
    ),
    re.compile(r"^is this\b"),
    re.compile(r"^is it\b"),
    re.compile(r"^does the document\b"),
    re.compile(r"^does this\b"),
)

_SYNTHESIS_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(synthesize|combine|connect|relate|relationship between|implications of|overall impact|big picture)\b"
    ),
)

_EXPLORATORY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(why|explain|how come|explore|elaborate|details on|tell me more)\b"),
)


class QueryClassifier:
    """
    Fast heuristic query classifier for prompt routing.

    This avoids an extra LLM call and provides stable low-latency routing
    for common query intents.
    """

    @staticmethod
    def _normalize(query: str) -> str:
        query = query.strip().lower()
        query = re.sub(r"\s+", " ", query)
        return query

    @staticmethod
    def _matches_any(query: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
        return any(pattern.search(query) for pattern in patterns)

    @classmethod
    def classify(cls, query: str) -> QueryType:
        q = cls._normalize(query)

        if not q:
            return QueryType.FACTUAL

        if cls._matches_any(q, _ACTION_PATTERNS):
            return QueryType.ACTION

        if cls._matches_any(q, _COMPARISON_PATTERNS):
            return QueryType.COMPARISON

        if cls._matches_any(q, _SUMMARIZATION_PATTERNS):
            return QueryType.SUMMARIZATION

        if cls._matches_any(q, _VERIFICATION_PATTERNS):
            return QueryType.VERIFICATION

        if cls._matches_any(q, _SYNTHESIS_PATTERNS):
            return QueryType.SYNTHESIS

        if cls._matches_any(q, _EXPLORATORY_PATTERNS):
            return QueryType.EXPLORATORY

        return QueryType.FACTUAL
