from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import User, UserYearLearningPath


def _register(client: TestClient, identifier: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "学习路径用户",
            "identifier": identifier,
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def _year_path(theme: str) -> dict:
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "完成一个 AI 功能模块",
            "four_year_outcome": "具备全栈 AI 项目交付能力",
        },
        "learner_baseline": {
            "current_grade": "大三",
            "major": "软件工程",
            "mastered_content": ["Python", "前端基础"],
            "weaknesses": ["异步工程经验不足"],
            "constraints": ["时间有限"],
            "weekly_available_time": "每周 8 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级拆分",
            "sequence_rule": "先基础后项目",
            "resource_rule": "每个节点对应资源方向",
        },
        "grade_plans": {
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "grade_id": "year_3",
                        "course_or_chapter_theme": theme,
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "项目驱动",
                        },
                        "course_goal": f"完成{theme}",
                        "prerequisite_node_ids": [],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["OpenAI-compatible API 调用"],
                        "difficult_points": ["异步调用稳定性"],
                        "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
                    }
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
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": theme,
            "course_goal": f"完成{theme}",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "6 周",
                "pace_reason": "项目驱动",
            },
            "current_focus": f"正在学习 {theme}",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def test_learning_path_me_requires_auth(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'learning-path-auth.db'}"))

    response = client.get("/api/learning-path/me")

    assert response.status_code == 401


def test_learning_path_me_returns_404_before_path_generated(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'learning-path-empty.db'}"))
    token, _ = _register(client, "learning-path-empty@example.com")

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json()["detail"] == "还没有生成学习路径"


def test_learning_path_me_returns_year_learning_paths_and_latest_updated_at(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'learning-path-saved.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "learning-path-saved@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "learning-path-saved@example.com")).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="AI 基础",
                path_data=_year_path("AI 基础能力搭建"),
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI 项目",
                path_data=_year_path("AI 项目实战"),
            )
        )
        session.commit()

        latest = session.get(UserYearLearningPath, (user.uid, "year_3"))
        earlier = session.get(UserYearLearningPath, (user.uid, "year_2"))
        assert latest is not None
        assert earlier is not None
        latest.updated_at = latest.updated_at.replace(year=2026, month=6, day=5)
        earlier.updated_at = earlier.updated_at.replace(year=2026, month=6, day=1)
        session.add(latest)
        session.add(earlier)
        session.commit()

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["year_learning_paths"]["year_2"]["schema_version"] == "learning_path.v2.course_node"
    assert body["year_learning_paths"]["year_3"]["current_learning_course"]["course_or_chapter_theme"] == "AI 项目实战"
    assert body["year_learning_paths"]["year_3"]["current_learning_courses"][0]["course_node_id"] == "year_3_course_1"
    assert body["updated_at"].startswith("2026-06-05")
