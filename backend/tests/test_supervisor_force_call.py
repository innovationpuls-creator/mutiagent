from __future__ import annotations

import asyncio
from langchain_core.messages import AIMessage

from app.orchestration.agents.supervisor import (
    ALL_CURRENT_GRADE_COURSES_ID,
    _learning_path_force_args,
    _force_call_response,
    build_system_prompt,
    create_supervisor_node,
)
from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_PROFILE,
    AGENT_SECTION_MARKDOWN,
)


def _complete_profile(summary_text: str = "Test") -> dict:
    return {
        "type": "basic_profile",
        "summary_text": summary_text,
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "项目实践",
            "has_clear_goal": "是",
            "learning_method_preference": "项目驱动",
            "learning_pace_preference": "周末集中",
            "content_preference": ["实践"],
            "need_guidance": "需要",
            "knowledge_foundation": "有 Python 基础",
            "strengths": "执行力强",
            "weaknesses": "部署经验不足",
            "experience": "做过课程项目",
            "short_term_goal": "完成 AI 功能模块",
            "long_term_goal": "完成 AI 应用开发项目",
            "weekly_available_time": "每周 8 小时",
            "constraints": "周末集中",
        },
    }


def test_force_call_response_uses_next_course_for_course_change_query() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "我不想要《AI Agent 开发基础能力搭建》了，现在帮我生成一门新课",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                {"course_node_id": "year_3_course_1"},
                                {"course_node_id": "year_3_course_2"},
                            ],
                        },
                    },
                },
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_COURSE_KNOWLEDGE
    assert tool_call["args"]["course_id"] == "year_3_course_2"


def test_force_call_response_returns_completion_reply_when_no_next_course_exists() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "我不想要《AI 应用开发项目实战》了，现在帮我生成一门新课",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_2",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                {"course_node_id": "year_3_course_1"},
                                {"course_node_id": "year_3_course_2"},
                            ],
                        },
                    },
                },
            },
        },
    )

    assert response["response"].startswith("当前所有任务已经完成。")
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_maps_named_outline_regeneration_to_course_id() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "帮我重新生成AI Agent 开发基础能力搭建的章节大纲",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "course_or_chapter_theme": "AI Agent 开发基础能力搭建",
                                },
                            ],
                        },
                    },
                },
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_COURSE_KNOWLEDGE
    assert tool_call["args"] == {"course_id": "year_3_course_1"}


def test_force_call_response_maps_chinese_course_name_to_course_id_for_outline() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "帮我生成AI应用核心架构与RAG实战的章节大纲",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "course_or_chapter_theme": "AI Agent 开发基础能力搭建",
                                },
                                {
                                    "course_node_id": "year_3_course_2",
                                    "course_or_chapter_theme": "AI应用核心架构与RAG实战",
                                },
                            ],
                        },
                    },
                },
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_COURSE_KNOWLEDGE
    assert tool_call["args"] == {"course_id": "year_3_course_2"}


def test_force_call_response_uses_current_course_for_generic_start_query() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "ok，开始",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                {
                                    "course_node_id": "year_3_course_1",
                                    "course_or_chapter_theme": "LangGraph 核心架构与单智能体状态机构建",
                                },
                                {
                                    "course_node_id": "year_3_course_2",
                                    "course_or_chapter_theme": "多轮对话记忆管理与 RAG 增强",
                                },
                            ],
                        },
                    },
                },
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_COURSE_KNOWLEDGE
    assert tool_call["args"] == {"course_id": "year_3_course_1"}


def test_force_call_response_uses_sentinel_for_explicit_all_course_outline_request() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "帮我一次性生成当前年级全部课程大纲",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                },
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_COURSE_KNOWLEDGE
    assert tool_call["args"] == {"course_id": ALL_CURRENT_GRADE_COURSES_ID}


def test_learning_path_force_args_uses_profile_topic_for_generic_refresh_query() -> None:
    args = _learning_path_force_args({"query": "继续生成学习路径"})

    assert args == {
        "grade_year": "",
        "learning_topic": "",
        "specific_requirements": "",
    }


def test_learning_path_force_args_treats_punctuated_generic_refresh_query_as_generic() -> None:
    args = _learning_path_force_args({"query": "继续生成学习路径。"})

    assert args == {
        "grade_year": "",
        "learning_topic": "",
        "specific_requirements": "",
    }


def test_force_call_response_uses_specific_requirements_for_detailed_path_refresh_query() -> None:
    response = _force_call_response(
        AGENT_LEARNING_PATH,
        {
            "query": "更新学习路径，我想加强部署与监控",
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_LEARNING_PATH
    assert tool_call["args"] == {
        "grade_year": "",
        "learning_topic": "",
        "specific_requirements": "更新学习路径，我想加强部署与监控",
    }


def test_force_call_response_uses_section_markdown_for_course_resources() -> None:
    response = _force_call_response(
        AGENT_SECTION_MARKDOWN,
        {
            "query": "生成第一章内容",
            "course_knowledge": {"course_id": "year_3_course_1"},
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_SECTION_MARKDOWN
    assert tool_call["args"] == {
        "course_id": "year_3_course_1",
        "section_id": "1",
        "scope": "chapter_sections",
    }


def test_force_call_response_maps_current_course_resource_query_to_one_chapter() -> None:
    response = _force_call_response(
        AGENT_SECTION_MARKDOWN,
        {
            "query": "生成当前课程教学内容",
            "course_knowledge": {
                "course_id": "year_3_course_1",
                "sections": [
                    {"section_id": "1", "depth": 1, "order_index": 1, "title": "第一章"},
                    {"section_id": "2", "depth": 1, "order_index": 2, "title": "第二章"},
                ],
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_SECTION_MARKDOWN
    assert tool_call["args"] == {
        "course_id": "year_3_course_1",
        "section_id": "1",
        "scope": "chapter_sections",
    }


def test_force_call_response_maps_english_second_chapter_query_to_real_root_section() -> None:
    response = _force_call_response(
        AGENT_SECTION_MARKDOWN,
        {
            "query": (
                "Please generate chapter 2 Embedding Generation and Storage, "
                "including markdown, video resources, and HTML animations."
            ),
            "course_knowledge": {
                "course_id": "year_3_course_1",
                "sections": [
                    {"section_id": "1", "depth": 1, "order_index": 1, "title": "Data Ingestion & Chunking Strategy"},
                    {"section_id": "2", "depth": 1, "order_index": 2, "title": "Embedding Generation & Storage"},
                ],
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_SECTION_MARKDOWN
    assert tool_call["args"] == {
        "course_id": "year_3_course_1",
        "section_id": "2",
        "scope": "chapter_sections",
    }


def test_force_call_response_prompts_for_profile_details_on_generic_profile_update_query() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "更新个人画像",
            "messages": [],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，我需要先确认这次是否值得更新。")
    assert "发生了什么具体变化" in response["response"]
    assert "不会改画像" in response["response"]
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_prompts_for_profile_details_on_punctuated_generic_profile_update_query() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "更新个人画像。",
            "messages": [],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，我需要先确认这次是否值得更新。")
    assert "发生了什么具体变化" in response["response"]
    assert "不会改画像" in response["response"]
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_prompts_for_profile_details_on_profile_completion_query() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "完善我的个人画像",
            "messages": [],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，我需要先确认这次是否值得更新。")
    assert "发生了什么具体变化" in response["response"]
    assert "不会改画像" in response["response"]
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_prompts_for_profile_details_on_question_alignment_query() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "我现在想更新一下我的个人画像，进入提问环节",
            "messages": [],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，我需要先确认这次是否值得更新。")
    assert "发生了什么具体变化" in response["response"]
    assert "不会改画像" in response["response"]
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_prompts_for_profile_details_on_generic_path_refresh_after_completion() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "更新学习路径",
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
            ],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，我需要先确认这次是否值得更新。")
    assert "发生了什么具体变化" in response["response"]
    assert "不会改画像" in response["response"]
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_prompts_for_profile_details_on_punctuated_generic_path_refresh_after_completion() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "更新学习路径。",
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
            ],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，我需要先确认这次是否值得更新。")
    assert "发生了什么具体变化" in response["response"]
    assert "不会改画像" in response["response"]
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_pauses_followup_when_user_says_no_need_after_completion() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "先不用了",
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
            ],
        },
    )

    assert response["response"].startswith("好的，当前先不调整。")
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_force_call_response_pauses_profile_update_when_followup_has_no_change() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "没有具体变化，只是看看",
            "messages": [
                AIMessage(content="可以。更新个人画像前，我需要先确认这次是否值得更新。请先告诉我你想更新哪一块。"),
            ],
        },
    )

    assert response["response"].startswith("好的，当前先不调整。")
    message = response["messages"][0]
    assert message.content == response["response"]
    assert not message.tool_calls


def test_supervisor_node_returns_completion_reply_when_course_change_has_no_next_course() -> None:
    class GuardLlm:
        def bind_tools(self, _tools: list) -> GuardLlm:
            return self

        async def ainvoke(self, _messages: list) -> AIMessage:
            raise AssertionError("force_call path should bypass llm invocation")

    supervisor_node = create_supervisor_node(GuardLlm())

    result = asyncio.run(
        supervisor_node(
            {
                "query": "我不想要《AI 应用开发项目实战》了，现在帮我生成一门新课",
                "profile": _complete_profile(),
                "learning_path": {"grade_year": "year_3", "courses": []},
                "year_learning_paths": {
                    "year_3": {
                        "current_learning_course": {
                            "grade_id": "year_3",
                            "course_node_id": "year_3_course_2",
                        },
                        "grade_plans": {
                            "year_3": {
                                "course_nodes": [
                                    {"course_node_id": "year_3_course_1"},
                                    {"course_node_id": "year_3_course_2"},
                                ],
                            },
                        },
                    },
                },
                "messages": [],
            }
        )
    )

    assert result["response"].startswith("当前所有任务已经完成。")
    assert result["messages"][0].content == result["response"]


def test_force_call_response_uses_latest_grade_year_for_course_change_query() -> None:
    response = _force_call_response(
        AGENT_COURSE_KNOWLEDGE,
        {
            "query": "我不想要现在这门课了，现在帮我生成一门新课",
            "latest_grade_year": "year_4",
            "year_learning_paths": {
                "year_3": {
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                {"course_node_id": "year_3_course_1"},
                                {"course_node_id": "year_3_course_2"},
                            ],
                        },
                    },
                },
                "year_4": {
                    "current_learning_course": {
                        "grade_id": "year_4",
                        "course_node_id": "year_4_course_1",
                    },
                    "grade_plans": {
                        "year_4": {
                            "course_nodes": [
                                {"course_node_id": "year_4_course_1"},
                                {"course_node_id": "year_4_course_2"},
                            ],
                        },
                    },
                },
            },
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_COURSE_KNOWLEDGE
    assert tool_call["args"]["course_id"] == "year_4_course_2"


def test_build_system_prompt_counts_v2_course_nodes() -> None:
    prompt = build_system_prompt(
        {
            "profile": _complete_profile("大三软件工程学生"),
            "year_learning_paths": {
                "year_3": {
                    "schema_version": "learning_path.v2.course_node",
                    "grade_plans": {
                        "year_3": {
                            "grade_id": "year_3",
                            "grade_name": "大三",
                            "grade_goal": "完成 AI 项目",
                            "course_nodes": [
                                {"course_node_id": "year_3_course_1"},
                                {"course_node_id": "year_3_course_2"},
                            ],
                        },
                    },
                },
            },
        },
    )

    assert "大三(year_3) 学习路径已生成 — 2 门课程" in prompt
    assert "0 门课程" not in prompt


def test_build_system_prompt_marks_summary_only_profile_as_incomplete() -> None:
    prompt = build_system_prompt(
        {
            "profile": {"type": "basic_profile", "summary_text": "旧画像摘要"},
        },
    )

    assert "❌ 用户画像未完成" in prompt
    assert "✅ 用户画像已完成" not in prompt


def test_supervisor_node_direct_text_reply_for_chitchat_and_qa() -> None:
    class MockLlm:
        def __init__(self) -> None:
            self.tools: list = []
            self.called_messages: list = []
            
        def bind_tools(self, tools: list) -> MockLlm:
            self.tools = tools
            return self

        async def ainvoke(self, messages: list) -> AIMessage:
            self.called_messages = messages
            return AIMessage(content="FastAPI 是一个用于构建 API 的现代、快速（高性能）的 Web 框架。")

    mock_llm = MockLlm()
    supervisor_node = create_supervisor_node(mock_llm)
    
    result = asyncio.run(
        supervisor_node(
            {
                "query": "什么是 FastAPI",
                "profile": _complete_profile(),
                "year_learning_paths": {
                    "year_3": {
                        "current_learning_course": {
                            "grade_id": "year_3",
                            "course_node_id": "year_3_course_1",
                        }
                    }
                },
                "messages": [],
            }
        )
    )

    assert mock_llm.called_messages, "LLM was not called"
    system_msg = mock_llm.called_messages[0].content
    assert "## 核心决策逻辑" in system_msg
    assert "直接回复" in system_msg
    assert not result["messages"][0].tool_calls
    assert "FastAPI 是一个" in result["response"]

