from uuid import UUID

from app.providers.services.types import ProviderSelectionCandidate
from app.query.schemas.followups import FollowupSuggestions
from app.query.services.answer_service import AnswerService
from app.query.services.followup_service import FollowupService


def test_followup_service_wraps_answer_service_output(monkeypatch) -> None:
    service = FollowupService(AnswerService("no-result"))

    monkeypatch.setattr(
        service.answer_service,
        "generate_followups",
        lambda **kwargs: ["What changed next?", "Show the evidence."],
    )

    payload = service.generate(
        query_text="Explain the retrieval flow",
        answer_text="The retrieval flow starts with hybrid search.",
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[],
    )

    assert payload == FollowupSuggestions(follow_ups=["What changed next?", "Show the evidence."])


def test_followup_service_metadata_payload_normalizes_items() -> None:
    payload = FollowupService.as_metadata(["  What changed next?  ", "", "Show the evidence."])

    assert payload == {"follow_up_suggestions": ["What changed next?", "Show the evidence."]}


def test_answer_service_followups_extracts_suggestions_block_from_answer_text() -> None:
    service = AnswerService("no-result")

    followups = service.generate_followups(
        query_text="Explain the architectures",
        answer_text=(
            "### Suggestions\n"
            "- What specific efficiency goals were prioritized in each architecture?\n"
            "- How did training strategies influence model scaling?\n"
            "- Which tokenization method proved most effective for performance?\n"
        ),
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[
            ProviderSelectionCandidate(
                provider_type="custom",
                model_name="test-model",
                feature_scope="chat",
                source="tenant",
                base_url="http://mock-api",
            )
        ],
    )

    assert followups == [
        "What specific efficiency goals were prioritized in each architecture?",
        "How did training strategies influence model scaling?",
        "Which tokenization method proved most effective for performance?",
    ]


def test_answer_service_followups_extracts_question_lines_from_answer_text() -> None:
    service = AnswerService("no-result")

    followups = service.generate_followups(
        query_text="Explain the architectures",
        answer_text=(
            "1. What is the most important takeaway?\n"
            "2. Can you show the exact evidence from the documents?\n"
            "3. Can you explain this in more detail?\n"
        ),
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[
            ProviderSelectionCandidate(
                provider_type="custom",
                model_name="test-model",
                feature_scope="chat",
                source="tenant",
                base_url="http://mock-api",
            )
        ],
    )

    assert followups == [
        "What is the most important takeaway?",
        "Can you show the exact evidence from the documents?",
        "Can you explain this in more detail?",
    ]


def test_answer_service_followups_prefer_same_structured_answer_payload() -> None:
    service = AnswerService("no-result")

    followups = service.generate_followups(
        query_text="Explain the architectures",
        answer_text=(
            '{"key_findings":[],"detailed_analysis":"hello","limitations":"","conclusion":"",'
            '"confidence_score":0.8,"follow_up_suggestions":["A?","B?","C?"],'
            '"comparison_table":null,"chart":null,"diagram":null}'
        ),
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[
            ProviderSelectionCandidate(
                provider_type="custom",
                model_name="test-model",
                feature_scope="chat",
                source="tenant",
                base_url="http://mock-api",
            )
        ],
    )

    assert followups == ["A?", "B?", "C?"]


def test_answer_service_followups_use_static_fallback_when_llm_unavailable() -> None:
    service = AnswerService("no-result")

    followups = service.generate_followups(
        query_text="Summarize the architecture decisions",
        answer_text="This is a short summary.",
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[],
    )

    assert followups == [
        "Can you explain architecture decisions in more detail?",
        "Can you expand the summary with more detail?",
        "Can you show the exact evidence from the documents?",
    ]


def test_answer_service_followups_fallback_avoids_echoing_long_noisy_prompt() -> None:
    service = AnswerService("no-result")

    noisy_query = (
        "Can you explain it still have errors-- Parse error on line 3: ...s/Sensors] -->|data "
        "(text, sim, toy)| B[ --^ Expecting 'SQE', 'DOUBLECIRCLEEND' and more Mermaid parser "
        "tokens, so please give me fix correct mermaid diagram"
    )

    followups = service.generate_followups(
        query_text=noisy_query,
        answer_text="The diagram still fails to parse because the Mermaid syntax is malformed.",
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[],
    )

    assert followups == [
        "Can you show the corrected version step by step?",
        "What is the exact syntax error causing this failure?",
        "Can you explain the fix in simpler terms?",
    ]


def test_answer_service_followups_filters_echoed_candidates_before_fallback() -> None:
    service = AnswerService("no-result")

    query_text = (
        "Fix this Parse error on line 3 in the Mermaid graph and show the corrected diagram"
    )

    followups = service.generate_followups(
        query_text=query_text,
        answer_text=(
            "Can you explain fix this Parse error on line 3 in the Mermaid graph and show "
            "the corrected diagram in more detail?\n"
            "What is the most important takeaway here?\n"
            "Can you show the exact evidence from the documents?\n"
        ),
        tenant_id=UUID("11111111-1111-7111-8111-111111111111"),
        previous_messages=None,
        provider_candidates=[],
    )

    assert followups == [
        "What is the most important takeaway here?",
        "Can you show the exact evidence from the documents?",
    ]
