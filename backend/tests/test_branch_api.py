from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import User, UserCourseKnowledgeOutline, UserYearLearningPath


def _register(client: TestClient, identifier: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "繁枝用户",
            "identifier": identifier,
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def _course(course_id: str, theme: str) -> dict:
    return {
        "course_node_id": course_id,
        "grade_id": "year_2",
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


def _year_path() -> dict:
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "后端工程",
            "goal_type": "能力提升",
            "desired_outcome": "补齐工程能力",
            "four_year_outcome": "具备工程交付能力",
        },
        "learner_baseline": {
            "current_grade": "大二",
            "major": "软件工程",
            "mastered_content": ["Python"],
            "weaknesses": ["数据库"],
            "constraints": ["时间有限"],
            "weekly_available_time": "每周 6 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级拆分",
            "sequence_rule": "先基础再实践",
            "resource_rule": "按课程生成资源",
        },
        "grade_plans": {
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入工程主线",
                "course_nodes": [
                    _course("year_2_course_1", "数据结构基础"),
                    _course("year_2_course_2", "数据库系统"),
                    _course("year_2_course_3", "后端接口实战"),
                ],
            }
        },
        "knowledge_graph": {
            "global_relations": [],
            "critical_paths": [],
        },
        "resource_generation_contract": {
            "downstream_agents": [],
            "resource_directions": [],
        },
        "dynamic_update_contract": {
            "trackable_metrics": [],
            "update_triggers": [],
            "adjustment_strategy": "按周调整",
        },
        "current_learning_course": {
            "grade_id": "year_2",
            "course_node_id": "year_2_course_2",
            "course_or_chapter_theme": "数据库系统",
            "course_goal": "完成 数据库系统",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "4 周",
                "pace_reason": "按课程节奏推进",
            },
            "current_focus": "关系模型",
            "progress_state": "in_progress",
            "next_action": "继续学习 SQL",
        },
    }


def _outline(course_id: str, grade_year: str, course_name: str, sections: list[dict]) -> dict:
    return {
        "course_id": course_id,
        "course_name": course_name,
        "grade_year": grade_year,
        "personalization_summary": f"{course_name} 个性化安排",
        "sections": sections,
        "learning_sequence": ["第一步", "第二步"],
        "total_estimated_hours": "12 小时",
    }


def test_branch_overview_requires_auth(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'branch-auth.db'}"))

    response = client.get("/api/branch/overview")

    assert response.status_code == 401


def test_branch_overview_returns_clickable_tabs_and_course_statuses(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-overview.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-overview@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "branch-overview@example.com")).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=_year_path(),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_2_course_1",
                grade_year="year_2",
                course_name="数据结构基础",
                outline_data=_outline(
                    "year_2_course_1",
                    "year_2",
                    "数据结构基础",
                    [{"section_id": "1", "parent_section_id": None, "depth": 1, "title": "顺序表", "order_index": 1, "description": "基础结构", "key_knowledge_points": ["线性表"]}],
                ),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_2_course_2",
                grade_year="year_2",
                course_name="数据库系统",
                outline_data=_outline(
                    "year_2_course_2",
                    "year_2",
                    "数据库系统",
                    [{"section_id": "1", "parent_section_id": None, "depth": 1, "title": "关系模型", "order_index": 1, "description": "核心概念", "key_knowledge_points": ["范式"]}],
                ),
            )
        )
        session.commit()

    response = client.get("/api/branch/overview", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]
    year_1 = body["years"]["year_1"]

    assert year_2["grade_name"] == "大二"
    assert year_2["has_courses"] is True
    assert year_2["has_outline_content"] is True
    assert year_2["is_clickable"] is True
    assert [course["status"] for course in year_2["courses"]] == ["completed", "current", "locked"]
    assert [course["has_outline"] for course in year_2["courses"]] == [True, True, False]

    assert year_1["has_courses"] is False
    assert year_1["has_outline_content"] is False
    assert year_1["is_clickable"] is False
    assert year_1["courses"] == []


def test_branch_overview_keeps_year_clickable_without_outline_content(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-no-outline.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-no-outline@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "branch-no-outline@example.com")).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=_year_path(),
            )
        )
        session.commit()

    response = client.get("/api/branch/overview", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["has_courses"] is True
    assert year_2["has_outline_content"] is False
    assert year_2["is_clickable"] is True
    assert [course["has_outline"] for course in year_2["courses"]] == [False, False, False]


def test_branch_overview_marks_last_course_as_completed_when_current_progress_is_completed(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-completed-last.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-completed-last@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "branch-completed-last@example.com")).one()
        path_data = _year_path()
        path_data["current_learning_course"] = {
            "grade_id": "year_2",
            "course_node_id": "year_2_course_3",
            "course_or_chapter_theme": "后端接口实战",
            "course_goal": "完成 后端接口实战",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "4 周",
                "pace_reason": "按课程节奏推进",
            },
            "current_focus": "课程已完成",
            "progress_state": "completed",
            "next_action": "当前年级课程已完成",
        }
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=path_data,
            )
        )
        session.commit()

    response = client.get("/api/branch/overview", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["current_course_id"] == "year_2_course_3"
    assert [course["status"] for course in year_2["courses"]] == ["completed", "completed", "completed"]


def test_branch_overview_reads_current_learning_courses_when_legacy_field_is_missing(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-current-learning-courses.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-current-learning-courses@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "branch-current-learning-courses@example.com")).one()
        path_data = _year_path()
        current_course = path_data.pop("current_learning_course")
        path_data["current_learning_courses"] = [current_course]
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=path_data,
            )
        )
        session.commit()

    response = client.get("/api/branch/overview", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["current_course_id"] == "year_2_course_2"
    assert [course["status"] for course in year_2["courses"]] == ["completed", "current", "locked"]
