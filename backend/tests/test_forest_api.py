from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    User,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from app.services.forest_service import (
    generate_or_read_quiz,
    read_forest_quiz_session,
    submit_quiz_attempt,
)


def test_forest_tables_are_created(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-tables.db'}"
    TestClient(create_app(database_url=database_url))
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        assert session.exec(select(ChapterQuiz)).all() == []
        assert session.exec(select(ChapterQuizAttempt)).all() == []
        assert session.exec(select(ChapterProgress)).all() == []


def _course(grade_id: str, course_id: str, theme: str) -> dict:
    return {
        "course_node_id": course_id,
        "grade_id": grade_id,
        "course_or_chapter_theme": theme,
        "time_arrangement": {
            "semester_scope": "上学期",
            "duration": "4 周",
            "pace_reason": "按课程节奏推进",
        },
        "course_goal": f"完成 {theme}",
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "key_points": [f"{theme} 重点"],
        "difficult_points": [f"{theme} 难点"],
        "learning_sequence": ["理解概念", "完成练习"],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": [f"掌握 {theme}"],
    }


def _path() -> dict:
    current = _course("year_3", "year_3_course_2", "AI Agent 开发")
    next_course = _course("year_3", "year_3_course_3", "AI 项目交付")
    return {
        "schema_version": "learning_path.v2.course_node",
        "grade_plans": {
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [current, next_course],
            },
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_2",
            "course_or_chapter_theme": "AI Agent 开发",
            "course_goal": "完成 AI Agent 开发",
            "time_arrangement": current["time_arrangement"],
            "current_focus": "正在学习 AI Agent 开发",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def _outline() -> dict:
    return {
        "course_id": "year_3_course_2",
        "course_name": "AI Agent 开发",
        "grade_year": "year_3",
        "personalization_summary": "先完成需求拆解。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "第一章：需求拆解",
                "order_index": 1,
                "description": "确认功能边界与验收标准。",
                "key_knowledge_points": ["功能边界", "验收标准"],
            },
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "第二章：工具编排",
                "order_index": 2,
                "description": "编排工具调用。",
                "key_knowledge_points": ["工具编排"],
            },
        ],
        "learning_sequence": ["第一章：需求拆解", "第二章：工具编排"],
        "total_estimated_hours": "8 小时",
        "section_composed_markdowns": {},
    }


def _seed_forest_data(database_url: str) -> str:
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        user = User(
            uid="forest-user",
            username="Forest 用户",
            identifier="forest@example.com",
            password_hash="hash",
        )
        session.add(user)
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI",
                path_data=_path(),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_3_course_2",
                grade_year="year_3",
                course_name="AI Agent 开发",
                outline_data=_outline(),
            )
        )
        session.commit()
    return "forest-user"


def test_read_forest_quiz_session_opens_first_chapter(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-read.db'}"
    TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        result = read_forest_quiz_session(session, user_uid, "year_3_course_2", "1")

    assert result.course.course_node_id == "year_3_course_2"
    assert result.chapter["section_id"] == "1"
    assert result.quiz is None
    assert result.progress.state == "available"


def test_generate_or_read_quiz_reuses_ready_quiz(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-generate.db'}"
    TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    questions = [{"question_id": "q1", "type": "single_choice", "prompt": "题目", "options": [], "points": 100}]

    with Session(engine) as session:
        first = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)
        second = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)

    assert first.quiz_id == second.quiz_id
    assert first.questions[0].question_id == "q1"


def test_submit_quiz_attempt_passes_and_opens_next_chapter(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-submit.db'}"
    TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    questions = [{"question_id": "q1", "type": "single_choice", "prompt": "题目", "options": [], "points": 100}]

    with Session(engine) as session:
        quiz = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)
        result = submit_quiz_attempt(
            session,
            user_uid,
            quiz.quiz_id,
            {"q1": "A"},
            {"score": 71, "passed": True, "question_results": [], "summary": "通过"},
        )
        current = session.get(ChapterProgress, (user_uid, "year_3_course_2", "1"))
        next_progress = session.get(ChapterProgress, (user_uid, "year_3_course_2", "2"))

    assert result.passed is True
    assert current is not None
    assert current.state == "passed"
    assert next_progress is not None
    assert next_progress.state == "available"
