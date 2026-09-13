"""Model-independent, evidence-first web research for DeepSpace.

This module deliberately performs retrieval before the chat provider is asked
to answer. Models synthesize retained evidence; they are never trusted to
decide whether an explicit research request should search the web.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

from app.deepspace.models.research import DeepSpaceResearchRun, DeepSpaceResearchSource
from app.deepspace.services.browser_reader import read_rendered_url
from app.deepspace.services.url_reader import read_url
from app.providers.services.types import WebSearchRequest, WebSearchResponse, WebSearchResultItem

_INTENT = re.compile(
    r"\b(search|look\s*up|find\s+(?:online|on\s+the\s+web)|latest|current|today|news|verify|fact[ -]?check|research)\b",
    re.I,
)
_FRESH = re.compile(
    r"\b(latest|current|today|recent|news|this\s+(?:week|month|year)|up[- ]to[- ]date)\b", re.I
)
_WORDS = re.compile(r"[\w-]{3,}", re.UNICODE)
_NEGATION = re.compile(r"\b(no|not|never|none|without|false|deny|denied|incorrect|failed)\b", re.I)
_STOP_TERMS = frozenset(
    {
        "and",
        "are",
        "for",
        "from",
        "has",
        "have",
        "into",
        "its",
        "not",
        "that",
        "the",
        "their",
        "this",
        "was",
        "were",
        "with",
    }
)
_OFFICIAL_DOMAINS = (".gov", ".edu", "who.int", "europa.eu", "openai.com", "docs.")


@dataclass(slots=True)
class ResearchSource:
    url: str
    title: str
    snippet: str
    domain: str
    score: float
    published_at: str | None = None
    author: str | None = None
    canonical_url: str | None = None
    engines: str | None = None
    retrieval_status: str = "search_snippet_only"
    verification_status: str = "unverified"
    text: str = ""
    passages: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResearchResult:
    run_id: str | None
    queries: list[str]
    sources: list[ResearchSource]
    quality: dict[str, Any]
    freshness_request: bool
    elapsed_ms: int

    def evidence_context(self) -> str:
        blocks: list[str] = []
        for index, source in enumerate(self.sources, start=1):
            if not source.retrieval_status.startswith("fetched") or not source.passages:
                continue
            date = f" Published: {source.published_at}." if source.published_at else ""
            passages = "\n".join(f"- {passage}" for passage in source.passages[:3])
            blocks.append(
                f"[R{index}] {source.title} ({source.domain})\nURL: {source.url}.{date}\nEvidence:\n{passages}"
            )
        return "\n\n".join(blocks)

    def citations(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f"R{index}",
                "title": source.title,
                "url": source.url,
                "snippet": (source.passages[0] if source.passages else source.snippet)[:800],
                "published_date": source.published_at,
                "source": source.engines or source.domain,
                "retrieval_status": source.retrieval_status,
                "verification_status": source.verification_status,
            }
            for index, source in enumerate(self.sources, start=1)
        ]


class DeepSpaceResearchPipeline:
    """Bounded research pipeline with tenant-scoped durable audit records."""

    def __init__(self, *, db: Any, settings: Any) -> None:
        self.db = db
        self.settings = settings

    @staticmethod
    def should_research(prompt: str) -> bool:
        return bool(_INTENT.search(prompt or ""))

    @staticmethod
    def is_freshness_request(prompt: str) -> bool:
        return bool(_FRESH.search(prompt or ""))

    def plan_queries(self, prompt: str) -> list[str]:
        base = " ".join(prompt.split())[:420]
        return [
            base,
            f"{base} latest news",
            f"{base} official source",
            f"{base} independent reporting",
            f"{base} risks criticism contradictions",
        ]

    async def run(
        self,
        *,
        prompt: str,
        auth: Any,
        conversation_id: uuid.UUID,
        provider: Any,
        candidate: Any,
        request: Any | None = None,
    ) -> ResearchResult:
        started = time.monotonic()
        freshness = self.is_freshness_request(prompt)
        queries = self.plan_queries(prompt)
        run = self._create_run(
            auth=auth, conversation_id=conversation_id, prompt=prompt, freshness=freshness
        )
        candidate_metadata = getattr(candidate, "metadata", {}) or {}
        if not isinstance(candidate_metadata, dict):
            candidate_metadata = {}
        metadata = {
            **candidate_metadata,
            "tenant_id": str(auth.tenant_id),
            "user_id": str(auth.user_id),
        }
        if request is not None:
            metadata["rate_limit_request"] = request
        if freshness:
            metadata["time_range"] = "month"

        async def search(query: str) -> list[WebSearchResultItem]:
            response = cast(
                WebSearchResponse,
                await asyncio.to_thread(
                    provider.search,
                    WebSearchRequest(
                        query=query,
                        max_results=8,
                        timeout_seconds=15,
                        include_answer=False,
                        include_raw_content=False,
                        provider_name=str(getattr(candidate, "provider_type", "searxng")),
                        metadata=metadata,
                    ),
                ),
            )
            return response.results

        batches = await asyncio.gather(
            *(search(query) for query in queries), return_exceptions=True
        )
        candidates: list[ResearchSource] = []
        seen_urls: set[str] = set()
        for batch in batches:
            if isinstance(batch, BaseException):
                continue
            for item in batch:
                normalized = item.url.rstrip("/").lower()
                if normalized in seen_urls:
                    continue
                seen_urls.add(normalized)
                domain = (urlparse(item.url).hostname or "").lower().removeprefix("www.")
                if not domain:
                    continue
                candidates.append(
                    ResearchSource(
                        url=item.url,
                        title=item.title,
                        snippet=item.content,
                        domain=domain,
                        score=0.0,
                        published_at=item.published_date,
                        engines=item.source,
                    )
                )
                if len(candidates) >= max(
                    1, min(int(getattr(self.settings, "deepspace_research_max_candidates", 40)), 40)
                ):
                    break
            if len(candidates) >= max(
                1, min(int(getattr(self.settings, "deepspace_research_max_candidates", 40)), 40)
            ):
                break
        ranked = self._rank(prompt, candidates, freshness)[
            : max(1, min(int(getattr(self.settings, "deepspace_research_fetch_count", 6)) + 2, 10))
        ]

        async def fetch(source: ResearchSource) -> ResearchSource:
            try:
                result = await asyncio.to_thread(
                    read_url,
                    source.url,
                    timeout_seconds=min(
                        20, int(getattr(self.settings, "deepspace_url_read_timeout_seconds", 15))
                    ),
                    max_bytes=int(
                        getattr(self.settings, "deepspace_url_read_max_bytes", 2_000_000)
                    ),
                    allowed_domains=candidate_metadata.get("allowed_domains"),
                )
                source.url, source.title, source.text = (
                    result.url,
                    result.title or source.title,
                    result.text,
                )
                source.published_at = result.published_at or source.published_at
                source.author, source.canonical_url = result.author, result.canonical_url
                source.metadata = {
                    "modified_at": result.modified_at,
                    "section_headings": result.section_headings or [],
                    "tables": result.tables or [],
                }
                source.passages = self._rank_passages(prompt, result.text)[:4]
                source.retrieval_status = "fetched" if source.passages else "empty_page"
                source.engines = source.engines or "url_read"
            except Exception as exc:  # safe fallback: a snippet is never upgraded to evidence
                try:
                    result = await asyncio.to_thread(
                        read_rendered_url,
                        source.url,
                        settings=self.settings,
                        allowed_domains=candidate_metadata.get("allowed_domains"),
                    )
                    source.url, source.title, source.text = (
                        result.url,
                        result.title or source.title,
                        result.text,
                    )
                    source.passages = self._rank_passages(prompt, result.text)[:4]
                    source.retrieval_status = "fetched_browser" if source.passages else "empty_page"
                except Exception:
                    source.error = str(exc)[:300]
            return source

        fetch_count = max(
            1, min(int(getattr(self.settings, "deepspace_research_fetch_count", 6)), 8)
        )
        fetched = await asyncio.gather(*(fetch(source) for source in ranked[:fetch_count]))
        verification = self._verify(fetched, freshness)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        quality = {
            "queries_performed": queries,
            "results_considered": len(candidates),
            "pages_attempted": len(ranked[:fetch_count]),
            "pages_fetched": sum(s.retrieval_status.startswith("fetched") for s in fetched),
            "snippet_only": sum(s.retrieval_status == "search_snippet_only" for s in fetched),
            "freshness_request": freshness,
            "dated_sources": sum(bool(s.published_at) for s in fetched),
            "confirmed_sources": verification["confirmed_sources"],
            "conflicting_sources": verification["conflicting_sources"],
            "verification_pairs_compared": verification["pairs_compared"],
            "elapsed_ms": elapsed_ms,
        }
        # Preserve every considered candidate for auditability; only the
        # fetched subset is ever supplied to the answer model as evidence.
        self._persist(run, auth=auth, sources=candidates, quality=quality)
        return ResearchResult(
            str(getattr(run, "id", "")) or None, queries, fetched, quality, freshness, elapsed_ms
        )

    def _rank(
        self, prompt: str, sources: list[ResearchSource], freshness: bool
    ) -> list[ResearchSource]:
        terms = set(_WORDS.findall(prompt.casefold()))
        used_domains: set[str] = set()
        for source in sources:
            haystack = f"{source.title} {source.snippet}".casefold()
            relevance = sum(term in haystack for term in terms) / max(1, len(terms))
            authority = (
                0.30
                if source.domain.endswith(_OFFICIAL_DOMAINS) or source.domain in _OFFICIAL_DOMAINS
                else 0.0
            )
            dated = 0.12 if source.published_at else (-0.18 if freshness else 0.0)
            engine_bonus = 0.08 if source.engines and "," in source.engines else 0.0
            source.score = relevance + authority + dated + engine_bonus
        ordered = sorted(sources, key=lambda source: source.score, reverse=True)
        for source in ordered:
            if source.domain not in used_domains:
                source.score += 0.10
                used_domains.add(source.domain)
        return sorted(ordered, key=lambda source: source.score, reverse=True)

    @staticmethod
    def _rank_passages(prompt: str, text: str) -> list[str]:
        terms = set(_WORDS.findall(prompt.casefold()))
        chunks = [
            " ".join(part.split())
            for part in re.split(r"\n{2,}|(?<=[.!?])\s{2,}", text)
            if len(part.split()) >= 8
        ]
        return sorted(
            chunks, key=lambda chunk: sum(term in chunk.casefold() for term in terms), reverse=True
        )[:12]

    @staticmethod
    def _verify(sources: list[ResearchSource], freshness: bool) -> dict[str, int]:
        """Conservatively compare independently fetched evidence.

        This deliberately does not call a model: source status must remain
        provider-independent and auditable.  A source is only marked confirmed
        when another domain contains materially overlapping evidence; opposing
        polarity on an overlapping passage is marked conflicting.  This is an
        evidence signal, not a claim of universal truth.
        """
        fetched = [source for source in sources if source.retrieval_status.startswith("fetched")]
        agreement: set[int] = set()
        conflicts: set[int] = set()
        pairs_compared = 0
        for left_index, left in enumerate(fetched):
            left_text = " ".join(left.passages[:3])
            left_terms = set(_WORDS.findall(left_text.casefold()))
            for right_index in range(left_index + 1, len(fetched)):
                right = fetched[right_index]
                if left.domain == right.domain:
                    continue
                right_text = " ".join(right.passages[:3])
                right_terms = set(_WORDS.findall(right_text.casefold()))
                if not left_terms or not right_terms:
                    continue
                overlap = len(left_terms & right_terms) / max(
                    1, min(len(left_terms), len(right_terms))
                )
                if overlap < 0.18:
                    continue
                pairs_compared += 1
                if bool(_NEGATION.search(left_text)) != bool(_NEGATION.search(right_text)):
                    conflicts.update((left_index, right_index))
                else:
                    agreement.update((left_index, right_index))
        for source in sources:
            if not source.retrieval_status.startswith("fetched"):
                source.verification_status = "search_snippet_only"
            elif freshness and not source.published_at:
                source.verification_status = "outdated_or_undated"
            elif fetched.index(source) in conflicts:
                source.verification_status = "conflicting"
            elif fetched.index(source) in agreement:
                source.verification_status = "confirmed_by_independent_sources"
            else:
                source.verification_status = "supported_by_one_source"
        return {
            "confirmed_sources": sum(
                source.verification_status == "confirmed_by_independent_sources"
                for source in sources
            ),
            "conflicting_sources": sum(
                source.verification_status == "conflicting" for source in sources
            ),
            "pairs_compared": pairs_compared,
        }

    def _create_run(
        self, *, auth: Any, conversation_id: uuid.UUID, prompt: str, freshness: bool
    ) -> Any:
        try:
            run = DeepSpaceResearchRun(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                prompt=prompt[:4000],
                is_freshness_request=freshness,
            )
            self.db.add(run)
            self.db.flush()
            return run
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def _persist(
        self, run: Any, *, auth: Any, sources: list[ResearchSource], quality: dict[str, Any]
    ) -> None:
        if run is None:
            return
        try:
            run.status, run.quality_json, run.completed_at = "completed", quality, datetime.now(UTC)
            for ordinal, source in enumerate(sources, start=1):
                self.db.add(
                    DeepSpaceResearchSource(
                        run_id=run.id,
                        tenant_id=auth.tenant_id,
                        ordinal=ordinal,
                        url=source.url,
                        canonical_url=source.canonical_url,
                        domain=source.domain[:255],
                        title=source.title,
                        author=source.author,
                        published_at=source.published_at,
                        fetched_at=(
                            datetime.now(UTC)
                            if source.retrieval_status.startswith("fetched")
                            else None
                        ),
                        retrieval_status=source.retrieval_status,
                        verification_status=source.verification_status,
                        score=source.score,
                        snippet=source.snippet,
                        extracted_text=source.text[:40000] or None,
                        passages_json=[{"text": text} for text in source.passages],
                        metadata_json={
                            "engines": source.engines,
                            "error": source.error,
                            **source.metadata,
                        },
                    )
                )
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass

    def persist_quality_update(self, result: ResearchResult) -> None:
        """Persist post-generation citation-validation metrics without touching sources."""
        if not result.run_id:
            return
        try:
            run = self.db.get(DeepSpaceResearchRun, uuid.UUID(result.run_id))
            if run is None:
                return
            run.quality_json = dict(result.quality)
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass

    @staticmethod
    def validate_citations(answer: str, result: ResearchResult) -> str:
        """Remove only invented research identifiers; retain normal Markdown links."""
        valid = {f"R{index}" for index in range(1, len(result.sources) + 1)}
        return re.sub(
            r"\[R(\d{1,3})\]",
            lambda match: match.group(0) if f"R{match.group(1)}" in valid else "",
            answer,
        )

    @staticmethod
    def validate_answer_claims(answer: str, result: ResearchResult) -> tuple[str, dict[str, int]]:
        """Remove citations that do not support their attached sentence.

        Markdown links are untouched.  We only validate explicit ``[R#]``
        research citations against the fetched passages that the model saw.
        This makes unsupported citations visible rather than laundering them
        into the answer, while preserving the answer itself for the user.
        """
        source_by_id = {f"R{index}": source for index, source in enumerate(result.sources, start=1)}
        checked = supported = removed = 0
        # Keep trailing citations with the sentence that they are intended to
        # support (for example: ``The policy passed. [R1]``).
        pieces = re.findall(r".+?(?:[.!?](?:\s*\[R\d{1,3}\])*|\n|$)", answer, re.S)
        output: list[str] = []
        for piece in pieces:
            ids = re.findall(r"\[R(\d{1,3})\]", piece)
            for ordinal in ids:
                checked += 1
                identifier = f"R{ordinal}"
                source = source_by_id.get(identifier)
                if source and DeepSpaceResearchPipeline._claim_support(piece, source.passages):
                    supported += 1
                    continue
                piece = piece.replace(f"[{identifier}]", "")
                removed += 1
            output.append(piece)
        result.quality["citation_claims_checked"] = checked
        result.quality["citation_claims_supported"] = supported
        result.quality["citation_claims_removed"] = removed
        return "".join(output), {"checked": checked, "supported": supported, "removed": removed}

    @staticmethod
    def _claim_support(claim: str, passages: list[str]) -> bool:
        claim_terms = {
            term
            for term in _WORDS.findall(re.sub(r"\[R\d{1,3}\]", "", claim).casefold())
            if term not in _STOP_TERMS
        }
        if len(claim_terms) < 3 or not passages:
            return False
        for passage in passages:
            passage_terms = {
                term for term in _WORDS.findall(passage.casefold()) if term not in _STOP_TERMS
            }
            # Require the passage to cover a majority of the substantive
            # claim words. A low overlap would let a shared generic noun
            # (for example, "programme") validate an unrelated assertion.
            if len(claim_terms & passage_terms) / len(claim_terms) >= 0.50:
                return True
        return False

    @staticmethod
    def quality_markdown(result: ResearchResult) -> str:
        quality = result.quality
        fetched = int(quality.get("pages_fetched", 0))
        total = int(quality.get("results_considered", 0))
        label = "Current-source research" if result.freshness_request else "Web research"
        return (
            f"\n\n> **{label}** · {len(result.queries)} searches · {total} results considered · "
            f"{fetched} pages fetched · {int(quality.get('elapsed_ms', 0)) / 1000:.1f}s"
        )
