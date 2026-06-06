from __future__ import annotations

import asyncio
from langchain_core.messages import AIMessage

from app.orchestration.agents.supervisor import (
    _learning_path_force_args,
    _force_call_response,
    build_system_prompt,
    create_supervisor_node,
)
from app.orchestration.rule_engine import AGENT_COURSE_KNOWLEDGE, AGENT_LEARNING_PATH, AGENT_PROFILE


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


def test_force_call_response_prompts_for_profile_details_on_generic_profile_update_query() -> None:
    response = _force_call_response(
        AGENT_PROFILE,
        {
            "query": "更新个人画像",
            "messages": [],
        },
    )

    assert response["response"].startswith("可以。更新个人画像前，请先直接告诉我你想调整的具体信息。")
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

    assert response["response"].startswith("可以。更新个人画像前，请先直接告诉我你想调整的具体信息。")
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

    assert response["response"].startswith("可以。更新个人画像前，请先直接告诉我你想调整的具体信息。")
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

    assert response["response"].startswith("可以。更新个人画像前，请先直接告诉我你想调整的具体信息。")
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


def test_supervisor_node_returns_completion_reply_when_course_change_has_no_next_course() -> None:
    class GuardLlm:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
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
