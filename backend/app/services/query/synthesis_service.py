from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Final, Literal

from app.services.query.retrieval_service import RetrievedChunk
from app.services.query.snippet_service import SnippetService

logger = logging.getLogger(__name__)

CellStatus = Literal["supported", "partial", "not_found"]

TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-zA-Z0-9]+")
STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "with",
    }
)

SUPPORTED_THRESHOLD: Final[float] = 0.40
PARTIAL_THRESHOLD: Final[float] = 0.15
MAX_EVIDENCE_CHARS: Final[int] = 200


@dataclass(slots=True, frozen=True)
class MatrixCell:
    finding: str
    document: str
    status: CellStatus
    evidence: str = ""
    score: float = 0.0


@dataclass(slots=True, frozen=True)
class SynthesisResult:
    findings: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    cells: list[MatrixCell] = field(default_factory=list)


def _tokenize(text: str) -> set[str]:
    tokens = {token.lower() for token in TOKEN_RE.findall(text)}
    return {token for token in tokens if token and token not in STOPWORDS}


def _score_overlap(finding_tokens: set[str], chunk_tokens: set[str]) -> float:
    if not finding_tokens:
        return 0.0
    overlap = len(finding_tokens & chunk_tokens)
    return overlap / len(finding_tokens)


def _status_from_score(score: float) -> CellStatus:
    if score >= SUPPORTED_THRESHOLD:
        return "supported"
    if score >= PARTIAL_THRESHOLD:
        return "partial"
    return "not_found"


def build_synthesis_matrix(
    chunks: list[RetrievedChunk],
    key_findings: list[str],
) -> SynthesisResult:
    """
    Build a deterministic cross-document synthesis matrix from retrieved chunks
    and user-supplied findings using lightweight lexical overlap scoring.
    """
    if not chunks or not key_findings:
        return SynthesisResult()

    doc_map: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        doc_key = chunk.filename or str(chunk.document_id)
        doc_map.setdefault(doc_key, []).append(chunk)

    documents = sorted(doc_map.keys())
    normalized_findings = [
        finding.strip() for finding in key_findings if finding.strip()
    ]
    cells: list[MatrixCell] = []

    for finding in normalized_findings:
        finding_tokens = _tokenize(finding)

        for doc_name in documents:
            doc_chunks = sorted(
                doc_map[doc_name],
                key=lambda chunk: (
                    str(chunk.document_id),
                    getattr(chunk, "page_number", 0) or 0,
                    str(chunk.chunk_id),
                ),
            )

            best_score = 0.0
            best_snippet = ""

            for chunk in doc_chunks:
                chunk_tokens = _tokenize(chunk.content)
                score = _score_overlap(finding_tokens, chunk_tokens)

                if score > best_score:
                    best_score = score
                    best_snippet = SnippetService.clean(
                        chunk.content, MAX_EVIDENCE_CHARS
                    )

            status = _status_from_score(best_score)

            cells.append(
                MatrixCell(
                    finding=finding,
                    document=doc_name,
                    status=status,
                    evidence=best_snippet if status != "not_found" else "",
                    score=round(best_score, 6),
                )
            )

    return SynthesisResult(
        findings=normalized_findings,
        documents=documents,
        cells=cells,
    )
