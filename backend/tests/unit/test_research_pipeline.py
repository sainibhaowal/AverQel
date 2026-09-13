from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.deepspace.services.research_pipeline import (
    DeepSpaceResearchPipeline,
    ResearchResult,
    ResearchSource,
)
from app.deepspace.services.url_reader import URLReadResult
from app.providers.services.types import WebSearchResponse, WebSearchResultItem


class _Db:
    def add(self, _value):
        pass

    def flush(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def get(self, _model, _identifier):
        return None


class _SearchProvider:
    def search(self, request):
        return WebSearchResponse(
            query=request.query,
            answer=None,
            results=[
                WebSearchResultItem(
                    "Official update",
                    "https://example.gov/update",
                    "Official current update with facts.",
                    published_date="2026-09-12",
                    source="engine-a, engine-b",
                ),
                WebSearchResultItem(
                    "Independent report",
                    "https://news.example.org/report",
                    "Independent report verifying the update.",
                    published_date="2026-09-11",
                    source="engine-a",
                ),
            ],
        )


@pytest.mark.asyncio
async def test_pipeline_is_model_independent_and_only_promotes_fetched_pages(monkeypatch):
    def fake_read(url, **_kwargs):
        return URLReadResult(
            url,
            "Fetched page",
            "The official update confirms the current policy. Independent reporting confirms the same policy.",
            "text/html",
            False,
            [],
        )

    monkeypatch.setattr("app.deepspace.services.research_pipeline.read_url", fake_read)
    pipeline = DeepSpaceResearchPipeline(
        db=_Db(),
        settings=SimpleNamespace(
            deepspace_url_read_timeout_seconds=15, deepspace_url_read_max_bytes=2_000_000
        ),
    )
    result = await pipeline.run(
        prompt="Search the latest policy update and verify it online",
        auth=SimpleNamespace(tenant_id=uuid4(), user_id=uuid4()),
        conversation_id=uuid4(),
        provider=_SearchProvider(),
        candidate=SimpleNamespace(provider_type="searxng", metadata={}),
    )

    assert len(result.queries) == 5
    assert result.quality["results_considered"] == 2
    assert result.quality["pages_fetched"] == 2
    assert all(source.retrieval_status == "fetched" for source in result.sources)
    assert "[R1]" in result.evidence_context()
    assert (
        pipeline.validate_citations("Supported [R1], invented [R99].", result)
        == "Supported [R1], invented ."
    )


def test_research_intent_is_deterministic():
    assert DeepSpaceResearchPipeline.should_research("Find the latest news online")
    assert DeepSpaceResearchPipeline.should_research("Verify this claim")
    assert not DeepSpaceResearchPipeline.should_research("Explain Python tuples")


def test_research_citation_validation_removes_unsupported_attached_citation():
    source = ResearchSource(
        url="https://example.com/report",
        title="Report",
        snippet="",
        domain="example.com",
        score=1,
        retrieval_status="fetched",
        passages=["The programme launched in Berlin on 12 September 2026."],
    )
    result = ResearchResult(None, [], [source], {}, False, 0)
    answer, audit = DeepSpaceResearchPipeline.validate_answer_claims(
        "The programme launched in Berlin on 12 September 2026. [R1] The programme closed permanently. [R1]",
        result,
    )
    assert "12 September 2026. [R1]" in answer
    assert answer.count("[R1]") == 1
    assert audit == {"checked": 2, "supported": 1, "removed": 1}


def test_cross_source_verification_requires_overlapping_evidence():
    sources = [
        ResearchSource(
            "https://a.example/report",
            "A",
            "",
            "a.example",
            1,
            retrieval_status="fetched",
            passages=[
                "The city approved the clean energy policy in September 2026 after public consultation."
            ],
        ),
        ResearchSource(
            "https://b.example/report",
            "B",
            "",
            "b.example",
            1,
            retrieval_status="fetched",
            passages=[
                "The city approved the clean energy policy in September 2026 following consultation."
            ],
        ),
        ResearchSource(
            "https://c.example/report",
            "C",
            "",
            "c.example",
            1,
            retrieval_status="fetched",
            passages=[
                "The city did not approve the clean energy policy in September 2026 after consultation."
            ],
        ),
    ]
    audit = DeepSpaceResearchPipeline._verify(sources, freshness=False)
    assert audit["pairs_compared"] >= 2
    assert audit["conflicting_sources"] >= 1
    assert any(source.verification_status == "conflicting" for source in sources)
