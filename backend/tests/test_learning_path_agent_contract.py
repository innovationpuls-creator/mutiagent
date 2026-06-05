from __future__ import annotations

import asyncio
from pathlib import Path

from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import UserYearLearningPath
from app.orchestration.agents.models import YearLearningPathOutput
from app.orchestration.agents.learning_path import (
    _grade_year_from_profile,
    _topic_from_profile,
    create_learning_path_agent_node,
    _validate_learning_path_contract,
    run_learning_path_agent,
)
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT


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
                        "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
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
        "resource_generation_contract": {"downstream_agents": ["learning_resource_agent"], "resource_directions": []},
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
            "progress_state": "not_started",
            "next_action": "先完成需求拆解并确认验收边界",
        },
    }


def test_grade_year_from_profile_maps_chinese_grade() -> None:
    assert _grade_year_from_profile({"confirmed_info": {"current_grade": "大3"}}) == "year_3"
    assert _grade_year_from_profile({"confirmed_info": {"current_grade": "大三"}}) == "year_3"


def test_topic_from_profile_prefers_profile_direction() -> None:
    profile = {
        "confirmed_info": {
            "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
            "long_term_goal": "形成AI 应用开发方向的应用开发能力",
        },
        "summary_text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线。",
    }

    assert _topic_from_profile(profile) == "AI 应用开发"


def test_topic_from_profile_uses_vibecoding_when_user_said_learning_vibecoding() -> None:
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


def test_learning_path_prompt_mentions_json_output() -> None:
    assert "json" in LEARNING_PATH_AGENT_SYSTEM_PROMPT.lower()
    assert "先分析" in LEARNING_PATH_AGENT_SYSTEM_PROMPT


def test_run_learning_path_agent_uses_structured_llm_for_default_query(tmp_path: Path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return YearLearningPathOutput(**_llm_learning_path_payload())

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(f"sqlite:///{tmp_path / 'learning-path-thinking.db'}")
    set_engine(engine)
    init_db(engine)

    module = __import__("app.orchestration.agents.learning_path", fromlist=["ChatPromptTemplate"])
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
                    "profile": {
                        "type": "basic_profile",
                        "confirmed_info": {
                            "current_grade": "大3",
                            "major": "软件工程",
                            "short_term_goal": "围绕AI 应用开发完成一个可运行的课程级项目",
                            "long_term_goal": "形成AI 应用开发方向的应用开发能力",
                            "weekly_available_time": "每周 6-10 小时",
                            "constraints": "平时学习节奏",
                            "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
                        },
                        "summary_text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线。",
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is YearLearningPathOutput
    assert "用户画像关键信息" in str(captured["query"])
    assert "输出前先完成以下分析" in str(captured["query"])
    assert result["year_learning_path"]["current_learning_course"]["course_node_id"] == "year_3_course_1"


def test_run_learning_path_agent_falls_back_to_local_path_and_persists(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("fallback should not call structured llm successfully")

    engine = build_engine(f"sqlite:///{tmp_path / 'learning-path-fallback.db'}")
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
            "question_md": "画像已生成，是否继续生成学习路径？",
            "question_box": {"question": "画像已生成，下一步要继续生成学习路径吗？", "options": []},
            "text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线，适合采用项目驱动学习。",
            "summary_text": "【基础学习画像总结】大3软件工程，当前以AI 应用开发为主线，适合采用项目驱动学习。",
        },
        "messages": [],
    }

    result = asyncio.run(run_learning_path_agent(state, ExplodingLlm()))

    assert result["grade_year"] == "year_3"
    assert result["year_learning_path"]["schema_version"] == "learning_path.v2.course_node"
    assert result["year_learning_path"]["current_learning_course"]["grade_id"] == "year_3"
    assert _validate_learning_path_contract(result["year_learning_path"]) == ""
    assert set(result["year_learning_path"]["grade_plans"]) == {"year_1", "year_2", "year_3", "year_4"}

    with Session(engine) as session:
        row = session.get(UserYearLearningPath, ("00000000-0000-0000-0000-000000000001", "year_3"))

    assert row is not None
    assert row.path_data["current_learning_course"]["grade_id"] == "year_3"
    assert row.path_data["current_learning_course"]["course_or_chapter_theme"] == "AI 应用开发基础能力搭建"
    assert row.path_data["grade_plans"]["year_3"]["course_nodes"][0]["chapter_nodes"]
    assert row.path_data["grade_plans"]["year_3"]["course_nodes"][0]["core_knowledge_points"]
    assert row.path_data["resource_generation_contract"]["resource_directions"]
    assert row.path_data["knowledge_graph"]["critical_paths"]


def test_run_learning_path_agent_fallback_uses_user_topic_and_keeps_unknown_time_visible(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("fallback should not call structured llm successfully")

    engine = build_engine(f"sqlite:///{tmp_path / 'learning-path-vibecoding.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "query": "继续生成学习路径",
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
            "question_md": "画像已生成，是否继续生成学习路径？",
            "question_box": {"question": "画像已生成，下一步要继续生成学习路径吗？", "options": []},
            "text": "【基础学习画像总结】大三软件工程，目标是找工作，想学习vibecoding。",
            "summary_text": "【基础学习画像总结】大三软件工程，目标是找工作，想学习vibecoding。",
        },
        "messages": [],
    }

    result = asyncio.run(run_learning_path_agent(state, ExplodingLlm()))
    path = result["year_learning_path"]

    assert path["learning_goal"]["target_course_or_skill"] == "vibecoding"
    assert "vibecoding" in path["current_learning_course"]["course_or_chapter_theme"]
    assert path["learner_baseline"]["weekly_available_time"] == ""
    assert path["learner_baseline"]["weaknesses"] == []
    assert set(path["grade_plans"]) == {"year_1", "year_2", "year_3", "year_4"}


def test_learning_path_agent_node_updates_year_learning_paths_state(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("fallback should not call structured llm successfully")

    engine = build_engine(f"sqlite:///{tmp_path / 'learning-path-node.db'}")
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

    assert result["grade_year"] == "year_3"
    assert "year_3" in result["year_learning_paths"]
    assert result["year_learning_paths"]["year_3"]["current_learning_course"]["course_or_chapter_theme"] == "AI 应用开发基础能力搭建"
