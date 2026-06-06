from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.orchestration.agents.models import (
    ConfirmedInfoOutput,
    CurrentLearningCourse,
    LearningPathResultOutput,
    ProfileSessionOutput,
)


def _confirmed_info() -> dict:
    return {
        "current_grade": "大三",
        "major": "软件工程",
        "learning_stage": "有基础",
        "has_clear_goal": "大致有方向",
        "learning_method_preference": "项目驱动学习",
        "learning_pace_preference": "按项目里程碑推进",
        "content_preference": ["代码实践", "项目案例", "AI 对话调试"],
        "need_guidance": "需要轻量提醒",
        "knowledge_foundation": "已具备软件工程基础，AI 基础由系统补全为入门到基础",
        "strengths": "工程实现与课程学习能力",
        "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
        "experience": "平时学习，项目经验由系统补全为待强化",
        "short_term_goal": "在 3 个月内独立开发一个具备完整前后端功能的 Web 应用，并部署上线",
        "long_term_goal": "形成 AI 应用开发能力",
        "weekly_available_time": "每周 6-10 小时",
        "constraints": "平时学习节奏，避免过高强度",
    }


def _course_node(course_id: str, grade_id: str = "year_3") -> dict:
    return {
        "course_node_id": course_id,
        "grade_id": grade_id,
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
        "key_points": ["AI API 调用", "前后端集成"],
        "difficult_points": ["工程化部署"],
        "learning_sequence": ["需求拆解", "接口联调", "部署验收"],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["能独立演示完整功能"],
    }


def _learning_path() -> dict:
    grade_plans = {
        "year_1": {"grade_id": "year_1", "grade_name": "大一", "grade_goal": "夯实编程基础", "course_nodes": [_course_node("year_1_course_1", "year_1")]},
        "year_2": {"grade_id": "year_2", "grade_name": "大二", "grade_goal": "建立工程基础", "course_nodes": [_course_node("year_2_course_1", "year_2")]},
        "year_3": {"grade_id": "year_3", "grade_name": "大三", "grade_goal": "完成 AI Web 项目", "course_nodes": [_course_node("year_3_course_1", "year_3"), _course_node("year_3_course_2", "year_3")]},
        "year_4": {"grade_id": "year_4", "grade_name": "大四", "grade_goal": "就业作品集", "course_nodes": [_course_node("year_4_course_1", "year_4")]},
    }
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "独立完成 AI Web 应用",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": "大三",
            "major": "软件工程",
            "mastered_content": ["软件工程基础"],
            "weaknesses": ["数据库设计能力"],
            "constraints": ["平时学习"],
            "weekly_available_time": "每周 6-10 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进",
            "sequence_rule": "先基础后项目",
            "resource_rule": "按课程节点生成资源",
        },
        "grade_plans": grade_plans,
        "knowledge_graph": {"global_relations": [], "critical_paths": []},
        "resource_generation_contract": {"downstream_agents": ["learning_resource_agent"], "resource_directions": []},
        "dynamic_update_contract": {"trackable_metrics": ["题目得分"], "update_triggers": ["score > 70"], "adjustment_strategy": "通过后推进课程"},
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发项目课",
            "course_goal": "完成一个 AI 功能模块并接入 Web 应用",
            "time_arrangement": {"semester_scope": "上学期", "duration": "6 周", "pace_reason": "围绕平时学习节奏安排"},
            "current_focus": "正在学习 AI 应用开发项目课",
            "progress_state": "in_progress",
            "next_action": "开始第一章需求拆解",
        },
    }


def test_profile_session_output_requires_complete_confirmed_info() -> None:
    profile = ProfileSessionOutput(
        type="basic_profile",
        stage="generated",
        question_mode="question_box",
        confirmed_info=ConfirmedInfoOutput(**_confirmed_info()),
        defaulted_fields=["learning_stage"],
        question_md="画像已生成，是否继续生成学习路径？",
        question_box={"question": "下一步做什么？", "options": []},
        text="【基础学习画像总结】大三软件工程 AI 方向。",
    )

    assert profile.type == "basic_profile"
    assert profile.confirmed_info.current_grade == "大三"
    assert profile.confirmed_info.content_preference == ["代码实践", "项目案例", "AI 对话调试"]


def test_learning_path_requires_current_learning_course() -> None:
    path = LearningPathResultOutput(**_learning_path())

    assert path.schema_version == "learning_path.v2.course_node"
    assert isinstance(path.current_learning_course, CurrentLearningCourse)
    assert path.current_learning_course.course_node_id == "year_3_course_1"
    assert path.current_learning_courses[0].course_node_id == "year_3_course_1"


def test_learning_path_rejects_missing_current_learning_course() -> None:
    payload = _learning_path()
    payload.pop("current_learning_course")

    with pytest.raises(ValidationError):
        LearningPathResultOutput(**payload)


def test_learning_path_normalizes_missing_current_learning_courses() -> None:
    path = LearningPathResultOutput(**_learning_path())

    assert len(path.current_learning_courses) == 1
    assert path.current_learning_courses[0].course_node_id == path.current_learning_course.course_node_id


def test_learning_path_rejects_invalid_current_learning_course_progress_state() -> None:
    payload = _learning_path()
    payload["current_learning_course"]["progress_state"] = "unknown"

    with pytest.raises(ValidationError):
        LearningPathResultOutput(**payload)


def test_learning_path_rejects_current_learning_course_not_started_state() -> None:
    payload = _learning_path()
    payload["current_learning_course"]["progress_state"] = "not_started"

    with pytest.raises(ValidationError):
        LearningPathResultOutput(**payload)


