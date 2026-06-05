from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_knowledge import (
    _build_local_course_outline,
    _select_course_for_outline,
    run_course_knowledge_agent,
)
from app.orchestration.agents.models import CourseKnowledgeDraftOutput, CourseKnowledgeOutput
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT


def test_select_course_for_outline_uses_current_learning_course() -> None:
    path = {
        "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "AI 应用开发",
                    },
                ],
            },
        },
    }

    course = _select_course_for_outline({"year_3": path}, "")

    assert course["course_node_id"] == "year_3_course_1"
    assert course["course_or_chapter_theme"] == "AI 应用开发"


def test_select_course_for_outline_requires_path() -> None:
    with pytest.raises(ValueError, match="学习路径不存在"):
        _select_course_for_outline(None, "")


def test_select_course_for_outline_rejects_unknown_explicit_course_id() -> None:
    path = {
        "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "AI 应用开发",
                    },
                ],
            },
        },
    }

    with pytest.raises(ValueError, match="指定课程无法定位"):
        _select_course_for_outline({"year_3": path}, "year_3_course_missing")


def test_select_course_for_outline_prefers_latest_grade_year_when_no_explicit_course_id() -> None:
    year_3_path = {
        "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "旧课程",
                    },
                ],
            },
        },
    }
    year_4_path = {
        "current_learning_course": {"grade_id": "year_4", "course_node_id": "year_4_course_1"},
        "grade_plans": {
            "year_4": {
                "course_nodes": [
                    {
                        "course_node_id": "year_4_course_1",
                        "course_or_chapter_theme": "最新课程",
                    },
                ],
            },
        },
    }

    course = _select_course_for_outline(
        {"year_3": year_3_path, "year_4": year_4_path},
        "",
        "year_4",
    )

    assert course["course_node_id"] == "year_4_course_1"
    assert course["course_or_chapter_theme"] == "最新课程"


def test_course_knowledge_prompt_mentions_json_output() -> None:
    assert "json" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT.lower()
    assert "先分析" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT


def test_build_local_course_outline_creates_nested_sections() -> None:
    outline = _build_local_course_outline(
        {
            "course_node_id": "year_3_course_1",
            "course_or_chapter_theme": "AI 应用开发",
            "grade_id": "year_3",
            "course_goal": "完成 AI 应用开发基础能力搭建",
            "time_arrangement": {
                "semester_scope": "上学期",
                "duration": "6 周",
                "pace_reason": "围绕平时学习安排",
            },
            "key_points": ["Prompt 设计", "前后端联调"],
            "difficult_points": ["错误处理与重试"],
            "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
            "prerequisite_node_ids": [],
            "chapter_nodes": [],
            "core_knowledge_points": [],
            "knowledge_relations": [],
            "downstream_resource_direction_ids": [],
            "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
        },
        {
            "confirmed_info": {
                "current_grade": "大三",
                "weekly_available_time": "每周 6-10 小时",
                "constraints": "平时学习节奏",
            }
        },
    )

    depths = {section["depth"] for section in outline["sections"]}
    assert 2 in depths
    assert any(section["parent_section_id"] for section in outline["sections"])
    assert "重点突破" in outline["personalization_summary"]
    assert outline["learning_sequence"][0] == "第一章：需求拆解"
    assert any(section["section_id"] == "1.3" for section in outline["sections"])
    assert any(section["title"] == "学习目标" for section in outline["sections"])
    assert any(section["title"] == "任务拆解" for section in outline["sections"])
    assert any(section["title"] == "检查点" for section in outline["sections"])


def test_run_course_knowledge_agent_uses_structured_llm_input_analysis(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class RecordingChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return CourseKnowledgeOutput(
                course_id="year_3_course_1",
                course_name="AI 应用开发",
                grade_year="year_3",
                personalization_summary="基于当前基础先稳住最小闭环，再逐步提升到部署演示。",
                sections=[
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "需求拆解",
                        "order_index": 1,
                        "description": "先确认功能边界与验收标准。",
                        "key_knowledge_points": ["功能边界", "验收标准"],
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "学习目标",
                        "order_index": 2,
                        "description": "明确本章完成后的目标。",
                        "key_knowledge_points": ["任务拆分"],
                    },
                    {
                        "section_id": "1.2",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "任务拆解",
                        "order_index": 3,
                        "description": "拆分当前阶段任务。",
                        "key_knowledge_points": ["步骤安排"],
                    },
                    {
                        "section_id": "1.3",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "检查点",
                        "order_index": 4,
                        "description": "核对本章是否完成。",
                        "key_knowledge_points": ["完成确认"],
                    },
                ],
                learning_sequence=["第一章：需求拆解"],
                total_estimated_hours="8 小时",
            )

    class RecordingPrompt:
        def __or__(self, _other):
            return RecordingChain()

    captured: dict[str, object] = {}
    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-thinking.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RecordingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_course_knowledge_agent(
                {
                    "user_id": "user-1",
                    "profile": {
                        "type": "basic_profile",
                        "confirmed_info": {
                            "current_grade": "大三",
                            "weekly_available_time": "每周 6-10 小时",
                            "constraints": "平时学习节奏",
                        },
                    },
                    "year_learning_paths": {
                        "year_3": {
                            "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                            "grade_plans": {
                                "year_3": {
                                    "course_nodes": [
                                        {
                                            "course_node_id": "year_3_course_1",
                                            "course_or_chapter_theme": "AI 应用开发",
                                            "grade_id": "year_3",
                                            "course_goal": "完成 AI 应用开发基础能力搭建",
                                            "time_arrangement": {
                                                "semester_scope": "上学期",
                                                "duration": "6 周",
                                                "pace_reason": "围绕平时学习安排",
                                            },
                                            "key_points": ["Prompt 设计", "前后端联调"],
                                            "difficult_points": ["错误处理与重试"],
                                            "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
                                            "prerequisite_node_ids": [],
                                            "chapter_nodes": [],
                                            "core_knowledge_points": [],
                                            "knowledge_relations": [],
                                            "downstream_resource_direction_ids": [],
                                            "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
                                        },
                                    ],
                                },
                            },
                        },
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is CourseKnowledgeDraftOutput
    assert "输出前先完成以下分析" in str(captured["query"])
    assert "课程信息" in str(captured["query"])
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert result["course_knowledge"]["learning_sequence"] == ["第一章：需求拆解"]


def test_run_course_knowledge_agent_falls_back_to_local_outline_and_persists(tmp_path: Path) -> None:
    class ExplodingStructuredLlm:
        def with_structured_output(self, *_args, **_kwargs):
            return object()

    class ExplodingChain:
        async def ainvoke(self, _payload):
            raise RuntimeError("json mode failed")

    class ExplodingPrompt:
        def __or__(self, _other):
            return ExplodingChain()

    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-fallback.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": {"type": "basic_profile"},
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                "course_node_id": "year_3_course_1",
                                "course_or_chapter_theme": "AI 应用开发",
                                "grade_id": "year_3",
                                "course_goal": "完成 AI 应用开发基础能力搭建",
                                "time_arrangement": {
                                    "semester_scope": "上学期",
                                    "duration": "6 周",
                                    "pace_reason": "围绕平时学习安排",
                                },
                                "key_points": ["Prompt 设计", "前后端联调"],
                                "difficult_points": ["错误处理与重试"],
                                "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
                                "prerequisite_node_ids": [],
                                "chapter_nodes": [],
                                "core_knowledge_points": [],
                                "knowledge_relations": [],
                                "downstream_resource_direction_ids": [],
                                "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
                            },
                        ],
                    },
                },
            },
        },
        "messages": [],
    }

    original_prompt = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = original_prompt.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ExplodingPrompt()

    original_prompt.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, ExplodingStructuredLlm()))
    finally:
        original_prompt.ChatPromptTemplate = original_factory

    assert "course_knowledge" in result
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert result["course_knowledge"]["course_name"] == "AI 应用开发"
    assert result["course_knowledge"]["grade_year"] == "year_3"
    assert result["course_knowledge"]["sections"]
    assert result["course_knowledge"]["learning_sequence"]
    assert result["course_knowledge"]["learning_sequence"][0] == "第一章：需求拆解"

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None
    assert row.outline_data["course_name"] == "AI 应用开发"


def test_run_course_knowledge_agent_normalizes_partial_structured_outline(tmp_path: Path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class PartialOutlineResult:
        def model_dump(self):
            return {
                "personalization_summary": "先完成架构设计，再推进联调与部署。",
                "sections": [
                    {
                        "section_id": "1",
                        "title": "架构设计",
                        "description": "确认多智能体主流程与状态边界。",
                        "key_knowledge_points": ["LangGraph 编排"],
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "title": "学习目标",
                        "description": "明确架构设计的章节目标。",
                        "key_knowledge_points": ["状态边界"],
                    },
                    {
                        "section_id": "1.2",
                        "parent_section_id": "1",
                        "title": "任务拆解",
                        "description": "拆分架构设计的阶段任务。",
                        "key_knowledge_points": ["编排设计"],
                    },
                    {
                        "section_id": "1.3",
                        "parent_section_id": "1",
                        "title": "检查点",
                        "description": "验证架构设计是否可进入联调。",
                        "key_knowledge_points": ["边界确认"],
                    },
                    {
                        "section_id": "2",
                        "title": "多智能体联调",
                        "description": "打通事件流、状态流与错误回传。",
                        "key_knowledge_points": ["SSE 流式交互"],
                    },
                    {
                        "section_id": "2.1",
                        "parent_section_id": "2",
                        "title": "学习目标",
                        "description": "明确联调阶段要达到的能力目标。",
                        "key_knowledge_points": ["错误回传"],
                    },
                    {
                        "section_id": "2.2",
                        "parent_section_id": "2",
                        "title": "任务拆解",
                        "description": "验证事件流与错误回传。",
                        "key_knowledge_points": ["事件流验证"],
                    },
                    {
                        "section_id": "2.3",
                        "parent_section_id": "2",
                        "title": "检查点",
                        "description": "确认联调结果可以进入部署阶段。",
                        "key_knowledge_points": ["错误回传"],
                    },
                ],
                "learning_sequence": ["1", "2"],
                "total_estimated_hours": 72,
            }

    class PartialOutlineChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return PartialOutlineResult()

    class PartialOutlinePrompt:
        def __or__(self, _other):
            return PartialOutlineChain()

    captured: dict[str, object] = {}
    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-normalize.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return PartialOutlinePrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_course_knowledge_agent(
                {
                    "user_id": "user-1",
                    "profile": {
                        "type": "basic_profile",
                        "confirmed_info": {
                            "current_grade": "大三",
                            "weekly_available_time": "每周 6-10 小时",
                            "constraints": "缺少项目练习",
                        },
                    },
                    "year_learning_paths": {
                        "year_3": {
                            "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_2"},
                            "grade_plans": {
                                "year_3": {
                                    "course_nodes": [
                                        {
                                            "course_node_id": "year_3_course_1",
                                            "course_or_chapter_theme": "AI Agent 开发基础能力搭建",
                                            "grade_id": "year_3",
                                            "course_goal": "完成最小闭环",
                                            "time_arrangement": {
                                                "semester_scope": "上学期",
                                                "duration": "6 周",
                                                "pace_reason": "围绕平时学习安排",
                                            },
                                            "key_points": ["Prompt 设计", "前后端联调"],
                                            "difficult_points": ["错误处理与重试"],
                                            "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"],
                                            "prerequisite_node_ids": [],
                                            "chapter_nodes": [],
                                            "core_knowledge_points": [],
                                            "knowledge_relations": [],
                                            "downstream_resource_direction_ids": [],
                                            "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
                                        },
                                        {
                                            "course_node_id": "year_3_course_2",
                                            "course_or_chapter_theme": "AI Agent 开发项目实战",
                                            "grade_id": "year_3",
                                            "course_goal": "完成真实交互与部署演示",
                                            "time_arrangement": {
                                                "semester_scope": "下学期",
                                                "duration": "8 周",
                                                "pace_reason": "项目实战需要完整联调与部署周期",
                                            },
                                            "key_points": ["LangGraph 编排", "SSE 流式交互", "部署与监控"],
                                            "difficult_points": ["多智能体状态管理", "线上稳定性"],
                                            "learning_sequence": ["架构设计", "多智能体联调", "部署验收"],
                                            "prerequisite_node_ids": ["year_3_course_1"],
                                            "chapter_nodes": [],
                                            "core_knowledge_points": [],
                                            "knowledge_relations": [],
                                            "downstream_resource_direction_ids": [],
                                            "acceptance_criteria": ["项目支持真实用户流程与部署演示"],
                                        },
                                    ],
                                },
                            },
                        },
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    outline = result["course_knowledge"]
    assert captured["query"]
    assert outline["course_id"] == "year_3_course_2"
    assert outline["course_name"] == "AI Agent 开发项目实战"
    assert outline["grade_year"] == "year_3"
    assert outline["total_estimated_hours"] == "72 小时"
    assert outline["sections"][0]["parent_section_id"] is None
    assert outline["sections"][0]["depth"] == 1
    assert outline["sections"][0]["order_index"] == 1
    assert outline["sections"][1]["order_index"] == 2
    assert outline["learning_sequence"] == ["第一章：架构设计", "第二章：多智能体联调"]
