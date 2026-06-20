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
            "school": "测试大学",
            "major": "软件工程",
            "class_name": "三班",
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


def _multi_year_path() -> dict:
    def make_course(grade_id: str, course_id: str, theme: str) -> dict:
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

    year_1_course = make_course("year_1", "year_1_course_1", "编程基础")
    year_2_course = make_course("year_2", "year_2_course_1", "数据结构基础")
    year_3_course = make_course("year_3", "year_3_course_1", "AI 应用开发基础")
    year_4_course = make_course("year_4", "year_4_course_1", "毕业项目实战")
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "补齐工程能力",
            "four_year_outcome": "具备工程交付能力",
        },
        "learner_baseline": {
            "current_grade": "大三",
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
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "打好基础",
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
            "course_goal": "完成 AI 应用开发基础",
            "time_arrangement": year_3_course["time_arrangement"],
            "current_focus": "正在学习 AI 应用开发基础",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def _outline(
    course_id: str, grade_year: str, course_name: str, sections: list[dict]
) -> dict:
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
    client = TestClient(
        create_app(database_url=f"sqlite:///{tmp_path / 'branch-auth.db'}")
    )

    response = client.get("/api/branch/overview")

    assert response.status_code == 401


def test_branch_overview_returns_clickable_tabs_and_course_statuses(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-overview.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-overview@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "branch-overview@example.com")
        ).one()
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
                    [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "顺序表",
                            "order_index": 1,
                            "description": "基础结构",
                            "key_knowledge_points": ["线性表"],
                        }
                    ],
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
                    [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "关系模型",
                            "order_index": 1,
                            "description": "核心概念",
                            "key_knowledge_points": ["范式"],
                        }
                    ],
                ),
            )
        )
        session.commit()

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]
    year_1 = body["years"]["year_1"]

    assert year_2["grade_name"] == "大二"
    assert year_2["has_courses"] is True
    assert year_2["has_outline_content"] is True
    assert year_2["is_clickable"] is True
    assert [course["status"] for course in year_2["courses"]] == [
        "completed",
        "current",
        "locked",
    ]
    assert [course["has_outline"] for course in year_2["courses"]] == [
        True,
        True,
        False,
    ]

    assert year_1["has_courses"] is False
    assert year_1["has_outline_content"] is False
    assert year_1["is_clickable"] is False
    assert year_1["courses"] == []


def test_branch_overview_keeps_year_clickable_without_outline_content(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-no-outline.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-no-outline@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "branch-no-outline@example.com")
        ).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=_year_path(),
            )
        )
        session.commit()

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["has_courses"] is True
    assert year_2["has_outline_content"] is False
    assert year_2["is_clickable"] is True
    assert [course["has_outline"] for course in year_2["courses"]] == [
        False,
        False,
        False,
    ]


def test_branch_overview_falls_back_to_builtin_grade_name_when_grade_plan_name_is_blank(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-fallback-grade-name.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-fallback-grade-name@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(
                User.identifier == "branch-fallback-grade-name@example.com"
            )
        ).one()
        path_data = _year_path()
        path_data["grade_plans"]["year_2"]["grade_name"] = "   "
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_2",
                learning_topic="后端工程",
                path_data=path_data,
            )
        )
        session.commit()

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["years"]["year_2"]["grade_name"] == "大二"


def test_branch_overview_marks_complete_outline_payload_without_sections_as_outline_content(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-empty-sections-outline.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-empty-sections-outline@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(
                User.identifier == "branch-empty-sections-outline@example.com"
            )
        ).one()
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
                course_id="year_2_course_2",
                grade_year="year_2",
                course_name="数据库系统",
                outline_data=_outline("year_2_course_2", "year_2", "数据库系统", []),
            )
        )
        session.commit()

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["has_outline_content"] is True
    assert [course["has_outline"] for course in year_2["courses"]] == [
        False,
        True,
        False,
    ]


def test_branch_overview_ignores_legacy_sections_only_outline_payload(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-legacy-outline.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-legacy-outline@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "branch-legacy-outline@example.com")
        ).one()
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
                course_id="year_2_course_2",
                grade_year="year_2",
                course_name="数据库系统",
                outline_data={"sections": []},
            )
        )
        session.commit()

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["has_outline_content"] is False
    assert [course["has_outline"] for course in year_2["courses"]] == [
        False,
        False,
        False,
    ]


def test_branch_overview_marks_last_course_as_completed_when_current_progress_is_completed(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-completed-last.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-completed-last@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "branch-completed-last@example.com")
        ).one()
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

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["current_course_id"] == "year_2_course_3"
    assert [course["status"] for course in year_2["courses"]] == [
        "completed",
        "completed",
        "completed",
    ]


def test_branch_overview_reads_current_learning_courses_when_legacy_field_is_missing(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-current-learning-courses.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-current-learning-courses@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(
                User.identifier == "branch-current-learning-courses@example.com"
            )
        ).one()
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

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    year_2 = body["years"]["year_2"]

    assert year_2["current_course_id"] == "year_2_course_2"
    assert [course["status"] for course in year_2["courses"]] == [
        "completed",
        "current",
        "locked",
    ]


def test_branch_overview_expands_single_multi_grade_path_row(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'branch-expanded.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, _ = _register(client, "branch-expanded@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "branch-expanded@example.com")
        ).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data=_multi_year_path(),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_1_course_1",
                grade_year="year_1",
                course_name="编程基础",
                outline_data=_outline(
                    "year_1_course_1",
                    "year_1",
                    "编程基础",
                    [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "变量与控制流",
                            "order_index": 1,
                            "description": "基础语法",
                            "key_knowledge_points": ["变量"],
                        }
                    ],
                ),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发基础",
                outline_data=_outline(
                    "year_3_course_1",
                    "year_3",
                    "AI 应用开发基础",
                    [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "接口接入",
                            "order_index": 1,
                            "description": "完成最小闭环",
                            "key_knowledge_points": ["接口"],
                        }
                    ],
                ),
            )
        )
        session.commit()

    response = client.get(
        "/api/branch/overview", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["years"]["year_1"]["courses"][0]["course_node_id"] == "year_1_course_1"
    assert body["years"]["year_2"]["courses"][0]["course_node_id"] == "year_2_course_1"
    assert body["years"]["year_3"]["courses"][0]["course_node_id"] == "year_3_course_1"
    assert body["years"]["year_4"]["courses"][0]["course_node_id"] == "year_4_course_1"
    assert [course["status"] for course in body["years"]["year_1"]["courses"]] == [
        "completed"
    ]
    assert [course["status"] for course in body["years"]["year_2"]["courses"]] == [
        "completed"
    ]
    assert [course["status"] for course in body["years"]["year_3"]["courses"]] == [
        "current"
    ]
    assert [course["status"] for course in body["years"]["year_4"]["courses"]] == [
        "locked"
    ]
    assert body["years"]["year_1"]["current_course_id"] is None
    assert body["years"]["year_3"]["current_course_id"] == "year_3_course_1"
    assert body["years"]["year_4"]["current_course_id"] is None
    assert body["years"]["year_1"]["has_outline_content"] is True
    assert body["years"]["year_2"]["has_outline_content"] is False
    assert body["years"]["year_3"]["has_outline_content"] is True
    assert body["years"]["year_4"]["has_outline_content"] is False
