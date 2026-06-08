from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app.main import create_app
from app.models import UserCourseKnowledgeOutline, UserProfile, UserYearLearningPath


def _register(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "画像读取用户",
            "identifier": "profile-read@example.com",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        },
    )
    body = response.json()
    return body["access_token"], body["user"]["uid"]


def test_profile_dashboard_requires_auth(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'profile-auth.db'}"))

    response = client.get("/api/profile/dashboard")

    assert response.status_code == 401


def test_profile_dashboard_returns_empty_state_before_profile_generated(tmp_path: Path) -> None:
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'profile-empty.db'}"))
    token, _ = _register(client)

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profileCompleteness"] == 0
    assert body["profile"]["major"] == "暂未确认"
    assert body["todayLearning"]["currentCourseOutline"] is None
    assert body["recommendations"] == []


def test_profile_dashboard_treats_empty_profile_row_as_not_generated(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-empty-row.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={},
                profile_text="",
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profileCompleteness"] == 0
    assert body["profile"]["major"] == "暂未确认"
    assert body["todayLearning"]["title"] == "先完成基础画像"
    assert body["todayLearning"]["source"] == "等待画像生成"


def test_profile_dashboard_reads_saved_profile(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-saved.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "软件工程",
                        "learning_stage": "课程与项目并行",
                        "content_preference": ["视频", "代码实践"],
                        "short_term_goal": "提升 AI 应用开发能力",
                        "weaknesses": "算法和系统设计",
                        "weekly_available_time": "每周 8 小时",
                    },
                    "text": "【用户基础信息】\n大三软件工程，课程与项目并行。",
                },
                profile_text="【用户基础信息】\n大三软件工程，课程与项目并行。",
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["currentGrade"] == "大三"
    assert body["profile"]["major"] == "软件工程"
    assert body["profile"]["contentPreference"] == ["视频", "代码实践"]
    assert body["profileCompleteness"] > 0
    assert body["todayLearning"]["source"] == "基础画像 Agent"


def test_profile_dashboard_marks_unsupported_postgraduate_grade_as_needing_revision(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-unsupported-grade.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "研一",
                        "major": "软件工程",
                        "learning_stage": "项目实践",
                        "has_clear_goal": "是",
                        "learning_method_preference": "项目驱动学习",
                        "learning_pace_preference": "按项目里程碑推进",
                        "content_preference": ["代码实践"],
                        "need_guidance": "需要轻量提醒",
                        "knowledge_foundation": "软件工程基础",
                        "strengths": "工程实现",
                        "weaknesses": "部署经验不足",
                        "experience": "做过课程项目",
                        "short_term_goal": "完成 AI 功能模块",
                        "long_term_goal": "形成 AI 应用开发能力",
                        "weekly_available_time": "每周 8 小时",
                        "constraints": "时间有限",
                    },
                    "text": "当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。",
                },
                profile_text="当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。",
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["currentGrade"] == "研一"
    assert "当前学习路径只支持大一到大四" in body["profileSummaryText"]
    assert body["todayLearning"]["source"] == "等待画像修正"
    assert body["todayLearning"]["currentLearningCourse"] is None
    assert body["recommendations"] == []


def test_profile_dashboard_treats_collecting_profile_as_incomplete(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-collecting.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "collecting",
                    "stage": "basic_info",
                    "question_mode": "question_md",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "",
                        "learning_stage": "",
                        "has_clear_goal": "",
                        "learning_method_preference": "",
                        "learning_pace_preference": "",
                        "content_preference": [],
                        "need_guidance": "",
                        "knowledge_foundation": "",
                        "strengths": "",
                        "weaknesses": "",
                        "experience": "",
                        "short_term_goal": "",
                        "long_term_goal": "",
                        "weekly_available_time": "",
                        "constraints": "",
                    },
                    "defaulted_fields": [],
                    "question_md": "为了生成基础画像，请先告诉我你的专业。",
                    "question_box": {"question": "", "options": []},
                    "text": "为了生成基础画像，请先告诉我你的专业。",
                },
                profile_text="为了生成基础画像，请先告诉我你的专业。",
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["currentGrade"] == "大三"
    assert body["profile"]["major"] == "暂未确认"
    assert body["profileCompleteness"] == 6
    assert body["todayLearning"]["source"] == "等待画像生成"
    assert body["recommendations"] == []


def test_profile_dashboard_prefers_current_learning_course_from_path(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-path.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "软件工程",
                    },
                    "text": "【用户基础信息】\n大三软件工程。",
                },
                profile_text="【用户基础信息】\n大三软件工程。",
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_3": {
                            "grade_id": "year_3",
                            "grade_name": "大三",
                            "grade_goal": "完成 AI Web 项目",
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "grade_id": "year_3",
                                    "course_or_chapter_theme": "AI 应用开发项目课",
                                    "time_arrangement": {
                                        "semester_scope": "上学期",
                                        "duration": "6 周",
                                        "pace_reason": "围绕平时学习节奏安排",
                                    },
                                    "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
                                    "prerequisite_node_ids": [],
                                    "chapter_nodes": [],
                                    "core_knowledge_points": [],
                                    "key_points": ["AI API 调用"],
                                    "difficult_points": ["工程化部署"],
                                    "learning_sequence": ["需求拆解"],
                                    "knowledge_relations": [],
                                    "downstream_resource_direction_ids": [],
                                    "acceptance_criteria": ["能独立演示完整功能"],
                                },
                                {
                                    "course_node_id": "year_3_course_2",
                                    "grade_id": "year_3",
                                    "course_or_chapter_theme": "AI Web 项目实战",
                                    "time_arrangement": {
                                        "semester_scope": "下学期",
                                        "duration": "8 周",
                                        "pace_reason": "配合项目节奏推进",
                                    },
                                    "course_goal": "完成完整项目交付",
                                    "prerequisite_node_ids": [],
                                    "chapter_nodes": [],
                                    "core_knowledge_points": [],
                                    "key_points": ["联调"],
                                    "difficult_points": ["部署"],
                                    "learning_sequence": ["实现", "验收"],
                                    "knowledge_relations": [],
                                    "downstream_resource_direction_ids": [],
                                    "acceptance_criteria": ["完整交付"],
                                },
                            ],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "AI 应用开发项目课",
                        "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "围绕平时学习节奏安排",
                        },
                        "current_focus": "正在学习 AI 应用开发项目课",
                        "progress_state": "in_progress",
                        "next_action": "开始第一章需求拆解",
                    },
                },
            )
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=uid,
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发项目课",
                outline_data={
                    "course_id": "year_3_course_1",
                    "course_name": "AI 应用开发项目课",
                    "grade_year": "year_3",
                    "personalization_summary": "先完成需求拆解，再进入接口接入与联调。",
                    "sections": [
                        {
                            "section_id": "1",
                            "parent_section_id": None,
                            "depth": 1,
                            "title": "需求拆解",
                            "order_index": 1,
                            "description": "确认功能边界与验收标准。",
                            "key_knowledge_points": ["功能边界"],
                        }
                    ],
                    "learning_sequence": ["1"],
                    "total_estimated_hours": "6-8 小时",
                },
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["todayLearning"]["source"] == "学习路径智能体"
    assert body["todayLearning"]["currentLearningCourse"]["course_node_id"] == "year_3_course_1"
    assert body["todayLearning"]["currentCourseDetail"]["course_node_id"] == "year_3_course_1"
    assert body["todayLearning"]["currentCourseOutline"]["course_id"] == "year_3_course_1"
    assert [course["course_node_id"] for course in body["todayLearning"]["gradeCourses"]] == [
        "year_3_course_1",
        "year_3_course_2",
    ]
    assert body["todayLearning"]["followingCourses"][0]["course_node_id"] == "year_3_course_2"


def test_profile_dashboard_keeps_learning_path_visible_when_profile_is_collecting(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-collecting-path.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "collecting",
                    "stage": "basic_info",
                    "question_mode": "question_md",
                    "confirmed_info": {
                        "current_grade": "大三",
                        "major": "",
                        "learning_stage": "",
                        "has_clear_goal": "",
                        "learning_method_preference": "",
                        "learning_pace_preference": "",
                        "content_preference": [],
                        "need_guidance": "",
                        "knowledge_foundation": "",
                        "strengths": "",
                        "weaknesses": "",
                        "experience": "",
                        "short_term_goal": "",
                        "long_term_goal": "",
                        "weekly_available_time": "",
                        "constraints": "",
                    },
                    "defaulted_fields": [],
                    "question_md": "为了生成基础画像，请先告诉我你的专业。",
                    "question_box": {"question": "", "options": []},
                    "text": "为了生成基础画像，请先告诉我你的专业。",
                },
                profile_text="为了生成基础画像，请先告诉我你的专业。",
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_3": {
                            "grade_id": "year_3",
                            "grade_name": "大三",
                            "grade_goal": "完成 AI Web 项目",
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "grade_id": "year_3",
                                    "course_or_chapter_theme": "AI 应用开发项目课",
                                    "time_arrangement": {
                                        "semester_scope": "上学期",
                                        "duration": "6 周",
                                        "pace_reason": "围绕平时学习节奏安排",
                                    },
                                    "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
                                    "prerequisite_node_ids": [],
                                    "chapter_nodes": [],
                                    "core_knowledge_points": [],
                                    "key_points": ["AI API 调用"],
                                    "difficult_points": ["工程化部署"],
                                    "learning_sequence": ["需求拆解"],
                                    "knowledge_relations": [],
                                    "downstream_resource_direction_ids": [],
                                    "acceptance_criteria": ["能独立演示完整功能"],
                                },
                            ],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "AI 应用开发项目课",
                        "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "围绕平时学习节奏安排",
                        },
                        "current_focus": "正在学习 AI 应用开发项目课",
                        "progress_state": "in_progress",
                        "next_action": "开始第一章需求拆解",
                    },
                },
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["profileCompleteness"] == 6
    assert body["todayLearning"]["source"] == "学习路径智能体"
    assert body["todayLearning"]["currentLearningCourse"]["course_node_id"] == "year_3_course_1"
    assert body["recommendations"] == []


def test_profile_dashboard_prefers_latest_updated_learning_path_when_multiple_years_exist(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-latest-path.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "大四",
                        "major": "软件工程",
                    },
                    "text": "【用户基础信息】\n大四软件工程。",
                },
                profile_text="【用户基础信息】\n大四软件工程。",
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_3": {
                            "grade_id": "year_3",
                            "grade_name": "大三",
                            "grade_goal": "完成 AI Web 项目",
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "grade_id": "year_3",
                                    "course_or_chapter_theme": "旧路径课程",
                                    "time_arrangement": {
                                        "semester_scope": "上学期",
                                        "duration": "6 周",
                                        "pace_reason": "围绕平时学习节奏安排",
                                    },
                                    "course_goal": "完成旧路径课程",
                                    "prerequisite_node_ids": [],
                                    "chapter_nodes": [],
                                    "core_knowledge_points": [],
                                    "key_points": ["旧知识点"],
                                    "difficult_points": ["旧难点"],
                                    "learning_sequence": ["旧步骤"],
                                    "knowledge_relations": [],
                                    "downstream_resource_direction_ids": [],
                                    "acceptance_criteria": ["旧验收"],
                                },
                            ],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "旧路径课程",
                        "course_goal": "完成旧路径课程",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "围绕平时学习节奏安排",
                        },
                        "current_focus": "正在学习旧路径课程",
                        "progress_state": "in_progress",
                        "next_action": "继续旧路径课程",
                    },
                },
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=uid,
                grade_year="year_4",
                learning_topic="AI 应用开发",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_4": {
                            "grade_id": "year_4",
                            "grade_name": "大四",
                            "grade_goal": "完成毕业项目",
                            "course_nodes": [
                                {
                                    "course_node_id": "year_4_course_1",
                                    "grade_id": "year_4",
                                    "course_or_chapter_theme": "最新路径课程",
                                    "time_arrangement": {
                                        "semester_scope": "下学期",
                                        "duration": "8 周",
                                        "pace_reason": "围绕毕业项目推进",
                                    },
                                    "course_goal": "完成最新路径课程",
                                    "prerequisite_node_ids": [],
                                    "chapter_nodes": [],
                                    "core_knowledge_points": [],
                                    "key_points": ["新知识点"],
                                    "difficult_points": ["新难点"],
                                    "learning_sequence": ["新步骤"],
                                    "knowledge_relations": [],
                                    "downstream_resource_direction_ids": [],
                                    "acceptance_criteria": ["新验收"],
                                },
                            ],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_4",
                        "course_node_id": "year_4_course_1",
                        "course_or_chapter_theme": "最新路径课程",
                        "course_goal": "完成最新路径课程",
                        "time_arrangement": {
                            "semester_scope": "下学期",
                            "duration": "8 周",
                            "pace_reason": "围绕毕业项目推进",
                        },
                        "current_focus": "正在学习最新路径课程",
                        "progress_state": "in_progress",
                        "next_action": "继续最新路径课程",
                    },
                },
                updated_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["todayLearning"]["currentLearningCourse"]["course_node_id"] == "year_4_course_1"
    assert body["todayLearning"]["currentCourseDetail"]["course_node_id"] == "year_4_course_1"
    assert body["todayLearning"]["title"] == "最新路径课程"


def test_profile_dashboard_falls_back_to_next_valid_path_when_latest_path_is_invalid(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'profile-fallback-valid-path.db'}"
    client = TestClient(create_app(database_url=database_url))
    token, uid = _register(client)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    with Session(engine) as session:
        session.add(
            UserProfile(
                user_uid=uid,
                profile_data={
                    "type": "basic_profile",
                    "stage": "generated",
                    "confirmed_info": {
                        "current_grade": "大四",
                        "major": "软件工程",
                    },
                    "text": "【用户基础信息】\n大四软件工程。",
                },
                profile_text="【用户基础信息】\n大四软件工程。",
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=uid,
                grade_year="year_3",
                learning_topic="AI 应用开发",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_3": {
                            "grade_id": "year_3",
                            "grade_name": "大三",
                            "grade_goal": "完成 AI Web 项目",
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "grade_id": "year_3",
                                    "course_or_chapter_theme": "有效路径课程",
                                    "time_arrangement": {
                                        "semester_scope": "上学期",
                                        "duration": "6 周",
                                        "pace_reason": "围绕平时学习节奏安排",
                                    },
                                    "course_goal": "完成有效路径课程",
                                    "prerequisite_node_ids": [],
                                    "chapter_nodes": [],
                                    "core_knowledge_points": [],
                                    "key_points": ["有效知识点"],
                                    "difficult_points": ["有效难点"],
                                    "learning_sequence": ["有效步骤"],
                                    "knowledge_relations": [],
                                    "downstream_resource_direction_ids": [],
                                    "acceptance_criteria": ["有效验收"],
                                },
                            ],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "有效路径课程",
                        "course_goal": "完成有效路径课程",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "围绕平时学习节奏安排",
                        },
                        "current_focus": "继续有效路径课程",
                        "progress_state": "in_progress",
                        "next_action": "继续有效路径课程",
                    },
                },
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid=uid,
                grade_year="year_4",
                learning_topic="AI 应用开发",
                path_data={
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_4": {
                            "grade_id": "year_4",
                            "grade_name": "大四",
                            "grade_goal": "完成毕业项目",
                            "course_nodes": [],
                        },
                    },
                    "current_learning_course": {
                        "grade_id": "year_4",
                        "course_node_id": "year_4_course_missing",
                        "course_or_chapter_theme": "损坏路径课程",
                        "course_goal": "完成损坏路径课程",
                        "time_arrangement": {
                            "semester_scope": "下学期",
                            "duration": "8 周",
                            "pace_reason": "围绕毕业项目推进",
                        },
                        "current_focus": "这条路径无法定位到课程节点",
                        "progress_state": "in_progress",
                        "next_action": "等待回退到下一条有效路径",
                    },
                },
                updated_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
            )
        )
        session.commit()

    response = client.get("/api/profile/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["todayLearning"]["currentLearningCourse"]["course_node_id"] == "year_3_course_1"
    assert body["todayLearning"]["currentCourseDetail"]["course_node_id"] == "year_3_course_1"
    assert body["todayLearning"]["title"] == "有效路径课程"
