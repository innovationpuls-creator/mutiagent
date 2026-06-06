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


def _year_path(theme: str, grade_id: str = "year_3") -> dict:
    grade_name = {
        "year_1": "大一",
        "year_2": "大二",
        "year_3": "大三",
        "year_4": "大四",
    }[grade_id]
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "完成一个 AI 功能模块",
            "four_year_outcome": "具备全栈 AI 项目交付能力",
        },
        "learner_baseline": {
            "current_grade": grade_name,
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
            grade_id: {
                "grade_id": grade_id,
                "grade_name": grade_name,
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [
                    {
                        "course_node_id": f"{grade_id}_course_1",
                        "grade_id": grade_id,
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
            "grade_id": grade_id,
            "course_node_id": f"{grade_id}_course_1",
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


def _multi_year_path() -> dict:
    def make_course(grade_id: str, course_id: str, theme: str) -> dict:
        return {
            "course_node_id": course_id,
            "grade_id": grade_id,
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
            "key_points": ["阶段重点"],
            "difficult_points": ["阶段难点"],
            "learning_sequence": ["第一步", "第二步"],
            "knowledge_relations": [],
            "downstream_resource_direction_ids": [],
            "acceptance_criteria": [f"完成 {theme}"],
        }

    year_1_course = make_course("year_1", "year_1_course_1", "编程基础")
    year_2_course = make_course("year_2", "year_2_course_1", "工程化 Web 开发")
    year_3_course = make_course("year_3", "year_3_course_1", "AI 应用开发基础")
    year_4_course = make_course("year_4", "year_4_course_1", "毕业项目实战")
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
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "打基础",
                "course_nodes": [year_1_course],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "进入工程主线",
                "course_nodes": [year_2_course],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 应用开发项目",
                "course_nodes": [year_3_course],
            },
            "year_4": {
                "grade_id": "year_4",
                "grade_name": "大四",
                "grade_goal": "沉淀毕业项目",
                "course_nodes": [year_4_course],
            },
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
            "course_or_chapter_theme": "AI 应用开发基础",
            "course_goal": "完成AI 应用开发基础",
            "time_arrangement": year_3_course["time_arrangement"],
            "current_focus": "正在学习 AI 应用开发基础",
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
                path_data=_year_path("AI 基础能力搭建", "year_2"),
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


def test_learning_path_me_expands_multi_grade_plan_from_single_saved_row(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'learning-path-expanded.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "learning-path-expanded@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == "learning-path-expanded@example.com")).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data=_multi_year_path(),
            )
        )
        session.commit()

    response = client.get("/api/learning-path/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert set(body["year_learning_paths"]) == {"year_1", "year_2", "year_3", "year_4"}
    assert body["year_learning_paths"]["year_1"]["grade_plans"]["year_1"]["course_nodes"][0]["course_node_id"] == "year_1_course_1"
    assert body["year_learning_paths"]["year_4"]["grade_plans"]["year_4"]["course_nodes"][0]["course_node_id"] == "year_4_course_1"
