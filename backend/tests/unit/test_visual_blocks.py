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


def test_gallery_requires_at_least_one_image() -> None:
    try:
        validate_visual_fence("gallery", '{"title":"Empty","items":[]}')
    except ValueError:
        pass
    else:
        raise AssertionError("empty galleries must fail schema validation")


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
