"""Contract tests for the learning path agent."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserYearLearningPath
from app.orchestration.agents.learning_path import (
    _build_analysis_input,
    _build_learning_path_from_plan,
    _build_local_learning_path,
    _grade_year_from_profile,
    _topic_from_profile,
    _validate_learning_path_contract,
    create_learning_path_agent_node,
    run_learning_path_agent,
)
from app.orchestration.agents.models import LearningPathPlanOutput
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT
from app.services.learning_path_service import upsert_year_learning_path
from tests.postgres import postgresql_test_url


def _complete_profile(
    summary_text: str = "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线。",
) -> dict:
    return {
        "type": "basic_profile",
        "stage": "generated",
        "question_mode": "question_box",
        "confirmed_info": {
            "current_grade": "大3",
            "major": "软件工程",
            "learning_stage": "有基础",
            "has_clear_goal": "大致有方向",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例", "AI 对话调试"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全",
            "strengths": "工程实现与课程学习能力",
            "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
            "experience": "平时学习",
            "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
            "long_term_goal": "形成AI 应用开发方向的应用开发能力",
            "weekly_available_time": "每周 6-10 小时",
            "constraints": "平时学习节奏，避免过高强度",
        },
        "defaulted_fields": [],
        "question_md": "画像已生成，是否进入学习路径草案智能体？",
        "question_box": {
            "question": "画像已生成，下一步要进入学习路径草案智能体吗？",
            "options": [],
        },
        "text": summary_text,
        "summary_text": summary_text,
    }


def _confirmed_intake(
    *,
    grade_year: str = "year_3",
    grade_name: str = "大三",
    learning_topic: str = "数据结构",
    course_titles: list[str] | None = None,
) -> dict:
    titles = course_titles or [
        "数据结构入门与复杂度基础",
        "线性结构实践",
        "树与递归基础",
        "查找排序与哈希",
        "图结构与综合项目",
    ]
    return {
        "type": "learning_path_intake",
        "status": "confirmed",
        "grade_year": grade_year,
        "grade_name": grade_name,
        "learning_topic": learning_topic,
        "courses": [
            {
                "title": title,
                "purpose": f"完成 {title} 的关键训练",
                "source_textbook_id": f"textbook-{index}",
                "source_textbook_title": f"{learning_topic}教材 {index}",
                "source_outline_section_ids": [
                    f"textbook-{index}-section-1",
                    f"textbook-{index}-section-2",
                ],
            }
            for index, title in enumerate(titles, start=1)
        ],
        "recommendation_reasons": [f"目标是学习{learning_topic}"],
        "user_modification_summary": "",
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }


AI_COURSE_TITLES = [
    "AI Agent 最小可用闭环搭建",
    "AI Agent 多节点编排与联调",
    "AI Agent 工程化调试与评测",
    "AI Agent 部署上线与稳定性复盘",
]


def _llm_learning_path_payload() -> dict:
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": "AI 应用开发",
            "goal_type": "项目实践",
            "desired_outcome": "独立完成一个 AI 应用项目",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": "大三",
            "major": "软件工程",
            "mastered_content": ["软件工程基础"],
            "weaknesses": ["多智能体编排经验"],
            "constraints": ["平时学习节奏"],
            "weekly_available_time": "每周 6-10 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进",
            "sequence_rule": "先基础后项目，先单体闭环后多智能体协作",
            "resource_rule": "按课程节点生成资源",
        },
        "grade_plans": {
            "year_1": {
                "grade_id": "year_1",
                "grade_name": "大一",
                "grade_goal": "夯实基础",
                "course_nodes": [
                    {
                        "course_node_id": "year_1_course_1",
                        "grade_id": "year_1",
                        "course_or_chapter_theme": "编程与算法基础",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "8 周",
                            "pace_reason": "先打基础",
                        },
                        "course_goal": "完成编程基础训练",
                        "prerequisite_node_ids": [],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["Python 基础"],
                        "difficult_points": ["抽象建模"],
                        "learning_sequence": ["语法", "数据结构", "算法"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["完成基础练习"],
                    }
                ],
            },
            "year_2": {
                "grade_id": "year_2",
                "grade_name": "大二",
                "grade_goal": "建立工程能力",
                "course_nodes": [
                    {
                        "course_node_id": "year_2_course_1",
                        "grade_id": "year_2",
                        "course_or_chapter_theme": "工程化 Web 开发基础",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "8 周",
                            "pace_reason": "建立前后端协作能力",
                        },
                        "course_goal": "完成基础 Web 应用",
                        "prerequisite_node_ids": ["year_1_course_1"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["接口设计"],
                        "difficult_points": ["数据建模"],
                        "learning_sequence": ["接口", "数据库", "联调"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["完成一个基础 Web 应用"],
                    }
                ],
            },
            "year_3": {
                "grade_id": "year_3",
                "grade_name": "大三",
                "grade_goal": "完成 AI 项目闭环",
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "grade_id": "year_3",
                        "course_or_chapter_theme": "AI 应用开发基础能力搭建",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "6 周",
                            "pace_reason": "围绕平时学习节奏安排",
                        },
                        "course_goal": "完成最小功能闭环",
                        "prerequisite_node_ids": ["year_2_course_1"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["Prompt 设计", "前后端联调"],
                        "difficult_points": ["错误处理与重试"],
                        "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": [
                            "完成一个可运行的 AI 功能模块并接入 Web 应用"
                        ],
                    },
                    {
                        "course_node_id": "year_3_course_2",
                        "grade_id": "year_3",
                        "course_or_chapter_theme": "AI 应用开发项目实战",
                        "time_arrangement": {
                            "semester_scope": "下学期",
                            "duration": "8 周",
                            "pace_reason": "在基础闭环后进入复杂项目",
                        },
                        "course_goal": "完成课程级项目",
                        "prerequisite_node_ids": ["year_3_course_1"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["LangGraph 编排", "SSE 流式交互"],
                        "difficult_points": ["线上稳定性"],
                        "learning_sequence": ["架构设计", "多智能体联调", "部署验收"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["支持真实用户流程与部署演示"],
                    },
                ],
            },
            "year_4": {
                "grade_id": "year_4",
                "grade_name": "大四",
                "grade_goal": "沉淀作品集",
                "course_nodes": [
                    {
                        "course_node_id": "year_4_course_1",
                        "grade_id": "year_4",
                        "course_or_chapter_theme": "就业级作品集与迭代优化",
                        "time_arrangement": {
                            "semester_scope": "上学期",
                            "duration": "10 周",
                            "pace_reason": "围绕求职展示打磨",
                        },
                        "course_goal": "形成作品集",
                        "prerequisite_node_ids": ["year_3_course_2"],
                        "chapter_nodes": [],
                        "core_knowledge_points": [],
                        "key_points": ["项目复盘"],
                        "difficult_points": ["方案表达"],
                        "learning_sequence": ["项目复盘", "优化迭代", "作品集整理"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [],
                        "acceptance_criteria": ["形成就业级项目作品集"],
                    }
                ],
            },
        },
        "knowledge_graph": {"global_relations": [], "critical_paths": []},
        "resource_generation_contract": {
            "downstream_agents": ["learning_resource_agent"],
            "resource_directions": [],
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["项目里程碑完成度"],
            "update_triggers": ["里程碑完成"],
            "adjustment_strategy": "根据验收结果调整课程推进节奏",
        },
        "current_learning_course": {
            "grade_id": "year_3",
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发基础能力搭建",
            "course_goal": "完成最小功能闭环",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "6 周",
                "pace_reason": "围绕平时学习节奏安排",
            },
            "current_focus": "优先搭建最小闭环并补齐错误处理能力",
            "progress_state": "in_progress",
            "next_action": "先完成需求拆解并确认验收边界",
        },
    }


def _llm_learning_path_plan_payload(
    course_themes: list[str],
    *,
    goal_type: str = "项目实践",
    grade_goal: str = "完成 AI 项目闭环",
    desired_outcome: str = "完成一个可上线并可演示的 AI Agent 项目",
    four_year_outcome: str = "形成就业级项目作品集",
    current_focus: str = "先聚焦最小可用闭环与部署稳定性",
    next_action: str = "先完成第一门课的需求拆解与验收边界确认",
) -> dict:
    return {
        "goal_type": goal_type,
        "grade_goal": grade_goal,
        "desired_outcome": desired_outcome,
        "four_year_outcome": four_year_outcome,
        "current_focus": current_focus,
        "next_action": next_action,
        "course_specs": [
            {
                "theme": theme,
                "semester_scope": "上学期" if index < len(course_themes) else "下学期",
                "duration": "6 周" if index != 2 else "8 周",
                "pace_reason": "围绕周末集中与上线目标安排",
                "goal": f"完成 {theme} 对应的关键训练",
                "stage_titles": [
                    f"{theme}需求拆解",
                    f"{theme}实现联调",
                    f"{theme}验收复盘",
                ],
                "key_points": [
                    f"{theme}能力点 1",
                    f"{theme}能力点 2",
                    f"{theme}能力点 3",
                ],
                "difficult_points": [f"{theme}部署稳定性", f"{theme}调试与回归"],
                "acceptance_criteria": [f"完成 {theme} 的阶段验收并可演示"],
                "difficulty_level": "中级",
            }
            for index, theme in enumerate(course_themes, start=1)
        ],
    }


def _single_year_learning_path_payload(
    grade_year: str,
    grade_name: str,
    grade_goal: str,
    course_themes: list[str],
    *,
    topic: str = "AI 应用开发",
) -> dict:
    course_nodes: list[dict] = []
    for index, theme in enumerate(course_themes, start=1):
        course_nodes.append(
            {
                "course_node_id": f"{grade_year}_course_{index}",
                "grade_id": grade_year,
                "course_or_chapter_theme": theme,
                "time_arrangement": {
                    "semester_scope": "上学期"
                    if index < len(course_themes)
                    else "下学期",
                    "duration": "6 周",
                    "pace_reason": "围绕当前阶段学习目标逐步推进",
                },
                "course_goal": f"完成 {theme} 对应的核心训练",
                "prerequisite_node_ids": [f"{grade_year}_course_{index - 1}"]
                if index > 1
                else [],
                "chapter_nodes": [
                    {
                        "chapter_node_id": f"{grade_year}_course_{index}_chapter_1",
                        "chapter_theme": f"{theme} 拆解",
                        "knowledge_hierarchy": [],
                        "core_knowledge_point_ids": [],
                        "key_points": [f"{theme} 重点"],
                        "difficult_points": [f"{theme} 难点"],
                        "prerequisite_node_ids": [],
                        "learning_sequence": [f"{theme} 学习顺序"],
                        "knowledge_relations": [],
                        "downstream_resource_direction_ids": [
                            f"{grade_year}_course_{index}_resource"
                        ],
                    }
                ],
                "core_knowledge_points": [
                    {
                        "knowledge_point_id": f"{grade_year}_course_{index}_kp_1",
                        "name": f"{theme} 核心知识",
                        "parent_knowledge_point_id": None,
                        "level": "核心",
                        "description": f"{theme} 的关键知识点",
                        "mastery_standard": f"能把 {theme} 用到项目任务里",
                    }
                ],
                "key_points": [f"{theme} 重点"],
                "difficult_points": [f"{theme} 难点"],
                "learning_sequence": [f"{theme} 学习顺序"],
                "knowledge_relations": [],
                "downstream_resource_direction_ids": [
                    f"{grade_year}_course_{index}_resource"
                ],
                "acceptance_criteria": [f"完成 {theme} 的阶段验收"],
            }
        )

    current_course = course_nodes[0]
    return {
        "schema_version": "learning_path.v2.course_node",
        "learning_goal": {
            "target_course_or_skill": topic,
            "goal_type": "项目实践",
            "desired_outcome": f"围绕 {topic} 完成目标学年学习闭环",
            "four_year_outcome": "形成就业级项目作品集",
        },
        "learner_baseline": {
            "current_grade": grade_name,
            "major": "软件工程",
            "mastered_content": ["软件工程基础"],
            "weaknesses": ["工程化能力"],
            "constraints": ["平时学习节奏"],
            "weekly_available_time": "每周 6-10 小时",
        },
        "planning_rules": {
            "node_unit": "course_node",
            "grade_boundary_rule": "按年级递进",
            "sequence_rule": "同一年级内按课程顺序递进",
            "resource_rule": "按课程节点生成资源",
        },
        "grade_plans": {
            grade_year: {
                "grade_id": grade_year,
                "grade_name": grade_name,
                "grade_goal": grade_goal,
                "course_nodes": course_nodes,
            }
        },
        "knowledge_graph": {
            "global_relations": [],
            "critical_paths": [
                {
                    "path_id": f"{grade_year}_critical_path",
                    "purpose": f"{grade_name}主学习路径",
                    "ordered_node_ids": [
                        course["course_node_id"] for course in course_nodes
                    ],
                }
            ],
        },
        "resource_generation_contract": {
            "downstream_agents": ["learning_resource_agent"],
            "resource_directions": [
                {
                    "resource_direction_id": f"{course['course_node_id']}_resource",
                    "target_node_ids": [course["course_node_id"]],
                    "resource_type": "文档",
                    "generation_goal": f"围绕 {course['course_or_chapter_theme']} 生成资源",
                    "content_requirements": ["包含阶段任务", "包含验收标准"],
                    "difficulty_level": "中级"
                    if grade_year in {"year_3", "year_4"}
                    else "基础",
                }
                for course in course_nodes
            ],
        },
        "dynamic_update_contract": {
            "trackable_metrics": ["项目里程碑完成度"],
            "update_triggers": ["milestone completed"],
            "adjustment_strategy": "结合已完成课程数调整后续课程重点",
        },
        "current_learning_course": {
            "grade_id": grade_year,
            "course_node_id": current_course["course_node_id"],
            "course_or_chapter_theme": current_course["course_or_chapter_theme"],
            "course_goal": current_course["course_goal"],
            "time_arrangement": current_course["time_arrangement"],
            "current_focus": f"优先完成 {current_course['course_or_chapter_theme']}",
            "progress_state": "in_progress",
            "next_action": "先完成第一阶段任务拆解",
        },
    }


def test_grade_year_from_profile_maps_chinese_grade() -> None:
    assert (
        _grade_year_from_profile({"confirmed_info": {"current_grade": "大3"}})
        == "year_3"
    )
    assert (
        _grade_year_from_profile({"confirmed_info": {"current_grade": "大三"}})
        == "year_3"
    )


def test_grade_year_from_profile_rejects_unsupported_postgraduate_grade() -> None:
    assert _grade_year_from_profile({"confirmed_info": {"current_grade": "研一"}}) == ""


def test_topic_from_profile_prefers_profile_direction() -> None:
    profile = {
        "confirmed_info": {
            "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
            "long_term_goal": "形成AI 应用开发方向的应用开发能力",
        },
        "summary_text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线。",
    }

    assert _topic_from_profile(profile) == "AI 应用开发"


def test_topic_from_profile_uses_vibecoding_when_user_said_learning_vibecoding() -> (
    None
):
    profile = {
        "confirmed_info": {
            "short_term_goal": "找工作，学习vibecoding",
            "long_term_goal": "",
        },
        "summary_text": "【基础学习画像总结】大三软件工程，目标是找工作，想学习vibecoding。",
    }

    assert _topic_from_profile(profile) == "vibecoding"


def test_validate_learning_path_contract_rejects_missing_current_course() -> None:
    result = _validate_learning_path_contract(
        {"schema_version": "learning_path.v2.course_node", "grade_plans": {}}
    )

    assert result == "学习路径缺少 current_learning_course。"


def test_validate_learning_path_contract_rejects_current_course_that_is_not_active_or_completed() -> (
    None
):
    payload = _llm_learning_path_payload()
    payload["current_learning_course"]["progress_state"] = "not_started"

    result = _validate_learning_path_contract(payload)

    assert (
        result
        == "current_learning_course.progress_state 必须是 in_progress 或 completed。"
    )


def test_validate_learning_path_contract_rejects_grade_with_less_than_three_courses() -> (
    None
):
    payload = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        ["AI 应用开发基础能力搭建", "AI 应用开发项目实战"],
    )

    result = _validate_learning_path_contract(payload)

    assert result == "当前学年课程数量必须在 4 到 8 门之间。"


def test_learning_path_prompt_mentions_json_output() -> None:
    assert "json" in LEARNING_PATH_AGENT_SYSTEM_PROMPT.lower()
    assert "先分析" in LEARNING_PATH_AGENT_SYSTEM_PROMPT
    assert "course_specs" in LEARNING_PATH_AGENT_SYSTEM_PROMPT
    assert "4-8 门课程" in LEARNING_PATH_AGENT_SYSTEM_PROMPT
    assert "必须且只能输出 3 门课程" not in LEARNING_PATH_AGENT_SYSTEM_PROMPT


def test_build_analysis_input_requires_confirmed_intake() -> None:
    intake = _confirmed_intake()
    intake["status"] = "draft"

    with pytest.raises(
        ValueError,
        match="learning_path_intake.status is not confirmed",
    ):
        _build_analysis_input(
            _complete_profile(),
            "year_3",
            "数据结构",
            "",
            [],
            intake,
        )


def test_build_learning_path_from_plan_preserves_confirmed_course_source_binding() -> (
    None
):
    intake = _confirmed_intake(
        learning_topic="AI 应用开发",
        course_titles=AI_COURSE_TITLES,
    )
    plan_data = _llm_learning_path_plan_payload(
        [
            "模型返回标题 1",
            "模型返回标题 2",
            "模型返回标题 3",
            "模型返回标题 4",
        ]
    )

    path = _build_learning_path_from_plan(
        _complete_profile(),
        grade_year="year_3",
        learning_topic="AI 应用开发",
        plan_data=plan_data,
        intake_courses=intake["courses"],
    )

    course_nodes = path["grade_plans"]["year_3"]["course_nodes"]
    for index, course_node in enumerate(course_nodes):
        intake_course = intake["courses"][index]
        assert course_node["course_or_chapter_theme"] == intake_course["title"]
        assert course_node["source_textbook_id"] == intake_course["source_textbook_id"]
        assert (
            course_node["source_textbook_title"]
            == intake_course["source_textbook_title"]
        )
        assert (
            course_node["source_outline_section_ids"]
            == intake_course["source_outline_section_ids"]
        )
        assert (
            course_node["course_stage_plan"]
            == plan_data["course_specs"][index]["stage_titles"]
        )


def test_build_learning_path_from_full_path_uses_intake_source_binding() -> None:
    intake = _confirmed_intake(
        learning_topic="AI 应用开发",
        course_titles=AI_COURSE_TITLES,
    )
    plan_data = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        [
            "模型返回标题 1",
            "模型返回标题 2",
            "模型返回标题 3",
            "模型返回标题 4",
        ],
    )
    for index, course_node in enumerate(
        plan_data["grade_plans"]["year_3"]["course_nodes"],
        start=1,
    ):
        course_node["source_textbook_id"] = f"model-textbook-{index}"
        course_node["source_textbook_title"] = f"模型教材 {index}"
        course_node["source_outline_section_ids"] = [f"model-section-{index}"]
        course_node["course_stage_plan"] = [f"模型阶段 {index}"]

    path = _build_learning_path_from_plan(
        _complete_profile(),
        grade_year="year_3",
        learning_topic="AI 应用开发",
        plan_data=plan_data,
        intake_courses=intake["courses"],
    )

    course_nodes = path["grade_plans"]["year_3"]["course_nodes"]
    for index, course_node in enumerate(course_nodes):
        intake_course = intake["courses"][index]
        assert course_node["course_or_chapter_theme"] == intake_course["title"]
        assert course_node["source_textbook_id"] == intake_course["source_textbook_id"]
        assert (
            course_node["source_textbook_title"]
            == intake_course["source_textbook_title"]
        )
        assert (
            course_node["source_outline_section_ids"]
            == intake_course["source_outline_section_ids"]
        )


def test_data_structure_learning_path_uses_confirmed_textbook_sections_over_model_sources() -> (
    None
):
    intake = _confirmed_intake(
        learning_topic="数据结构",
        course_titles=[
            "复杂度分析与线性结构基础",
            "树与递归基础",
            "查找排序与哈希",
            "图结构与综合项目",
        ],
    )
    intake["courses"][0]["source_textbook_id"] = "textbook-data-structures"
    intake["courses"][0]["source_textbook_title"] = "数据结构教程"
    intake["courses"][0]["source_outline_section_ids"] = ["1.1", "1.2"]

    plan_data = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成数据结构基础训练",
        [
            "模型改写的复杂度课程",
            "模型改写的树课程",
            "模型改写的排序课程",
            "模型改写的图课程",
        ],
    )
    first_course = plan_data["grade_plans"]["year_3"]["course_nodes"][0]
    first_course["source_textbook_id"] = "model-textbook"
    first_course["source_textbook_title"] = "模型替换教材"
    first_course["source_outline_section_ids"] = ["9.9"]

    path = _build_learning_path_from_plan(
        _complete_profile(),
        grade_year="year_3",
        learning_topic="数据结构",
        plan_data=plan_data,
        intake_courses=intake["courses"],
    )

    first_node = path["grade_plans"]["year_3"]["course_nodes"][0]
    assert first_node["course_or_chapter_theme"] == "复杂度分析与线性结构基础"
    assert first_node["source_textbook_id"] == "textbook-data-structures"
    assert first_node["source_textbook_title"] == "数据结构教程"
    assert first_node["source_outline_section_ids"] == ["1.1", "1.2"]


def test_build_analysis_input_forbids_replacing_confirmed_textbook_sources() -> None:
    query = _build_analysis_input(
        _complete_profile(),
        "year_3",
        "AI 应用开发",
        "",
        [],
        _confirmed_intake(
            learning_topic="AI 应用开发",
            course_titles=AI_COURSE_TITLES,
        ),
    )

    assert "课程标题和来源绑定必须来自已确认课程草案" in query
    assert "模型不得替换教材来源" in query


def test_build_analysis_input_declares_downstream_resource_agent_order() -> None:
    query = _build_analysis_input(
        _complete_profile(),
        "year_3",
        "数据结构",
        "",
        [],
        _confirmed_intake(
            learning_topic="数据结构",
            course_titles=[
                "复杂度分析与线性结构基础",
                "树与递归基础",
                "查找排序与哈希",
                "图结构与综合项目",
            ],
        ),
    )

    assert "resource_generation_contract 必须声明下游顺序" in query
    assert (
        "course_knowledge_agent -> section_markdown_agent -> "
        "section_video_search_agent -> section_html_animation_agent"
    ) in query
    assert "路径课程的 source_outline_section_ids 必须传递给大纲智能体" in query


def test_learning_path_prompt_declares_prompt_budget_metadata() -> None:
    payload = _build_analysis_input(
        _complete_profile(),
        "year_3",
        "数据结构",
        "",
        [],
        _confirmed_intake(
            learning_topic="数据结构",
            course_titles=[
                "复杂度分析与线性结构基础",
                "树与递归基础",
                "查找排序与哈希",
                "图结构与综合项目",
            ],
        ),
    )

    assert "prompt_budget_applied" in payload


def test_build_local_learning_path_rejects_unbound_fallback_generation() -> None:
    with pytest.raises(ValueError, match="已确认课程草案"):
        _build_local_learning_path(
            _complete_profile(),
            grade_year="year_3",
            learning_topic="AI 应用开发",
        )


def test_run_learning_path_agent_uses_structured_llm_for_default_query(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return LearningPathPlanOutput(
                **_llm_learning_path_plan_payload(
                    [
                        "AI Agent 最小可用闭环搭建",
                        "AI Agent 多节点编排与联调",
                        "AI Agent 工程化调试与评测",
                        "AI Agent 部署上线与稳定性复盘",
                    ]
                )
            )

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(postgresql_test_url(tmp_path, "learning-path-thinking"))
    set_engine(engine)
    init_db(engine)

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_learning_path_agent(
                {
                    "user_id": "00000000-0000-0000-0000-000000000001",
                    "query": "直接帮我生成，不确定的你随便帮我填",
                    "profile": _complete_profile(),
                    "learning_path_intake": _confirmed_intake(
                        learning_topic="AI 应用开发",
                        course_titles=AI_COURSE_TITLES,
                    ),
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is LearningPathPlanOutput
    assert "用户画像关键信息" in str(captured["query"])
    assert "输出前先完成以下分析" in str(captured["query"])
    assert (
        result["year_learning_path"]["current_learning_course"]["course_node_id"]
        == "year_3_course_1"
    )


def test_run_learning_path_agent_accepts_missing_desired_outcome_in_structured_plan(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            plan_payload = _llm_learning_path_plan_payload(
                [
                    "AI Agent 最小可用闭环搭建",
                    "AI Agent 编排与状态管理",
                    "AI Agent 工程化调试与评测",
                    "AI Agent 部署上线与监控",
                ]
            )
            plan_payload.pop("desired_outcome")
            return LearningPathPlanOutput(**plan_payload)

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-missing-desired-outcome")
    )
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(
            User(
                uid="00000000-0000-0000-0000-000000000010",
                username="课程用户",
                identifier="learning-path-10@example.com",
            )
        )
        session.commit()

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_learning_path_agent(
                {
                    "user_id": "00000000-0000-0000-0000-000000000010",
                    "query": "进入学习路径草案智能体",
                    "profile": _complete_profile(),
                    "learning_path_intake": _confirmed_intake(
                        learning_topic="AI 应用开发",
                        course_titles=AI_COURSE_TITLES,
                    ),
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is LearningPathPlanOutput
    assert (
        result["year_learning_path"]["learning_goal"]["desired_outcome"]
        == "完成一个围绕 AI 应用开发 的课程级项目"
    )
    assert (
        result["year_learning_path"]["current_learning_course"]["course_node_id"]
        == "year_3_course_1"
    )

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000010", "year_3")
        )

    assert row is not None
    assert (
        row.path_data["learning_goal"]["desired_outcome"]
        == "完成一个围绕 AI 应用开发 的课程级项目"
    )


def test_run_learning_path_agent_rejects_incomplete_basic_profile(
    tmp_path: Path,
) -> None:
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-incomplete-profile")
    )
    set_engine(engine)
    init_db(engine)

    result = asyncio.run(
        run_learning_path_agent(
            {
                "user_id": "00000000-0000-0000-0000-000000000099",
                "query": "进入学习路径草案智能体",
                "profile": {"type": "basic_profile", "summary_text": "旧画像摘要"},
                "messages": [],
            },
            object(),
        )
    )

    assert result == {"error": "请先完成基础画像再生成学习路径。", "hard_error": True}


def test_run_learning_path_agent_rejects_unsupported_postgraduate_grade(
    tmp_path: Path,
) -> None:
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-unsupported-grade")
    )
    set_engine(engine)
    init_db(engine)

    profile = _complete_profile()
    profile["confirmed_info"]["current_grade"] = "研一"
    profile["summary_text"] = (
        "【基础学习画像总结】研一软件工程，当前以AI 应用开发为主线。"
    )
    profile["text"] = profile["summary_text"]

    result = asyncio.run(
        run_learning_path_agent(
            {
                "user_id": "00000000-0000-0000-0000-000000000098",
                "query": "进入学习路径草案智能体",
                "profile": profile,
                "messages": [],
            },
            object(),
        )
    )

    assert result == {
        "error": "当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。",
        "hard_error": True,
    }


def test_run_learning_path_agent_returns_error_when_structured_llm_setup_fails(
    tmp_path: Path,
) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("fallback should not call structured llm successfully")

    engine = build_engine(postgresql_test_url(tmp_path, "learning-path-fallback"))
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "query": "直接帮我生成，不确定的你随便帮我填",
        "profile": {
            "type": "basic_profile",
            "stage": "generated",
            "question_mode": "question_box",
            "confirmed_info": {
                "current_grade": "大3",
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
                "experience": "平时学习",
                "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
                "long_term_goal": "形成AI 应用开发方向的应用开发能力",
                "weekly_available_time": "每周 6-10 小时",
                "constraints": "平时学习节奏，避免过高强度",
            },
            "defaulted_fields": [],
            "question_md": "画像已生成，是否进入学习路径草案智能体？",
            "question_box": {
                "question": "画像已生成，下一步要进入学习路径草案智能体吗？",
                "options": [],
            },
            "text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线，适合采用项目驱动学习。",
            "summary_text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线，适合采用项目驱动学习。",
        },
        "learning_path_intake": _confirmed_intake(
            learning_topic="AI 应用开发",
            course_titles=AI_COURSE_TITLES,
        ),
        "messages": [],
    }

    result = asyncio.run(run_learning_path_agent(state, ExplodingLlm()))

    assert result.get("hard_error") is True
    assert result.get("error", "").startswith("学习路径生成失败，请重试生成学习路径。")

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000001", "year_3")
        )

    assert row is None


def test_run_learning_path_agent_returns_error_when_contract_validation_fails(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class InvalidPlanResult:
        def model_dump(self) -> dict:
            return _llm_learning_path_plan_payload(
                [
                    "AI Agent 最小可用闭环搭建",
                    "AI Agent 编排与状态管理",
                    "AI Agent 工程化调试与评测",
                    "AI Agent 上线链路压测",
                ]
            )

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return InvalidPlanResult()

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-two-course-fallback")
    )
    set_engine(engine)
    init_db(engine)

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_learning_path_agent(
                {
                    "user_id": "00000000-0000-0000-0000-000000000008",
                    "query": "进入学习路径草案智能体",
                    "profile": _complete_profile(),
                    "learning_path_intake": _confirmed_intake(
                        learning_topic="AI 应用开发",
                    ),
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is LearningPathPlanOutput
    assert result.get("hard_error") is True
    assert result.get("error", "").startswith("学习路径生成失败，请重试生成学习路径。")

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000008", "year_3")
        )

    assert row is None


def test_run_learning_path_agent_navigation_path_uses_user_topic_and_keeps_unknown_time_visible(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return LearningPathPlanOutput(
                **_llm_learning_path_plan_payload(
                    [
                        "vibecoding 目标拆解",
                        "vibecoding 工具链实践",
                        "vibecoding 项目闭环",
                        "vibecoding 求职作品整理",
                    ],
                    goal_type="就业准备",
                    grade_goal="围绕 vibecoding 形成求职作品",
                    desired_outcome="完成一个可展示的 vibecoding 项目",
                    current_focus="先把求职目标拆成可交付项目",
                    next_action="确认第一门课的练习任务",
                )
            )

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}

    engine = build_engine(postgresql_test_url(tmp_path, "learning-path-vibecoding"))
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "query": "下一步是什么？",
        "profile": {
            "type": "basic_profile",
            "stage": "generated",
            "question_mode": "question_box",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "软件工程",
                "learning_stage": "",
                "has_clear_goal": "",
                "learning_method_preference": "喜欢自己摸索",
                "learning_pace_preference": "",
                "content_preference": ["vibecoding"],
                "need_guidance": "",
                "knowledge_foundation": "",
                "strengths": "",
                "weaknesses": "",
                "experience": "",
                "short_term_goal": "找工作，学习vibecoding",
                "long_term_goal": "",
                "weekly_available_time": "",
                "constraints": "",
            },
            "defaulted_fields": [],
            "question_md": "画像已生成，是否进入学习路径草案智能体？",
            "question_box": {
                "question": "画像已生成，下一步要进入学习路径草案智能体吗？",
                "options": [],
            },
            "text": "【基础学习画像总结】大三软件工程，目标是找工作，想学习vibecoding。",
            "summary_text": "【基础学习画像总结】大三软件工程，目标是找工作，想学习vibecoding。",
        },
        "learning_path_intake": _confirmed_intake(
            learning_topic="vibecoding",
            course_titles=[
                "vibecoding 目标拆解",
                "vibecoding 工具链实践",
                "vibecoding 项目闭环",
                "vibecoding 求职作品整理",
            ],
        ),
        "messages": [],
    }

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_learning_path_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
    path = result["year_learning_path"]

    assert captured["schema"] is LearningPathPlanOutput
    assert "已确认课程草案" in str(captured["query"])
    assert path["learning_goal"]["target_course_or_skill"] == "vibecoding"
    assert "vibecoding" in path["current_learning_course"]["course_or_chapter_theme"]
    assert path["learner_baseline"]["weekly_available_time"] == ""
    assert path["learner_baseline"]["weaknesses"] == []
    assert set(path["grade_plans"]) == {"year_3"}
    assert len(path["grade_plans"]["year_3"]["course_nodes"]) == 4


def test_run_learning_path_agent_returns_error_when_structured_llm_times_out(
    tmp_path: Path,
) -> None:
    class SlowLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class SlowChain:
        async def ainvoke(self, _payload):
            await asyncio.sleep(0.05)
            raise AssertionError(
                "timeout fallback should fire before slow chain completes"
            )

    class SlowPrompt:
        def __or__(self, _other):
            return SlowChain()

    captured: dict[str, object] = {}
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-timeout-fallback")
    )
    set_engine(engine)
    init_db(engine)

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate
    original_timeout = module.LEARNING_PATH_STRUCTURED_TIMEOUT_SECONDS

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return SlowPrompt()

    module.ChatPromptTemplate = PromptFactory
    module.LEARNING_PATH_STRUCTURED_TIMEOUT_SECONDS = 0.01
    try:
        result = asyncio.run(
            run_learning_path_agent(
                {
                    "user_id": "00000000-0000-0000-0000-000000000006",
                    "query": "进入学习路径草案智能体",
                    "profile": _complete_profile(),
                    "learning_path_intake": _confirmed_intake(
                        learning_topic="AI 应用开发",
                        course_titles=AI_COURSE_TITLES,
                    ),
                    "messages": [],
                },
                SlowLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory
        module.LEARNING_PATH_STRUCTURED_TIMEOUT_SECONDS = original_timeout

    assert captured["schema"] is LearningPathPlanOutput
    assert result.get("hard_error") is True
    assert result.get("error", "").startswith("学习路径生成失败，请重试生成学习路径。")

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000006", "year_3")
        )

    assert row is None


def test_run_learning_path_agent_requires_confirmed_intake_for_navigation_query(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        called = False

        def with_structured_output(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError(
                "learning path should require confirmed intake before LLM"
            )

    engine = build_engine(postgresql_test_url(tmp_path, "learning-path-navigation"))
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000003",
        "query": "下一步是什么？",
        "profile": {
            "type": "basic_profile",
            "stage": "generated",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "软件工程",
                "learning_stage": "",
                "has_clear_goal": "",
                "learning_method_preference": "喜欢自己摸索",
                "learning_pace_preference": "",
                "content_preference": ["vibecoding"],
                "need_guidance": "",
                "knowledge_foundation": "",
                "strengths": "",
                "weaknesses": "",
                "experience": "",
                "short_term_goal": "找工作，学习vibecoding",
                "long_term_goal": "",
                "weekly_available_time": "",
                "constraints": "",
            },
            "summary_text": "【基础学习画像总结】大三软件工程，目标是找工作，想学习vibecoding。",
        },
        "messages": [],
    }

    llm = RecordingLlm()
    result = asyncio.run(run_learning_path_agent(state, llm))

    assert llm.called is False
    assert result == {
        "error": "请先确认课程草案，再生成正式学习路径。",
        "hard_error": True,
    }


def test_run_learning_path_agent_refresh_query_uses_existing_progress_for_llm_and_progress_roll_forward(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return LearningPathPlanOutput(
                **_llm_learning_path_plan_payload(
                    [
                        "AI Agent 最小可用闭环搭建",
                        "AI Agent 编排与状态管理",
                        "AI Agent 工程化调试与评测",
                        "AI Agent 部署上线与监控",
                    ]
                )
            )

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-refresh-progress")
    )
    set_engine(engine)
    init_db(engine)

    existing_path = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        [
            "AI 应用开发基础能力搭建",
            "AI 工程化服务编排",
            "AI 应用部署与监控实战",
        ],
    )
    existing_path["current_learning_course"] = {
        "grade_id": "year_3",
        "course_node_id": "year_3_course_2",
        "course_or_chapter_theme": "AI 工程化服务编排",
        "course_goal": "完成 AI 工程化服务编排 对应的核心训练",
        "time_arrangement": existing_path["grade_plans"]["year_3"]["course_nodes"][1][
            "time_arrangement"
        ],
        "current_focus": "第二门课程已完成，准备进入部署与监控实战",
        "progress_state": "completed",
        "next_action": "进入下一门课程",
    }

    with Session(engine) as session:
        session.add(
            User(
                uid="00000000-0000-0000-0000-000000000004",
                username="课程用户",
                identifier="learning-path-4@example.com",
            )
        )
        upsert_year_learning_path(
            session,
            "00000000-0000-0000-0000-000000000004",
            "year_3",
            "AI 应用开发",
            existing_path,
        )

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_learning_path_agent(
                {
                    "user_id": "00000000-0000-0000-0000-000000000004",
                    "query": "更新学习路径，我想加强部署与监控",
                    "profile": _complete_profile(),
                    "learning_path_intake": _confirmed_intake(
                        learning_topic="AI 应用开发",
                        course_titles=AI_COURSE_TITLES,
                    ),
                    "messages": [],
                    "year_learning_paths": {"year_3": existing_path},
                    "latest_grade_year": "year_3",
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is LearningPathPlanOutput
    assert "已有学习路径完成度摘要" in str(captured["query"])
    assert "year_3：共 3 门课程，已完成 2 门" in str(captured["query"])
    assert (
        result["year_learning_path"]["current_learning_course"]["course_node_id"]
        == "year_3_course_3"
    )
    assert (
        result["year_learning_path"]["current_learning_course"]["progress_state"]
        == "in_progress"
    )

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000004", "year_3")
        )

    assert row is not None
    assert set(row.path_data["grade_plans"]) == {"year_3"}
    assert (
        row.path_data["current_learning_course"]["course_node_id"] == "year_3_course_3"
    )


def test_run_learning_path_agent_new_grade_generation_includes_previous_year_progress_summary(
    tmp_path: Path,
) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return LearningPathPlanOutput(
                **_llm_learning_path_plan_payload(
                    [
                        "就业级作品集与迭代优化",
                        "AI Agent 综合项目孵化",
                        "AI Agent 毕业项目工程化打磨",
                        "AI Agent 求职展示与面试复盘",
                    ],
                    goal_type="就业准备",
                    grade_goal="沉淀就业级项目作品集",
                    desired_outcome="完成毕业阶段的可展示项目沉淀",
                    current_focus="先收束作品集主线与毕业项目表达",
                    next_action="先整理已有项目证据并确认毕业阶段主项目",
                )
            )

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-cross-grade-progress")
    )
    set_engine(engine)
    init_db(engine)

    existing_path = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        [
            "AI 应用开发基础能力搭建",
            "AI 工程化服务编排",
            "AI 应用部署与监控实战",
        ],
    )
    existing_path["current_learning_course"] = {
        "grade_id": "year_3",
        "course_node_id": "year_3_course_3",
        "course_or_chapter_theme": "AI 应用部署与监控实战",
        "course_goal": "完成 AI 应用部署与监控实战 对应的核心训练",
        "time_arrangement": existing_path["grade_plans"]["year_3"]["course_nodes"][2][
            "time_arrangement"
        ],
        "current_focus": "当前阶段课程已全部完成",
        "progress_state": "completed",
        "next_action": "当前年级课程已完成",
    }

    with Session(engine) as session:
        session.add(
            User(
                uid="00000000-0000-0000-0000-000000000007",
                username="课程用户",
                identifier="learning-path-7@example.com",
            )
        )
        upsert_year_learning_path(
            session,
            "00000000-0000-0000-0000-000000000007",
            "year_3",
            "AI 应用开发",
            existing_path,
        )

    profile = _complete_profile()
    profile["confirmed_info"]["current_grade"] = "大4"
    profile["summary_text"] = (
        "【基础学习画像总结】大4软件工程，准备进入毕业阶段并围绕 AI 应用开发沉淀作品。"
    )
    profile["text"] = profile["summary_text"]

    module = __import__(
        "app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"]
    )
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_learning_path_agent(
                {
                    "user_id": "00000000-0000-0000-0000-000000000007",
                    "query": "更新学习路径，我想开始毕业阶段的项目沉淀",
                    "profile": profile,
                    "learning_path_intake": _confirmed_intake(
                        grade_year="year_4",
                        grade_name="大四",
                        learning_topic="AI 应用开发",
                        course_titles=[
                            "就业级作品集与迭代优化",
                            "AI Agent 综合项目孵化",
                            "AI Agent 毕业项目工程化打磨",
                            "AI Agent 求职展示与面试复盘",
                        ],
                    ),
                    "messages": [],
                    "year_learning_paths": {"year_3": existing_path},
                    "latest_grade_year": "year_3",
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is LearningPathPlanOutput
    assert "已有学习路径完成度摘要" in str(captured["query"])
    assert "year_3：共 3 门课程，已完成 3 门" in str(captured["query"])
    assert result["grade_year"] == "year_4"
    assert set(result["year_learning_path"]["grade_plans"]) == {"year_4"}
    assert (
        result["year_learning_path"]["current_learning_course"]["course_node_id"]
        == "year_4_course_1"
    )

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000007", "year_4")
        )

    assert row is not None
    assert set(row.path_data["grade_plans"]) == {"year_4"}
    assert (
        row.path_data["current_learning_course"]["course_node_id"] == "year_4_course_1"
    )


def test_run_learning_path_agent_refresh_query_returns_error_when_structured_llm_setup_fails(
    tmp_path: Path,
) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("fallback should not call structured llm successfully")

    engine = build_engine(
        postgresql_test_url(tmp_path, "learning-path-fallback-refresh")
    )
    set_engine(engine)
    init_db(engine)

    existing_path = _single_year_learning_path_payload(
        "year_3",
        "大三",
        "完成 AI 项目闭环",
        [
            "AI 应用开发基础能力搭建",
            "AI 工程化服务编排",
            "AI 应用部署与监控实战",
        ],
    )
    existing_path["current_learning_course"] = {
        "grade_id": "year_3",
        "course_node_id": "year_3_course_2",
        "course_or_chapter_theme": "AI 工程化服务编排",
        "course_goal": "完成 AI 工程化服务编排 对应的核心训练",
        "time_arrangement": existing_path["grade_plans"]["year_3"]["course_nodes"][1][
            "time_arrangement"
        ],
        "current_focus": "第二门课程已完成，准备进入部署与监控实战",
        "progress_state": "completed",
        "next_action": "进入下一门课程",
    }

    with Session(engine) as session:
        session.add(
            User(
                uid="00000000-0000-0000-0000-000000000005",
                username="课程用户",
                identifier="learning-path-5@example.com",
            )
        )
        upsert_year_learning_path(
            session,
            "00000000-0000-0000-0000-000000000005",
            "year_3",
            "AI 应用开发",
            existing_path,
        )

    result = asyncio.run(
        run_learning_path_agent(
            {
                "user_id": "00000000-0000-0000-0000-000000000005",
                "query": "更新学习路径，我想继续强化部署与监控",
                "profile": _complete_profile(),
                "learning_path_intake": _confirmed_intake(
                    learning_topic="AI 应用开发",
                    course_titles=AI_COURSE_TITLES,
                ),
                "messages": [],
                "year_learning_paths": {"year_3": existing_path},
                "latest_grade_year": "year_3",
            },
            ExplodingLlm(),
        )
    )

    assert result.get("hard_error") is True
    assert result.get("error", "").startswith("学习路径生成失败，请重试生成学习路径。")

    with Session(engine) as session:
        row = session.get(
            UserYearLearningPath, ("00000000-0000-0000-0000-000000000005", "year_3")
        )

    assert row is not None
    assert (
        row.path_data["current_learning_course"]["course_node_id"] == "year_3_course_2"
    )
    assert row.path_data["current_learning_course"]["progress_state"] == "completed"


def test_learning_path_agent_node_updates_year_learning_paths_state(
    tmp_path: Path,
) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("fallback should not call structured llm successfully")

    engine = build_engine(postgresql_test_url(tmp_path, "learning-path-node"))
    set_engine(engine)
    init_db(engine)

    node = create_learning_path_agent_node(ExplodingLlm())
    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "query": "直接帮我生成，不确定的你随便帮我填",
        "profile": {
            "type": "basic_profile",
            "stage": "generated",
            "confirmed_info": {
                "current_grade": "大3",
                "major": "软件工程",
                "learning_stage": "有基础",
                "has_clear_goal": "大致有方向",
                "learning_method_preference": "项目驱动学习",
                "learning_pace_preference": "按项目里程碑推进",
                "content_preference": ["代码实践", "项目案例", "AI 对话调试"],
                "need_guidance": "需要轻量提醒",
                "knowledge_foundation": "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全",
                "strengths": "工程实现与课程学习能力",
                "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
                "experience": "平时学习",
                "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
                "long_term_goal": "形成AI 应用开发方向的应用开发能力",
                "weekly_available_time": "每周 6-10 小时",
                "constraints": "平时学习节奏，避免过高强度",
            },
            "summary_text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线。",
        },
        "messages": [],
        "year_learning_paths": {},
    }

    result = asyncio.run(node(state))

    assert result["response"] == "请先确认课程草案，再生成正式学习路径。"
    assert "grade_year" not in result
    assert "year_learning_paths" not in result
