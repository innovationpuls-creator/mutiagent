from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_knowledge import (
    ALL_CURRENT_GRADE_COURSES_ID,
    COURSE_KNOWLEDGE_RETRY_ERROR,
    _build_analysis_input,
    _normalize_generated_sections,
    _select_course_for_outline,
    run_course_knowledge_agent,
)
from app.orchestration.agents.models import (
    CourseKnowledgeOutput,
    SectionItem,
)
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT


def _complete_profile(summary_text: str = "【基础学习画像总结】大三软件工程，当前以AI 应用开发为主线。") -> dict:
    return {
        "type": "basic_profile",
        "summary_text": summary_text,
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "有 Python 和前端基础",
            "strengths": "能完成小型功能",
            "weaknesses": "异步工程经验不足",
            "experience": "做过课程项目",
            "short_term_goal": "完成 AI 功能模块",
            "long_term_goal": "成为全栈 AI 开发者",
            "weekly_available_time": "每周 8 小时",
            "constraints": "时间有限",
        },
    }


def _course_outline_target(*, learning_sequence: list[str] | None = None) -> dict:
    return {
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
        "learning_sequence": ["需求拆解", "接口接入", "最小闭环演示"] if learning_sequence is None else learning_sequence,
        "prerequisite_node_ids": [],
        "chapter_nodes": [],
        "core_knowledge_points": [],
        "knowledge_relations": [],
        "downstream_resource_direction_ids": [],
        "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
    }


def _course_tool_messages(course_id: str) -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "course_knowledge_agent",
                    "args": {"course_id": course_id},
                    "id": "force_course_knowledge_agent",
                }
            ],
        )
    ]


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


def test_select_course_for_outline_accepts_exact_course_name_as_explicit_input() -> None:
    path = {
        "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
        "grade_plans": {
            "year_3": {
                "course_nodes": [
                    {
                        "course_node_id": "year_3_course_1",
                        "course_or_chapter_theme": "构建本地知识库问答系统 (RAG基础)",
                    },
                    {
                        "course_node_id": "year_3_course_2",
                        "course_or_chapter_theme": "智能代理与工作流编排 (Agent & Workflow)",
                    },
                ],
            },
        },
    }

    course = _select_course_for_outline(
        {"year_3": path},
        "构建本地知识库问答系统 (RAG基础)",
    )

    assert course["course_node_id"] == "year_3_course_1"
    assert course["course_or_chapter_theme"] == "构建本地知识库问答系统 (RAG基础)"


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
    assert "只生成课程结构" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "自行设计" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "第一章、第二章" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "1.1" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "1.2" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "key_knowledge_points" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "不要生成 Markdown" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "视频" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "HTML 动画" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT


def test_course_knowledge_schema_requires_section_key_knowledge_points() -> None:
    with pytest.raises(ValueError):
        SectionItem(
            section_id="1",
            parent_section_id=None,
            depth=1,
            title="工程化导入",
            order_index=1,
            description="确认课程目标。",
            key_knowledge_points=[],
        )

def test_normalize_generated_sections_requires_chapter_and_subsection_ids() -> None:
    with pytest.raises(ValueError, match="一级章节 section_id"):
        _normalize_generated_sections(
            [
                {
                    "section_id": "chapter_1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "工程化导入",
                    "order_index": 1,
                    "description": "确认课程目标。",
                    "key_knowledge_points": ["课程目标"],
                },
                {
                    "section_id": "chapter_1.1",
                    "parent_section_id": "chapter_1",
                    "depth": 2,
                    "title": "能力边界",
                    "order_index": 2,
                    "description": "确认能力边界。",
                    "key_knowledge_points": ["能力拆解"],
                },
                {
                    "section_id": "chapter_1.2",
                    "parent_section_id": "chapter_1",
                    "depth": 2,
                    "title": "验收方式",
                    "order_index": 3,
                    "description": "确认验收方式。",
                    "key_knowledge_points": ["验收证据"],
                },
            ]
        )

    with pytest.raises(ValueError, match="1.1、1.2"):
        _normalize_generated_sections(
            [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": "工程化导入",
                    "order_index": 1,
                    "description": "确认课程目标。",
                    "key_knowledge_points": ["课程目标"],
                },
                {
                    "section_id": "1.a",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "能力边界",
                    "order_index": 2,
                    "description": "确认能力边界。",
                    "key_knowledge_points": ["能力拆解"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "验收方式",
                    "order_index": 3,
                    "description": "确认验收方式。",
                    "key_knowledge_points": ["验收证据"],
                },
            ]
        )


def test_build_analysis_input_uses_compact_course_and_profile_fields() -> None:
    query = _build_analysis_input(
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
            "chapter_nodes": [{"chapter_node_id": "unused"}],
            "core_knowledge_points": [{"knowledge_point_id": "unused"}],
            "knowledge_relations": [{"from": "a", "to": "b"}],
            "downstream_resource_direction_ids": ["resource_1"],
            "acceptance_criteria": ["完成一个可运行的 AI 功能模块并接入 Web 应用"],
        },
        _complete_profile(),
        {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(),
                            {
                                **_course_outline_target(),
                                "course_node_id": "year_3_course_2",
                                "course_or_chapter_theme": "AI Agent 开发项目实战",
                            },
                        ],
                    },
                },
            },
        },
    )

    assert "输出前先完成以下分析" in query
    assert "当前课程输入" in query
    assert "同年级课程顺序" in query
    assert "学习者输入" in query
    assert "chapter_nodes" not in query
    assert "knowledge_relations" not in query
    assert "profile_summary" in query


def test_run_course_knowledge_agent_uses_structured_outline_and_persists(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class RecordingLlm:
        pass

    def designed_outline_payload() -> dict:
        return {
                "personalization_summary": "按项目驱动画像先建立需求边界，再完成接口联调与演示闭环。",
                "sections": [
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "需求边界与功能验收",
                        "order_index": 1,
                        "description": "把 AI 功能目标收敛成可交付的最小闭环。",
                        "key_knowledge_points": ["用户场景拆解", "验收标准定义"],
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "功能边界拆解",
                        "order_index": 2,
                        "description": "结合用户目标确认第一版必须实现的功能范围。",
                        "key_knowledge_points": ["输入输出契约"],
                    },
                    {
                        "section_id": "1.2",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "验收证据设计",
                        "order_index": 3,
                        "description": "设计能够证明功能可运行的验收材料。",
                        "key_knowledge_points": ["运行截图", "接口响应样例"],
                    },
                    {
                        "section_id": "2",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "AI 接口接入与联调",
                        "order_index": 4,
                        "description": "把模型调用接入 Web 功能并处理关键异常。",
                        "key_knowledge_points": ["OpenAI-compatible API 调用", "错误处理"],
                    },
                    {
                        "section_id": "2.1",
                        "parent_section_id": "2",
                        "depth": 2,
                        "title": "请求结构设计",
                        "order_index": 5,
                        "description": "设计前后端之间稳定传递的请求结构。",
                        "key_knowledge_points": ["请求 payload", "响应解析"],
                    },
                    {
                        "section_id": "2.2",
                        "parent_section_id": "2",
                        "depth": 2,
                        "title": "异常与重试策略",
                        "order_index": 6,
                        "description": "处理调用失败、超时和用户可恢复提示。",
                        "key_knowledge_points": ["超时处理", "可恢复错误"],
                    },
                ],
                "learning_sequence": ["1", "2"],
                "total_estimated_hours": "18 小时",
            }

    class DesignedOutlineChain:
        async def ainvoke(self, payload):
            captured["query"] = payload["query"]
            return AIMessage(content=json.dumps(designed_outline_payload(), ensure_ascii=False))

    class DesignedOutlinePrompt:
        def __or__(self, _other):
            return DesignedOutlineChain()

    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-local-outline.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
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
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return DesignedOutlinePrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert not hasattr(RecordingLlm(), "with_structured_output")
    assert "AI 应用开发" in str(captured["query"])
    assert "同年级课程顺序" in str(captured["query"])
    assert "JSON Schema" not in str(captured["query"])
    assert "learning_sequence" in str(captured["query"])
    assert "需求拆解" not in str(captured["query"])
    assert "接口接入" not in str(captured["query"])
    assert "最小闭环演示" not in str(captured["query"])
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert result["course_knowledge"]["course_name"] == "AI 应用开发"
    assert result["course_knowledge"]["learning_sequence"] == ["第一章：需求边界与功能验收", "第二章：AI 接口接入与联调"]
    assert result["course_knowledge"]["sections"][0]["key_knowledge_points"] == ["用户场景拆解", "验收标准定义"]

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None
    assert row.outline_data["course_name"] == "AI 应用开发"
    assert row.outline_data["sections"][0]["section_id"] == "1"


def test_run_course_knowledge_agent_generates_all_grade_course_outlines_in_one_call(tmp_path: Path) -> None:
    captured: dict[str, object] = {"queries": [], "timeouts": []}

    class RecordingLlm:
        pass

    def outline_payload(course_id: str, title_prefix: str) -> dict:
        return {
            "course_id": course_id,
            "personalization_summary": f"{title_prefix} 按全年项目主线承接前后课程。",
            "sections": [
                {
                    "section_id": "1",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": f"{title_prefix} 架构导入",
                    "order_index": 1,
                    "description": f"建立 {title_prefix} 的核心边界。",
                    "key_knowledge_points": ["能力边界", "验收目标"],
                },
                {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "目标与输入输出",
                    "order_index": 2,
                    "description": "确认本课程输入、处理和交付物。",
                    "key_knowledge_points": ["输入契约", "交付物"],
                },
                {
                    "section_id": "1.2",
                    "parent_section_id": "1",
                    "depth": 2,
                    "title": "卡点与验收",
                    "order_index": 3,
                    "description": "提前识别卡点并设计验收方式。",
                    "key_knowledge_points": ["卡点定位", "验收证据"],
                },
                {
                    "section_id": "2",
                    "parent_section_id": None,
                    "depth": 1,
                    "title": f"{title_prefix} 实战闭环",
                    "order_index": 4,
                    "description": f"完成 {title_prefix} 的项目闭环。",
                    "key_knowledge_points": ["工程实现", "闭环验证"],
                },
                {
                    "section_id": "2.1",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "核心实现",
                    "order_index": 5,
                    "description": "完成最小可运行实现。",
                    "key_knowledge_points": ["最小实现", "接口联调"],
                },
                {
                    "section_id": "2.2",
                    "parent_section_id": "2",
                    "depth": 2,
                    "title": "结果复盘",
                    "order_index": 6,
                    "description": "复盘运行证据并连接下一门课。",
                    "key_knowledge_points": ["运行证据", "课程衔接"],
                },
            ],
            "learning_sequence": ["1", "2"],
            "total_estimated_hours": "16 小时",
        }

    def year_outline_payload() -> dict:
        return {
                "grade_year": "year_3",
                "year_summary": "全年按 AI 应用到 RAG 实战的顺序生成大纲。",
                "course_outlines": [
                    outline_payload("year_3_course_1", "AI 应用核心架构"),
                    outline_payload("year_3_course_2", "RAG 实战"),
                ],
            }

    class YearOutlineChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            return AIMessage(content=f"```json\n{json.dumps(year_outline_payload(), ensure_ascii=False)}\n```")

    year_chain = YearOutlineChain()

    class YearOutlinePrompt:
        def __or__(self, _other):
            return year_chain

    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-year-batch.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_or_chapter_theme": "AI 应用核心架构",
                            },
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_node_id": "year_3_course_2",
                                "course_or_chapter_theme": "RAG 实战",
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages(ALL_CURRENT_GRADE_COURSES_ID),
    }

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate
    original_wait_for = module.asyncio.wait_for

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return YearOutlinePrompt()

    async def recording_wait_for(awaitable, *, timeout):
        captured["timeouts"].append(timeout)
        return await awaitable

    module.ChatPromptTemplate = PromptFactory
    module.asyncio.wait_for = recording_wait_for
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.asyncio.wait_for = original_wait_for

    assert not hasattr(RecordingLlm(), "with_structured_output")
    assert year_chain.calls == 1
    assert captured["timeouts"] == [module.YEAR_COURSE_OUTLINE_TIMEOUT_SECONDS]
    assert "请一次性为当前年级的全部课程生成详细章节大纲" in captured["queries"][0]
    assert "JSON Schema" not in captured["queries"][0]
    assert "course_outlines" in captured["queries"][0]
    assert "AI 应用核心架构" in captured["queries"][0]
    assert "RAG 实战" in captured["queries"][0]
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert result["course_knowledge"]["course_name"] == "AI 应用核心架构"
    assert [outline["course_id"] for outline in result["course_knowledges"]] == ["year_3_course_1", "year_3_course_2"]

    with Session(engine) as session:
        first_row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
        second_row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_2"))

    assert first_row is not None
    assert second_row is not None
    assert first_row.outline_data["course_name"] == "AI 应用核心架构"
    assert second_row.outline_data["course_name"] == "RAG 实战"
    assert second_row.outline_data["sections"][1]["section_id"] == "1.1"


def test_run_course_knowledge_agent_empty_course_id_generates_current_course_only(tmp_path: Path) -> None:
    captured: dict[str, object] = {"queries": [], "timeouts": []}

    class RecordingLlm:
        pass

    class CurrentCourseChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return AIMessage(
                content=json.dumps(
                    {
                        "personalization_summary": "按当前课程生成单门章节大纲。",
                        "sections": [
                            {
                                "section_id": "1",
                                "parent_section_id": None,
                                "depth": 1,
                                "title": "架构入口",
                                "order_index": 1,
                                "description": "建立课程主线。",
                                "key_knowledge_points": ["架构边界", "目标验收"],
                            },
                            {
                                "section_id": "1.1",
                                "parent_section_id": "1",
                                "depth": 2,
                                "title": "目标边界",
                                "order_index": 2,
                                "description": "确认输入输出。",
                                "key_knowledge_points": ["输入输出"],
                            },
                            {
                                "section_id": "1.2",
                                "parent_section_id": "1",
                                "depth": 2,
                                "title": "验收方式",
                                "order_index": 3,
                                "description": "定义可验证结果。",
                                "key_knowledge_points": ["验收标准"],
                            },
                        ],
                        "learning_sequence": ["1"],
                        "total_estimated_hours": "8 小时",
                    },
                    ensure_ascii=False,
                )
            )

    class CurrentCoursePrompt:
        def __or__(self, _other):
            return CurrentCourseChain()

    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-empty-course-id.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "latest_grade_year": "year_3",
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            _course_outline_target(learning_sequence=[]),
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_node_id": "year_3_course_2",
                                "course_or_chapter_theme": "RAG 实战",
                            },
                        ],
                    },
                },
            },
        },
        "messages": [],
    }

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate
    original_wait_for = module.asyncio.wait_for

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return CurrentCoursePrompt()

    async def recording_wait_for(awaitable, *, timeout):
        captured["timeouts"].append(timeout)
        return await awaitable

    module.ChatPromptTemplate = PromptFactory
    module.asyncio.wait_for = recording_wait_for
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.asyncio.wait_for = original_wait_for

    assert len(captured["queries"]) == 1
    assert captured["timeouts"] == [module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS]
    assert "请为以下课程生成详细的章节大纲" in captured["queries"][0]
    assert "请一次性为当前年级的全部课程生成详细章节大纲" not in captured["queries"][0]
    assert "course_outlines" not in captured["queries"][0]
    assert result["course_knowledge"]["course_id"] == "year_3_course_1"
    assert "course_knowledges" not in result

    with Session(engine) as session:
        first_row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
        second_row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_2"))

    assert first_row is not None
    assert second_row is None


def test_run_course_knowledge_agent_rejects_incomplete_basic_profile(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-incomplete-profile.db'}")
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    result = asyncio.run(
        run_course_knowledge_agent(
            {
                "user_id": "user-1",
                "profile": {"type": "basic_profile", "summary_text": "旧画像摘要"},
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
            object(),
        )
    )

    assert result == {"error": "请先完成基础画像。"}


def test_run_course_knowledge_agent_returns_hard_error_after_json_output_failure(tmp_path: Path) -> None:
    class ExplodingLlm:
        pass

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
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                                {
                                    **_course_outline_target(learning_sequence=[]),
                                },
                            ],
                        },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    original_prompt = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = original_prompt.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return ExplodingPrompt()

    original_prompt.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, ExplodingLlm()))
    finally:
        original_prompt.ChatPromptTemplate = original_factory

    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_repairs_invalid_json_outline_once(tmp_path: Path) -> None:
    captured: dict[str, object] = {"queries": []}

    class RecordingLlm:
        pass

    def invalid_outline_payload() -> dict:
        return {
                "personalization_summary": "先从 RAG 主链路入手。",
                "sections": [
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "RAG 主链路",
                        "order_index": 1,
                        "description": "只返回了一级章节，缺少二级小节。",
                        "key_knowledge_points": ["检索增强生成"],
                    },
                ],
                "learning_sequence": ["1"],
                "total_estimated_hours": "12 小时",
            }

    def repaired_outline_payload() -> dict:
        return {
                "personalization_summary": "按项目驱动画像先理解 RAG 架构，再完成检索链路验收。",
                "sections": [
                    {
                        "section_id": "1",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "AI 应用核心架构",
                        "order_index": 1,
                        "description": "建立 AI 应用从输入到输出的核心分层。",
                        "key_knowledge_points": ["应用分层", "模型调用边界"],
                    },
                    {
                        "section_id": "1.1",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "请求入口与状态边界",
                        "order_index": 2,
                        "description": "确认用户输入、会话状态和模型调用之间的边界。",
                        "key_knowledge_points": ["输入契约", "状态隔离"],
                    },
                    {
                        "section_id": "1.2",
                        "parent_section_id": "1",
                        "depth": 2,
                        "title": "模型调用与错误回传",
                        "order_index": 3,
                        "description": "设计可恢复的模型调用与错误提示。",
                        "key_knowledge_points": ["调用超时", "错误提示"],
                    },
                    {
                        "section_id": "2",
                        "parent_section_id": None,
                        "depth": 1,
                        "title": "RAG 检索增强实战",
                        "order_index": 4,
                        "description": "完成从文档切分到答案引用的 RAG 主链路。",
                        "key_knowledge_points": ["向量检索", "引用归因"],
                    },
                    {
                        "section_id": "2.1",
                        "parent_section_id": "2",
                        "depth": 2,
                        "title": "知识切分与向量化",
                        "order_index": 5,
                        "description": "把课程资料处理成可检索的知识片段。",
                        "key_knowledge_points": ["chunk 设计", "embedding 生成"],
                    },
                    {
                        "section_id": "2.2",
                        "parent_section_id": "2",
                        "depth": 2,
                        "title": "检索召回与答案验收",
                        "order_index": 6,
                        "description": "验证检索结果是否真正支撑最终回答。",
                        "key_knowledge_points": ["top_k 召回", "答案证据"],
                    },
                ],
                "learning_sequence": ["1", "2"],
                "total_estimated_hours": "20 小时",
            }

    class RepairingChain:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, payload):
            self.calls += 1
            captured["queries"].append(payload["query"])
            if self.calls == 1:
                return AIMessage(content=json.dumps(invalid_outline_payload(), ensure_ascii=False))
            return AIMessage(content=json.dumps(repaired_outline_payload(), ensure_ascii=False))

    repairing_chain = RepairingChain()

    class RepairingPrompt:
        def __or__(self, _other):
            return repairing_chain

    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-repair.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                            {
                                **_course_outline_target(learning_sequence=[]),
                                "course_or_chapter_theme": "AI应用核心架构与RAG实战",
                            },
                        ],
                    },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return RepairingPrompt()

    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(run_course_knowledge_agent(state, RecordingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory

    assert not hasattr(RecordingLlm(), "with_structured_output")
    assert repairing_chain.calls == 2
    assert "JSON Schema" not in captured["queries"][0]
    assert "sections" in captured["queries"][0]
    assert "上一次输出没有通过课程大纲结构校验" in captured["queries"][1]
    assert "课程大纲必须包含章内小节" in captured["queries"][1]
    assert result["course_knowledge"]["course_name"] == "AI应用核心架构与RAG实战"
    assert result["course_knowledge"]["learning_sequence"] == ["第一章：AI 应用核心架构", "第二章：RAG 检索增强实战"]

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is not None
    assert row.outline_data["sections"][1]["section_id"] == "1.1"


def test_run_course_knowledge_agent_returns_hard_error_after_timeout(tmp_path: Path) -> None:
    class HangingLlm:
        pass

    class HangingChain:
        async def ainvoke(self, _payload):
            await asyncio.sleep(0.1)
            raise AssertionError("timeout fallback should return before the chain finishes")

    class HangingPrompt:
        def __or__(self, _other):
            return HangingChain()

    engine = build_engine(f"sqlite:///{tmp_path / 'course-knowledge-timeout.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.commit()

    state = {
        "user_id": "user-1",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
                "grade_plans": {
                    "year_3": {
                        "course_nodes": [
                                {
                                    **_course_outline_target(learning_sequence=[]),
                                },
                            ],
                        },
                },
            },
        },
        "messages": _course_tool_messages("year_3_course_1"),
    }

    module = __import__("app.orchestration.agents.course_knowledge", fromlist=["ChatPromptTemplate"])
    original_factory = module.ChatPromptTemplate
    original_timeout = module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return HangingPrompt()

    module.ChatPromptTemplate = PromptFactory
    module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS = 0.01
    try:
        result = asyncio.run(run_course_knowledge_agent(state, HangingLlm()))
    finally:
        module.ChatPromptTemplate = original_factory
        module.SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS = original_timeout

    assert result == {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))

    assert row is None


def test_run_course_knowledge_agent_normalizes_partial_json_outline(tmp_path: Path) -> None:
    class RecordingLlm:
        pass

    def partial_outline_payload() -> dict:
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
            return AIMessage(content=json.dumps(partial_outline_payload(), ensure_ascii=False))

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
                    "profile": _complete_profile("【基础学习画像总结】大三软件工程，当前重点是补齐项目练习。"),
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
                                                "learning_sequence": [],
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
                    "messages": _course_tool_messages("year_3_course_2"),
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
