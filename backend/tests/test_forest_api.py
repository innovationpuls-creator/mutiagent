from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.core.security import create_access_token
from app.main import create_app
from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    ChapterWeakness,
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


def _auth_headers(user_uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user_uid})}"}


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
        result, _weaknesses = submit_quiz_attempt(
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


def test_forest_quiz_session_api_reads_current_chapter(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-session-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)

    response = client.get(
        "/api/forest/courses/year_3_course_2/chapters/1/quiz",
        headers=_auth_headers(user_uid),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["course"]["course_node_id"] == "year_3_course_2"
    assert body["chapter"]["section_id"] == "1"
    assert body["progress"]["state"] == "available"


def test_generate_forest_quiz_api_persists_questions(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-generate-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)

    async def fake_generate_questions(*_args, **_kwargs):
        return [{"question_id": "q1", "type": "single_choice", "prompt": "题目", "options": [], "points": 100}]

    with patch("app.api.forest.generate_quiz_questions", fake_generate_questions):
        response = client.post(
            "/api/forest/courses/year_3_course_2/chapters/1/quiz/generate",
            json={"regenerate": False},
            headers=_auth_headers(user_uid),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["course_node_id"] == "year_3_course_2"
    assert body["chapter_id"] == "1"
    assert body["questions"][0]["question_id"] == "q1"


def test_generate_forest_quiz_api_reuses_ready_quiz_without_llm(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-generate-reuse-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    questions = [{"question_id": "q1", "type": "single_choice", "prompt": "题目", "options": [], "points": 100}]

    with Session(engine) as session:
        quiz = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)

    async def fail_generate_questions(*_args, **_kwargs):
        raise AssertionError("ready quiz should be reused")

    with patch("app.api.forest.generate_quiz_questions", fail_generate_questions):
        response = client.post(
            "/api/forest/courses/year_3_course_2/chapters/1/quiz/generate",
            json={"regenerate": False},
            headers=_auth_headers(user_uid),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["quiz_id"] == quiz.quiz_id
    assert body["questions"][0]["question_id"] == "q1"


def test_submit_forest_quiz_attempt_api_opens_next_chapter(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-attempt-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    questions = [{"question_id": "q1", "type": "single_choice", "prompt": "题目", "options": [], "points": 100}]

    with Session(engine) as session:
        quiz = generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)

    async def fake_grade_answers(*_args, **_kwargs):
        return {"score": 71, "passed": True, "question_results": [], "summary": "通过"}

    with patch("app.api.forest.grade_quiz_answers", fake_grade_answers):
        response = client.post(
            f"/api/forest/quizzes/{quiz.quiz_id}/attempts",
            json={"answers": {"q1": "A"}},
            headers=_auth_headers(user_uid),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 71
    assert body["passed"] is True

    with Session(engine) as session:
        next_progress = session.get(ChapterProgress, (user_uid, "year_3_course_2", "2"))

    assert next_progress is not None
    assert next_progress.state == "available"


def test_stream_forest_ai_api_returns_sse_chunks(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-ai-stream-api.db'}"
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)

    async def fake_stream_response(*_args, **_kwargs):
        yield "第一段"
        yield "第二段"

    with patch("app.api.forest.stream_forest_ai_response", fake_stream_response):
        response = client.post(
            "/api/forest/ai/stream",
            json={
                "course_node_id": "year_3_course_2",
                "chapter_id": "1",
                "quiz_id": None,
                "question_id": None,
                "message": "请解析",
                "active_question_context": {
                    "course_node_id": "year_3_course_2",
                    "chapter_id": "1",
                    "quiz_id": None,
                    "question_id": None,
                    "question": None,
                    "answer": None,
                    "grading_result": None,
                },
            },
            headers=_auth_headers(user_uid),
        )

    assert response.status_code == 200
    assert "event: forest_ai_text_chunk" in response.text
    assert '"chunk": "第一段"' in response.text
    assert '"chunk": "第二段"' in response.text
    assert "event: forest_ai_completed" in response.text


def test_read_forest_quiz_session_with_string_options(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-read-options.db'}"
    client = TestClient(create_app(database_url=database_url))
    user_uid = _seed_forest_data(database_url)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    questions = [
        {
            "question_id": "q1",
            "type": "single_choice",
            "prompt": "以下哪个是正确的？",
            "options": [
                "A. 选项一",
                "B. 选项二",
            ],
            "correct_option_id": "A",
            "points": 100
        }
    ]

    with Session(engine) as session:
        generate_or_read_quiz(session, user_uid, "year_3_course_2", "1", questions, regenerate=False)
        result = read_forest_quiz_session(session, user_uid, "year_3_course_2", "1")

    assert result.quiz is not None
    assert result.quiz.status == "ready"
    assert len(result.quiz.questions) == 1
    assert result.quiz.questions[0].options == [
        {"option_id": "A", "text": "选项一"},
        {"option_id": "B", "text": "选项二"},
    ]


def test_weakness_name_resolution(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'forest-weakness.db'}"
    TestClient(create_app(database_url=database_url))

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        user = User(
            uid="forest-user",
            username="Forest 用户",
            identifier="forest@example.com",
            password_hash="hash",
        )
        session.add(user)

        custom_outline = {
            "course_id": "year_3_course_2",
            "course_name": "AI Agent 开发",
            "grade_year": "year_3",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "第一章：需求拆解",
                    "order_index": 1,
                    "description": "确认功能边界与验收标准。",
                    "key_knowledge_points": ["功能边界", "验收标准"],
                }
            ],
            "learning_sequence": ["第一章：需求拆解"],
        }
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_3_course_2",
                grade_year="year_3",
                course_name="AI Agent 开发",
                outline_data=custom_outline,
            )
        )

        current_course = {
            "course_node_id": "year_3_course_2",
            "grade_id": "year_3",
            "course_or_chapter_theme": "AI Agent 开发",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "4 周",
                "pace_reason": "按课程节奏推进",
            },
            "course_goal": "完成 AI Agent 开发",
            "prerequisite_node_ids": [],
            "chapter_nodes": [],
            "core_knowledge_points": [
                {
                    "knowledge_point_id": "kp_lp_1",
                    "name": "机器学习核心",
                    "parent_knowledge_point_id": None,
                    "level": "核心",
                    "description": "机器学习的核心概念",
                    "mastery_standard": "掌握",
                }
            ],
            "key_points": ["AI Agent 开发 重点"],
            "difficult_points": ["AI Agent 开发 难点"],
            "learning_sequence": ["理解概念"],
            "knowledge_relations": [],
            "downstream_resource_direction_ids": [],
            "acceptance_criteria": ["掌握 AI Agent 开发"],
        }

        custom_path = {
            "schema_version": "learning_path.v2.course_node",
            "grade_plans": {
                "year_3": {
                    "grade_id": "year_3",
                    "grade_name": "大三",
                    "grade_goal": "完成 AI 应用开发项目",
                    "course_nodes": [current_course],
                },
            },
            "current_learning_course": {
                "grade_id": "year_3",
                "course_node_id": "year_3_course_2",
                "course_or_chapter_theme": "AI Agent 开发",
                "course_goal": "完成 AI Agent 开发",
                "time_arrangement": current_course["time_arrangement"],
                "current_focus": "正在学习 AI Agent 开发",
                "progress_state": "in_progress",
                "next_action": "继续学习第一章",
            },
        }
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI",
                path_data=custom_path,
            )
        )
        session.commit()

        questions = [
            {
                "question_id": "q1",
                "type": "single_choice",
                "prompt": "问题 1",
                "options": [],
                "points": 50,
                "knowledge_point_ids": ["功能边界"]
            },
            {
                "question_id": "q2",
                "type": "single_choice",
                "prompt": "问题 2",
                "options": [],
                "points": 50,
                "knowledge_point_ids": ["kp_lp_1"]
            }
        ]

        quiz = generate_or_read_quiz(session, "forest-user", "year_3_course_2", "1", questions, regenerate=False)

        answers = {"q1": "A", "q2": "B"}
        grading_result = {
            "score": 0,
            "passed": False,
            "question_results": [
                {"question_id": "q1", "score": 0, "max_score": 50},
                {"question_id": "q2", "score": 0, "max_score": 50}
            ],
            "summary": "不及格"
        }

        _, weaknesses = submit_quiz_attempt(
            session,
            "forest-user",
            quiz.quiz_id,
            answers,
            grading_result
        )

        assert len(weaknesses) == 2

        weakness_map = {w.knowledge_point_id: w for w in weaknesses}
        assert "功能边界" in weakness_map
        assert "kp_lp_1" in weakness_map

        assert weakness_map["功能边界"].knowledge_point_name == "功能边界"
        assert weakness_map["kp_lp_1"].knowledge_point_name == "机器学习核心"
