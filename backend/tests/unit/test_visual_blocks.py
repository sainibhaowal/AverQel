import pytest

from app.query.services.visual_blocks import (
    normalize_visual_markdown,
    validate_visual_block_payload,
    validate_visual_fence,
)


def test_valid_visual_fences_are_preserved() -> None:
    content = '```chart\n{"title":"Trend","chart_type":"line","series":[{"label":"A","value":1},{"label":"B","value":2}]}\n```'

    normalized, errors = normalize_visual_markdown(content)

    assert normalized == content
    assert errors == []


def test_invalid_visual_fences_are_demoted_to_safe_code() -> None:
    content = '```graph\n{"nodes":"not-a-list","edges":[]}\n```'

    normalized, errors = normalize_visual_markdown(content)

    assert "```text" in normalized
    assert errors


def test_card_tone_aliases_are_normalized_and_keep_cards_renderable() -> None:
    content = (
        '```card\n{"title":"Revenue","tone":"positive",'
        '"content":"**Trend: up 8.2%.**\\nRevenue reached $4.0M.",'
        '"metrics":[{"label":"Revenue","value":"$4.0M"}]}\n```\n\n'
        '```card\n{"title":"Quota attainment","tone":"caution",'
        '"content":"Slightly below target.",'
        '"metrics":[{"label":"Quota attainment","value":"96%"}]}\n```'
    )

    normalized, errors = normalize_visual_markdown(content)

    assert errors == []
    assert normalized.count("```card") == 2
    assert '"tone": "success"' in normalized
    assert '"tone": "warning"' in normalized
    assert "```text" not in normalized


def test_invalid_card_payload_still_falls_back_to_safe_code() -> None:
    content = '```card\n{"title":"Empty","tone":"positive","content":""}\n```'

    normalized, errors = normalize_visual_markdown(content)

    assert normalized.startswith("```text\n")
    assert errors


def test_evaluation_card_requires_a_bounded_score_and_supporting_metrics() -> None:
    card = {
        "type": "card",
        "id": "evaluation-1",
        "title": "API evaluation",
        "layout": "evaluation",
        "score": {"value": 51, "max": 100, "tone": "error"},
        "metrics": [{"label": "Valid tests", "value": 15}],
    }
    validate_visual_block_payload(card)
    fence = chr(96) * 3
    normalized, errors = normalize_visual_markdown(
        f'{fence}card\n{{"title":"API evaluation","layout":"evaluation",'
        '"score":{"value":51,"max":100,"tone":"error"},'
        f'"metrics":[{{"label":"Valid tests","value":15}}]}}\n{fence}'
    )
    assert errors == []
    assert normalized.startswith(f"{fence}card")

    invalid = {**card, "score": {"value": 101, "max": 100}}
    with pytest.raises(ValueError, match="score value must not exceed its maximum"):
        validate_visual_block_payload(invalid)


def test_referral_card_requires_reward_and_terms_and_can_omit_body_copy() -> None:
    card = {
        "type": "card",
        "id": "referral-1",
        "title": "Referral terms",
        "layout": "referral",
        "code": "81D9-627A-11",
        "primary_metric": {"label": "Gift tokens advertised", "value": "10,000,000"},
        "details": [{"label": "Free cash", "value": "No"}],
    }
    validate_visual_block_payload(card)
    fence = chr(96) * 3
    normalized, errors = normalize_visual_markdown(
        f'{fence}json\n{{"title":"Referral terms","layout":"referral",'
        '"primary_metric":{"label":"Gift tokens advertised","value":"10,000,000"},'
        f'"details":[{{"label":"Free cash","value":"No"}}]}}\n{fence}'
    )
    assert errors == []
    assert normalized.startswith(f"{fence}card")

    invalid = {**card, "details": []}
    with pytest.raises(ValueError, match="at least one terms detail"):
        validate_visual_block_payload(invalid)


def test_gallery_requires_at_least_one_image() -> None:
    try:
        validate_visual_fence("gallery", '{"title":"Empty","items":[]}')
    except ValueError:
        pass
    else:
        raise AssertionError("empty galleries must fail schema validation")


def test_infographic_fence_preserves_supported_layouts_and_source_links() -> None:
    content = (
        '```infographic\n{"title":"Launch plan","layout":"steps",'
        '"items":[{"title":"Research","icon":"lightbulb"},'
        '{"title":"Ship","icon":"zap"}],'
        '"sources":[{"title":"Plan","url":"https://example.com/plan"}]}\n```'
    )

    normalized, errors = normalize_visual_markdown(content)

    assert normalized == content
    assert errors == []

    invalid, invalid_errors = normalize_visual_markdown(content.replace('"zap"', '"rocket"'))
    assert invalid.startswith("```text\n")
    assert invalid_errors


def test_mismatched_generic_json_fence_recovers_visual_and_following_markdown() -> None:
    content = (
        '````json\n{"title":"Launch plan","layout":"steps",'
        '"items":[{"title":"Research"},{"title":"Ship"}]}\n```\n\n'
        "Quick summary follows."
    )

    normalized, errors = normalize_visual_markdown(content)

    assert normalized == (
        '```infographic\n{"title":"Launch plan","layout":"steps",'
        '"items":[{"title":"Research"},{"title":"Ship"}]}\n```\n\n'
        "Quick summary follows."
    )
    assert errors == []


def test_mismatched_generic_json_fence_does_not_promote_unrelated_json() -> None:
    content = '````json\n{"ok":true,"count":2}\n```\n\nKeep this as code.'

    normalized, errors = normalize_visual_markdown(content)

    assert normalized == content
    assert errors == []


def test_mismatched_place_card_fence_normalizes_common_source_and_detail_shapes() -> None:
    content = (
        '````json\n{"title":"Berlin Welcome Center",'
        '"content":"Visitor information at the airport.","layout":"place",'
        '"details":["**Hours:** 08:00–20:00"],'
        '"sources":[{"label":"Official visitor page",'
        '"href":"https://example.com/visit"}]}\n```'
    )

    normalized, errors = normalize_visual_markdown(content)

    assert errors == []
    assert normalized.startswith("```card\n")
    assert (
        '"details": [\n    {\n      "label": "Hours",\n      "value": "08:00–20:00"' in normalized
    )
    assert (
        '"sources": [\n    {\n      "title": "Official visitor page",\n      "url": "https://example.com/visit"'
        in normalized
    )


def test_indented_mixed_fences_recover_place_card_and_research_notes() -> None:
    content = (
        '    ~~~~json\n{"title":"Berlin Welcome Center",'
        '"content":"Visitor information at the airport.","layout":"place",'
        '"details":["**Hours:** 08:00–20:00"],'
        '"sources":[{"label":"Official visitor page",'
        '"href":"https://example.com/visit"}]}\n```\n\n'
        "**Research notes:**\n- The source was read in full.\n\n"
        "### Sources\n[R1](https://example.com/visit)\n~~~"
    )

    normalized, errors = normalize_visual_markdown(content)

    assert errors == []
    assert normalized.startswith("```card\n")
    assert "**Research notes:**" in normalized
    assert "### Sources\n[R1](https://example.com/visit)" in normalized
    assert "\n~~~" not in normalized


def test_infographic_layout_requirements_are_validated() -> None:
    valid = {
        "type": "infographic",
        "id": "timeline-1",
        "title": "Milestones",
        "layout": "timeline",
        "items": [
            {"title": "Design", "date": "March"},
            {"title": "Launch", "date": "June"},
        ],
        "sources": [{"title": "Roadmap", "url": "https://example.com/roadmap"}],
    }
    validate_visual_block_payload(valid)

    invalid = {
        **valid,
        "layout": "stats",
        "items": [{"title": "Users"}, {"title": "Teams"}],
    }
    with pytest.raises(ValueError, match="statistics items require a value"):
        validate_visual_block_payload(invalid)


@pytest.mark.parametrize("direction", ["LR", "RL", "TD", "DT"])
def test_step_infographic_accepts_each_supported_flow_direction(direction: str) -> None:
    validate_visual_block_payload(
        {
            "type": "infographic",
            "id": f"steps-{direction}",
            "title": "Setup process",
            "layout": "steps",
            "direction": direction,
            "items": [{"title": "Prepare"}, {"title": "Run"}],
        }
    )


def test_step_infographic_rejects_unsupported_flow_direction() -> None:
    with pytest.raises(ValueError):
        validate_visual_block_payload(
            {
                "type": "infographic",
                "id": "steps-invalid-direction",
                "title": "Setup process",
                "layout": "steps",
                "direction": "DIAGONAL",
                "items": [{"title": "Prepare"}, {"title": "Run"}],
            }
        )


def test_infographic_timeline_date_labels_allow_longer_period_descriptions() -> None:
    timeline = {
        "type": "infographic",
        "id": "timeline-long-date",
        "title": "Milestones",
        "layout": "timeline",
        "items": [
            {"title": "Design", "date": "Setup: " + "prepare dependencies and access. " * 6},
            {"title": "Launch", "date": "June"},
        ],
    }
    assert len(timeline["items"][0]["date"]) > 80
    validate_visual_block_payload(timeline)

    too_long = {
        **timeline,
        "items": [{"title": "Design", "date": "x" * 301}, {"title": "Launch", "date": "June"}],
    }
    with pytest.raises(ValueError, match="at most 300 characters"):
        validate_visual_block_payload(too_long)


def test_place_cards_require_sources_and_accept_structured_details() -> None:
    card = {
        "type": "card",
        "id": "place-1",
        "title": "Example Museum",
        "content": "A city museum.",
        "layout": "place",
        "image_url": "https://example.com/museum.jpg",
        "details": [{"label": "Hours", "value": "10:00–18:00", "icon": "clock"}],
        "sources": [{"title": "Official visitor page", "url": "https://example.com/visit"}],
    }
    validate_visual_block_payload(card)

    with pytest.raises(ValueError, match="place cards require at least one source URL"):
        validate_visual_block_payload({**card, "sources": []})


def test_named_multi_series_payload_supports_secondary_axis_and_annotations() -> None:
    validate_visual_block_payload(
        {
            "type": "chart",
            "id": "benchmark",
            "chart_type": "bar",
            "series": [],
            "series_groups": [
                {
                    "name": "Model A",
                    "points": [{"label": "Q1", "value": 42}],
                    "axis": "left",
                },
                {
                    "name": "Latency",
                    "points": [{"label": "Q1", "value": 120}],
                    "axis": "right",
                },
            ],
            "secondary_y_label": "milliseconds",
            "annotations": [{"label": "Launch", "x": "Q1"}],
        }
    )


def test_canonical_visual_metadata_survives_validation() -> None:
    validate_visual_block_payload(
        {
            "type": "chart",
            "id": "stable-block",
            "block_id": "stable-block",
            "schema_version": 1,
            "revision": 4,
            "series": [{"label": "A", "value": 1}, {"label": "B", "value": 2}],
            "source_markdown": "```chart ...```",
            "assets": [{"url": "https://example.com/a.png", "status": "pending"}],
            "history": [{"revision": 4, "source": "note"}],
            "undo": {"can_undo": True},
        }
    )
