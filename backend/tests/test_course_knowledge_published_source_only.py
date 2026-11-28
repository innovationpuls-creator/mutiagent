from __future__ import annotations

from pathlib import Path

from sqlmodel import create_engine

from tests.postgres import postgresql_test_url


def _naming_payload_from_outline(outline: dict) -> dict:
    return {
        "personalization_summary": outline["personalization_summary"],
        "section_texts": {
            section["section_id"]: {
                "title": section["title"],
                "description": section["description"],
                "key_knowledge_points": section["key_knowledge_points"],
            }
            for section in outline["sections"]
        },
    }


def _engine(tmp_path: Path):
    return create_engine(
        postgresql_test_url(tmp_path, "course-knowledge-published-only"),
    )


def _state(textbook_id: str | None) -> dict:
    course = {
        "course_node_id": "year_3_course_1",
        "course_or_chapter_theme": "矩阵专题",
        "grade_id": "year_3",
        "course_goal": "掌握矩阵乘法",
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "4 周",
            "pace_reason": "项目驱动",
        },
        "key_points": ["矩阵乘法"],
        "difficult_points": ["维度匹配"],
        "learning_sequence": ["矩阵乘法"],
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["能完成矩阵乘法练习"],
    }
    if textbook_id is not None:
        course["source_textbook_id"] = textbook_id
        course["source_textbook_title"] = "矩阵教材"
        course["source_outline_section_ids"] = ["1.1"]

    return {
        "user_id": "user-1",
        "profile": {
            "type": "basic_profile",
            "summary_text": "大三软件工程，想学矩阵。",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "软件工程",
                "learning_stage": "项目实践",
                "has_clear_goal": "是",
                "learning_method_preference": "项目驱动学习",
                "learning_pace_preference": "按周推进",
                "content_preference": ["文档"],
                "need_guidance": "需要",
                "knowledge_foundation": "有 Python 基础",
                "strengths": "能完成小型功能",
                "weaknesses": "线性代数不熟",
                "experience": "做过课程项目",
                "short_term_goal": "学习矩阵",
                "long_term_goal": "形成 AI 工程基础",
                "weekly_available_time": "每周 8 小时",
                "constraints": "时间有限",
            },
        },
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
                "grade_plans": {
                    "year_3": {"course_nodes": [course]},
                },
            }
        },
        "messages": [],
    }
