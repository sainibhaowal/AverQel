from app.schemas.query.structured_response import StructuredAnswerResponse


def test_structured_answer_response_parsing():
    json_data = {
        "key_findings": ["Point 1", "Point 2"],
        "detailed_analysis": "This is detailed.",
        "limitations": "Some limits.",
        "conclusion": "Final thought.",
    }
    obj = StructuredAnswerResponse(**json_data)
    assert len(obj.key_findings) == 2
    assert obj.detailed_analysis == "This is detailed."
    assert obj.limitations == "Some limits."
    assert obj.conclusion == "Final thought."


def test_structured_answer_response_fallback():
    raw_text = "This is a raw text response."
    obj = StructuredAnswerResponse.fallback(raw_text)
    assert obj.key_findings == []
    assert obj.detailed_analysis == "This is a raw text response."
    assert obj.limitations == ""
    assert obj.conclusion == ""
