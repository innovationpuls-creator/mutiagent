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


def test_normalize_quiz_questions_with_various_options() -> None:
    # Test case 1: options are strings with letter prefixes
    questions = normalize_quiz_questions([
        {
            "question_id": "q1",
            "type": "single_choice",
            "prompt": "以下哪个是正确的？",
            "options": [
                "A. 选项A内容",
                "B: 选项B内容",
                "C、选项C内容",
                "D 选项D内容",
            ],
            "correct_option_id": "A. 选项A内容",
            "points": 10,
        }
    ])
    
    assert questions[0]["correct_option_id"] == "A"
    assert questions[0]["options"] == [
        {"option_id": "A", "text": "选项A内容"},
        {"option_id": "B", "text": "选项B内容"},
        {"option_id": "C", "text": "选项C内容"},
        {"option_id": "D", "text": "选项D内容"},
    ]

    # Test case 2: options are plain strings without prefixes
    questions2 = normalize_quiz_questions([
        {
            "question_id": "q1",
            "type": "single_choice",
            "prompt": "以下哪个是正确的？",
            "options": [
                "选项一",
                "选项二",
            ],
            "correct_option_id": "a",
            "points": 10,
        }
    ])
    assert questions2[0]["correct_option_id"] == "A"
    assert questions2[0]["options"] == [
        {"option_id": "A", "text": "选项一"},
        {"option_id": "B", "text": "选项二"},
    ]

    # Test case 3: options are dictionaries
    questions3 = normalize_quiz_questions([
        {
            "question_id": "q1",
            "type": "single_choice",
            "prompt": "以下哪个是正确的？",
            "options": [
                {"text": "选项A"},
                {"label": "选项B"},
                {"option_id": "C", "option_text": "选项C"},
            ],
            "correct_option_id": "b",
            "points": 10,
        }
    ])
    assert questions3[0]["correct_option_id"] == "B"
    assert questions3[0]["options"] == [
        {"option_id": "A", "text": "选项A"},
        {"option_id": "B", "text": "选项B"},
        {"option_id": "C", "text": "选项C"},
    ]
