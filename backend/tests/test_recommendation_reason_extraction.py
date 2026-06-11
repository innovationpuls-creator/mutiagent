from app.orchestration.agents.course_resources import _extract_recommendation_reason


def test_extracts_reason_from_markdown():
    md = "# Hello\n\nContent here.\n\n<!-- recommendation_reason: 因为你偏好项目驱动学习 -->"
    cleaned, reason = _extract_recommendation_reason(md)
    assert "recommendation_reason" not in cleaned
    assert reason == "因为你偏好项目驱动学习"
    assert "# Hello" in cleaned


def test_no_reason_returns_empty():
    md = "# Hello\n\nContent here."
    cleaned, reason = _extract_recommendation_reason(md)
    assert cleaned == md
    assert reason == ""


def test_reason_with_extra_spaces():
    md = "Content.\n\n<!--  recommendation_reason:  理由  -->"
    _, reason = _extract_recommendation_reason(md)
    assert reason == "理由"
