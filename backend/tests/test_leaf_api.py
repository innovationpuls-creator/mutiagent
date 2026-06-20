from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import (
    ChapterProgress,
    User,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)


def _register(client: TestClient, identifier: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "叶茂用户",
            "identifier": identifier,
            "school": "测试大学",
            "major": "软件工程",
            "class_name": "三班",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["access_token"], body["user"]["uid"]


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
    completed = _course("year_3", "year_3_course_1", "AI 应用入门")
    current = _course("year_3", "year_3_course_2", "AI Agent 开发")
    locked = _course("year_3", "year_3_course_3", "AI 项目交付")
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
            "mastered_content": ["Python"],
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
                "course_nodes": [completed, current, locked],
            },
        },
        "knowledge_graph": {"global_relations": [], "critical_paths": []},
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
            "course_node_id": "year_3_course_2",
            "course_or_chapter_theme": "AI Agent 开发",
            "course_goal": "完成 AI Agent 开发",
            "time_arrangement": current["time_arrangement"],
            "current_focus": "正在学习 AI Agent 开发",
            "progress_state": "in_progress",
            "next_action": "继续学习第一章",
        },
    }


def _outline(course_id: str, course_name: str) -> dict:
    return {
        "course_id": course_id,
        "course_name": course_name,
        "grade_year": "year_3",
        "personalization_summary": "先完成需求拆解，再进入最小闭环。",
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
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确本章目标。",
                "key_knowledge_points": ["学习目标"],
            },
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "第二章：工具编排",
                "order_index": 3,
                "description": "编排工具调用。",
                "key_knowledge_points": ["工具编排"],
            },
        ],
        "learning_sequence": ["第一章：需求拆解", "第二章：工具编排"],
        "total_estimated_hours": "8 小时",
        "section_composed_markdowns": {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "markdown": "# 学习目标\n\n已经拼装好的内容。",
                "blocks": [
                    {
                        "type": "markdown",
                        "markdown": "# 学习目标\n\n已经拼装好的内容。",
                    },
                ],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        },
    }


def _seed(client: TestClient, database_url: str, identifier: str) -> str:
    token, _ = _register(client, identifier)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        user = session.exec(select(User).where(User.identifier == identifier)).one()
        session.add(
            UserYearLearningPath(
                user_uid=user.uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data=_path(),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用入门",
                outline_data=_outline("year_3_course_1", "AI 应用入门"),
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=user.uid,
                course_id="year_3_course_2",
                grade_year="year_3",
                course_name="AI Agent 开发",
                outline_data=_outline("year_3_course_2", "AI Agent 开发"),
            )
        )
        session.commit()
    return token


def test_leaf_course_requires_auth(tmp_path: Path) -> None:
    client = TestClient(
        create_app(database_url=f"sqlite:///{tmp_path / 'leaf-auth.db'}")
    )

    response = client.get("/api/leaf/courses/year_3_course_2")

    assert response.status_code == 401


def test_leaf_course_returns_current_course_with_outline_and_composed_content(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'leaf-current.db'}"
    client = TestClient(create_app(database_url=database_url))
    token = _seed(client, database_url, "leaf-current@example.com")

    response = client.get(
        "/api/leaf/courses/year_3_course_2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_state"] == "available"
    assert body["course"]["course_node_id"] == "year_3_course_2"
    assert body["course"]["status"] == "current"
    assert body["can_generate"] is True
    assert body["outline"]["course_id"] == "year_3_course_2"
    assert body["sections"][0]["section_id"] == "1"
    assert body["section_composed_markdowns"]["1.1"]["markdown"].startswith(
        "# 学习目标"
    )
    assert body["generation_status"] is None


def test_leaf_course_opens_next_generatable_chapter_after_quiz_pass(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'leaf-next-chapter.db'}"
    client = TestClient(create_app(database_url=database_url))
    token = _seed(client, database_url, "leaf-next-chapter@example.com")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "leaf-next-chapter@example.com")
        ).one()
        session.add(
            ChapterProgress(
                user_uid=user.uid,
                course_node_id="year_3_course_2",
                chapter_id="1",
                state="passed",
                best_score=82,
            )
        )
        session.commit()

    response = client.get(
        "/api/leaf/courses/year_3_course_2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_generate"] is True
    assert body["first_generatable_chapter_id"] == "2"


def test_leaf_course_keeps_sections_empty_when_composed_content_missing(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'leaf-resource-fields.db'}"
    client = TestClient(create_app(database_url=database_url))
    token = _seed(client, database_url, "leaf-resource-fields@example.com")

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.identifier == "leaf-resource-fields@example.com")
        ).one()
        row = session.get(UserCourseKnowledgeOutline, (user.uid, "year_3_course_2"))
        assert row is not None
        outline_data = dict(row.outline_data)
        outline_data.pop("section_composed_markdowns", None)
        outline_data["section_markdowns"] = {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "markdown": "# 学习目标\n\n正文内容\n\n<!-- video:id=video_1 -->\n\n<!-- animation:id=anim_1 -->",
                "video_briefs": [
                    {"video_id": "video_1", "title": "导入视频", "purpose": "建立直觉"}
                ],
                "animation_briefs": [
                    {
                        "animation_id": "anim_1",
                        "title": "目标动画",
                        "concept": "目标收敛",
                        "visual_elements": ["目标卡片"],
                        "motion": "淡入",
                        "space": "高度 320px",
                        "placement_hint": "正文中段",
                    }
                ],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        }
        outline_data["section_video_links"] = {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "videos": [
                    {
                        "brief_id": "video_1",
                        "title": "导入视频",
                        "url": "https://example.com/video",
                        "cover_url": "https://example.com/cover.png",
                        "cover_status": "provided",
                        "source": "example.com",
                    }
                ],
            }
        }
        outline_data["section_html_animations"] = {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "animations": [
                    {
                        "brief_id": "anim_1",
                        "animation_id": "anim_1",
                        "title": "目标动画",
                        "html": '<section class="section-animation"></section>',
                    }
                ],
            }
        }
        row.outline_data = outline_data
        session.add(row)
        session.commit()

    response = client.get(
        "/api/leaf/courses/year_3_course_2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["section_composed_markdowns"] == {}


def test_leaf_course_returns_completed_view_only(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'leaf-completed.db'}"
    client = TestClient(create_app(database_url=database_url))
    token = _seed(client, database_url, "leaf-completed@example.com")

    response = client.get(
        "/api/leaf/courses/year_3_course_1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_state"] == "available"
    assert body["course"]["status"] == "completed"
    assert body["can_generate"] is False


def test_leaf_course_returns_locked_json_for_existing_locked_course(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'leaf-locked.db'}"
    client = TestClient(create_app(database_url=database_url))
    token = _seed(client, database_url, "leaf-locked@example.com")

    response = client.get(
        "/api/leaf/courses/year_3_course_3",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_state"] == "locked"
    assert body["course"]["status"] == "locked"
    assert body["outline"] is None
    assert body["can_generate"] is False
    assert body["locked_reason"] == "这门课程还未解锁。"


def test_leaf_course_returns_404_for_missing_course(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'leaf-missing.db'}"
    client = TestClient(create_app(database_url=database_url))
    token = _seed(client, database_url, "leaf-missing@example.com")

    response = client.get(
        "/api/leaf/courses/year_3_course_missing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "课程不存在"
