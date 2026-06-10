from __future__ import annotations

from datetime import datetime, timezone
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
    UserProfile,
    UserYearLearningPath,
)


def _register(client: TestClient, identifier: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "成森用户",
            "identifier": identifier,
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def _course(
    grade_id: str,
    course_id: str,
    theme: str,
    prerequisite_node_ids: list[str] | None = None,
) -> dict:
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
        "prerequisite_node_ids": prerequisite_node_ids or [],
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
    year_1_course = _course("year_1", "year_1_course_1", "编程基础")
    year_2_course_1 = _course(
        "year_2",
        "year_2_course_1",
        "数据结构基础",
        ["year_1_course_1"],
    )
    year_2_course_2 = _course(
        "year_2",
        "year_2_course_2",
        "数据库系统",
        ["year_2_course_1"],
    )
    year_3_course = _course(
        "year_3",
        "year_3_course_1",
        "AI 应用开发基础",
        ["year_2_course_2"],
    )
    return {
        "schema_version": "learning_path.v2.course_node",
        "grade_plans": {
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "打好编程基础",
                "course_nodes": [year_1_course],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入工程主线",
                "course_nodes": [year_2_course_1, year_2_course_2],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [year_3_course],
            },
        },
        "current_learning_course": {
            "grade_id": "year_2",
            "course_node_id": "year_2_course_2",
            "course_or_chapter_theme": "数据库系统",
            "course_goal": "完成 数据库系统",
            "time_arrangement": year_2_course_2["time_arrangement"],
            "current_focus": "关系模型",
            "progress_state": "in_progress",
            "next_action": "继续学习 SQL",
        },
    }


def _outline(course_id: str, grade_year: str, course_name: str) -> dict:
    return {
        "course_id": course_id,
        "course_name": course_name,
        "grade_year": grade_year,
        "personalization_summary": f"{course_name} 个性化安排",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "第一章",
                "order_index": 1,
                "description": "基础章节",
                "key_knowledge_points": ["基础概念"],
            }
        ],
        "learning_sequence": ["第一章"],
        "total_estimated_hours": "8 小时",
    }


def test_canopy_overview_requires_auth(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'canopy-auth.db'}"))

    response = client.get("/api/branch/canopy")

    assert response.status_code == 401


def test_canopy_overview_starts_growth_tree_from_seed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'canopy-seed.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "canopy-seed@example.com")

    response = client.get("/api/branch/canopy", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()

    assert body["growth_stage"] == 1
    assert body["completed_count"] == 0
    assert body["active_rate"] == 0
    assert [milestone["reached"] for milestone in body["milestones"]] == [False, False, False, False, False]


def test_canopy_overview_returns_calculated_tree_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'canopy-overview.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "canopy-overview@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    profile_created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    path_created_at = datetime(2026, 6, 2, tzinfo=timezone.utc)
    outline_created_at = datetime(2026, 6, 3, tzinfo=timezone.utc)
    quiz_created_at = datetime(2026, 6, 4, tzinfo=timezone.utc)
    first_passed_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    second_passed_at = datetime(2026, 6, 6, tzinfo=timezone.utc)

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "canopy-overview@example.com")).one()
        session.add(
            UserProfile(
                user_uid=user.uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "大二",
                        "major": "软件工程",
                    },
                    "text": "【用户基础信息】\n大二软件工程。",
                },
                profile_text="【用户基础信息】\n大二软件工程。",
                created_at=profile_created_at,
                updated_at=profile_created_at,
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=_path(),
                created_at=path_created_at,
                updated_at=path_created_at,
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_2_course_2",
                grade_year="year_2",
                course_name="数据库系统",
                outline_data=_outline("year_2_course_2", "year_2", "数据库系统"),
                created_at=outline_created_at,
                updated_at=outline_created_at,
            )
        )
        session.add(
            ChapterQuiz(
                quiz_id="quiz-1",
                user_uid=user.uid,
                course_node_id="year_2_course_2",
                chapter_id="1",
                status="ready",
                questions=[],
                created_at=quiz_created_at,
                updated_at=quiz_created_at,
            )
        )
        session.add(
            ChapterProgress(
                user_uid=user.uid,
                course_node_id="year_2_course_2",
                chapter_id="1",
                state="passed",
                best_score=80,
                passed_at=first_passed_at,
                updated_at=first_passed_at,
            )
        )
        session.add(
            ChapterProgress(
                user_uid=user.uid,
                course_node_id="year_2_course_2",
                chapter_id="2",
                state="passed",
                best_score=90,
                passed_at=second_passed_at,
                updated_at=second_passed_at,
            )
        )
        session.add(
            ChapterQuizAttempt(
                attempt_id="attempt-1",
                quiz_id="quiz-1",
                user_uid=user.uid,
                answers={},
                score=80,
                passed=True,
                grading_result={},
                created_at=first_passed_at,
            )
        )
        session.add(
            ChapterQuizAttempt(
                attempt_id="attempt-2",
                quiz_id="quiz-1",
                user_uid=user.uid,
                answers={},
                score=90,
                passed=True,
                grading_result={},
                created_at=second_passed_at,
            )
        )
        session.commit()

    response = client.get("/api/branch/canopy", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()

    assert body["growth_stage"] == 3
    assert body["completed_count"] == 2
    assert body["active_rate"] == 40
    assert body["avg_score"] == 85
    assert body["focused_hours"] == 8.0

    assert [course["id"] for course in body["courses"]] == [
        "year_1_course_1",
        "year_2_course_1",
        "year_2_course_2",
        "year_3_course_1",
    ]
    assert [course["grade"] for course in body["courses"]] == ["year_1", "year_2", "year_2", "year_3"]
    assert [course["status"] for course in body["courses"]] == ["completed", "completed", "current", "locked"]
    assert body["courses"][2]["title"] == "数据库系统"
    assert body["courses"][2]["description"] == "完成 数据库系统"
    assert body["courses"][2]["prerequisite_ids"] == ["year_2_course_1"]

    assert [milestone["date"] for milestone in body["milestones"]] == [
        "2026.06.01",
        "2026.06.02",
        "2026.06.03",
        "2026.06.04",
        "2026.06.05",
    ]
    assert [milestone["reached"] for milestone in body["milestones"]] == [True, True, True, True, True]
    assert body["milestones"][0]["title"] == "萌芽期 - 画像建立完成"
    assert body["milestones"][4]["desc"] == "成功通关首个章节测验，达成成森里程碑。"
