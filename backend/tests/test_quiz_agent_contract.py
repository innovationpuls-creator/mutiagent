from __future__ import annotations

import pytest

from app.orchestration.agents.quiz import (
    build_fallback_quiz_questions,
    normalize_grading_result,
    normalize_quiz_questions,
)


def test_build_fallback_quiz_questions_contains_supported_types() -> None:
    questions = build_fallback_quiz_questions("1", "第一章：需求拆解")

    assert [question["type"] for question in questions] == ["single_choice", "code", "image_upload"]
    assert [question["question_id"] for question in questions] == ["q1", "q2", "q3"]


def test_normalize_quiz_questions_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="题目类型不支持"):
        normalize_quiz_questions([{"question_id": "q1", "type": "essay", "prompt": "解释"}])


def test_normalize_grading_result_sets_passed_from_score() -> None:
    result = normalize_grading_result(
        {
            "score": 71,
            "question_results": [{"question_id": "q1", "correct": True, "feedback": "正确"}],
            "summary": "已经掌握",
        }
    )

    assert result["score"] == 71
    assert result["passed"] is True
