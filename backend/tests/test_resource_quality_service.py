from app.services.resource_quality_service import (
    _score_accuracy,
    _score_difficulty_fit,
    _score_outline_completeness,
)


def test_completeness_empty_outline():
    score, suggestions = _score_outline_completeness({})
    assert score == 0
    assert any("空" in s for s in suggestions)


def test_completeness_partial_content():
    outline = {
        "sections": [
            {"section_id": "1", "parent_section_id": None, "composed_markdown": "# Hello"},
            {"section_id": "2", "parent_section_id": None, "composed_markdown": ""},
        ]
    }
    score, suggestions = _score_outline_completeness(outline)
    assert score == 50
    assert any("1" in s for s in suggestions)


def test_completeness_full_content():
    outline = {
        "sections": [
            {"section_id": "1", "parent_section_id": None, "composed_markdown": "# Hello"},
            {"section_id": "2", "parent_section_id": None, "composed_markdown": "# World"},
        ]
    }
    score, _ = _score_outline_completeness(outline)
    assert score == 100


def test_difficulty_fit_no_profile():
    score, suggestions = _score_difficulty_fit({}, None)
    assert score == 60
    assert any("画像" in s for s in suggestions)


def test_difficulty_fit_beginner_too_many_sections():
    outline = {"sections": [{"section_id": str(i), "parent_section_id": None} for i in range(15)]}
    profile = {"learning_stage": "刚入门", "learning_pace_preference": "每天少量"}
    score, suggestions = _score_difficulty_fit(outline, profile)
    assert score < 70
    assert any("初学者" in s for s in suggestions)


def test_accuracy_good_outline():
    outline = {
        "sections": [
            {"section_id": "1", "parent_section_id": None},
            {"section_id": "1.1", "parent_section_id": "1"},
        ],
        "learning_sequence": ["1", "1.1"],
        "personalization_summary": "个性化说明",
    }
    score, _ = _score_accuracy(outline)
    assert score >= 90


def test_accuracy_poor_outline():
    outline = {"sections": [{"section_id": "1", "parent_section_id": None}]}
    score, suggestions = _score_accuracy(outline)
    assert score <= 70
    assert any("子节" in s for s in suggestions)
