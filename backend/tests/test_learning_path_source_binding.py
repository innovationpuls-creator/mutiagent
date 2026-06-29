from __future__ import annotations

from copy import deepcopy

from app.orchestration.agents.learning_path import _bind_confirmed_course_sources


def _path_dict() -> dict:
    return {
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "矩阵专题",
                        "course_stage_plan": ["预习", "练习"],
                        "learning_sequence": ["预习", "练习"],
                    },
                    {
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "向量专题",
                        "course_stage_plan": ["预习", "练习"],
                        "learning_sequence": ["预习", "练习"],
                    },
                ]
            }
        }
    }


def _intake_courses() -> list[dict]:
    return [
        {
            "title": "矩阵专题",
            "purpose": "掌握矩阵乘法",
            "source_textbook_id": "textbook-matrix",
            "source_textbook_title": "矩阵教材",
            "source_outline_section_ids": ["1.1", "1.2"],
        },
        {
            "title": "向量专题",
            "purpose": "掌握向量运算",
            "source_textbook_id": "textbook-vector",
            "source_textbook_title": "向量教材",
            "source_outline_section_ids": ["2.1"],
        },
    ]


def test_bind_confirmed_course_sources_rewrites_course_nodes():
    path_dict = _path_dict()
    intake_courses = _intake_courses()

    bound = _bind_confirmed_course_sources(
        deepcopy(path_dict),
        "year_3",
        intake_courses,
    )

    course_nodes = bound["grade_plans"]["year_3"]["course_nodes"]
    assert course_nodes[0]["source_textbook_id"] == "textbook-matrix"
    assert course_nodes[0]["source_textbook_title"] == "矩阵教材"
    assert course_nodes[0]["source_outline_section_ids"] == ["1.1", "1.2"]
    assert course_nodes[1]["source_textbook_id"] == "textbook-vector"
    assert course_nodes[1]["source_textbook_title"] == "向量教材"
    assert course_nodes[1]["source_outline_section_ids"] == ["2.1"]


def test_bind_confirmed_course_sources_rejects_length_mismatch():
    path_dict = _path_dict()

    try:
        _bind_confirmed_course_sources(
            deepcopy(path_dict), "year_3", _intake_courses()[:1]
        )
    except ValueError as exc:
        assert str(exc) == "学习路径 course_nodes 数量必须与已确认课程草案一致。"
    else:
        raise AssertionError("expected ValueError")
