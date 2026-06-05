"""Unit tests for the rule engine — pure logic, no LLM calls."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_PROFILE,
    evaluate,
    has_pending_profile_update_followup,
    is_navigation_query,
    is_course_start_query,
    is_review_plan_query,
    should_auto_continue_learning_path_after_profile,
)


class TestIntentDetection:
    def test_navigation_query_keywords(self):
        assert is_navigation_query("下一步")
        assert is_navigation_query("然后呢")
        assert is_navigation_query("好的")
        assert is_navigation_query("ok")
        assert not is_navigation_query("我想学Python")
        assert not is_navigation_query("我想学好Python")
        assert not is_navigation_query("好的编程习惯有哪些？")
        assert not is_navigation_query("然后我想看看课程安排")

    def test_course_start_query(self):
        assert is_course_start_query("开始第一门课")
        assert is_course_start_query("开始学习")
        assert is_course_start_query("生成课程")
        assert not is_course_start_query("先看看")

    def test_review_plan_query(self):
        assert is_review_plan_query("先看看学习路径")
        assert is_review_plan_query("回顾规划")
        assert is_review_plan_query("我的学习路径里面要学哪些课？")
        assert not is_review_plan_query("开始学习")


class TestHardRules:
    def test_no_profile_blocks_path_and_course(self):
        """Rule 1: No completed profile → both path and course_knowledge blocked."""
        state = {"query": "hello", "profile": None, "learning_path": None}
        result = evaluate(state)

        assert AGENT_PROFILE in result.allowed_agents
        assert AGENT_LEARNING_PATH in result.blocked_agents
        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents

    def test_collecting_profile_forces_profile(self):
        """When profile type is 'collecting', force_call should be profile_agent."""
        state = {
            "query": "hello",
            "profile": {"type": "collecting", "stage": "basic_info"},
            "learning_path": None,
            "messages": [],
        }
        result = evaluate(state)

        assert result.force_call == AGENT_PROFILE
        assert AGENT_LEARNING_PATH in result.blocked_agents

    def test_basic_profile_no_path_blocks_course(self):
        """Rule 2: Has profile but no path → course_knowledge blocked."""
        state = {
            "query": "hello",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": None,
            "messages": [],
        }
        result = evaluate(state)

        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents
        assert AGENT_LEARNING_PATH in result.allowed_agents
        assert AGENT_PROFILE in result.allowed_agents

    def test_has_profile_and_path_allows_all(self):
        """Rule 3: Profile completed + path exists → all agents allowed."""
        state = {
            "query": "hello",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_1", "courses": []},
            "year_learning_paths": {"year_1": {"courses": []}},
            "messages": [],
        }
        result = evaluate(state)

        assert not result.blocked_agents
        assert result.force_call is None

    def test_course_start_query_forces_course_knowledge(self):
        """Explicit course start query forces course_knowledge_agent."""
        state = {
            "query": "开始学习",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_1", "courses": []},
            "year_learning_paths": {"year_1": {"courses": []}},
            "messages": [],
        }
        result = evaluate(state)

        assert result.force_call == AGENT_COURSE_KNOWLEDGE

    def test_course_change_query_forces_course_knowledge(self):
        state = {
            "query": "我不想要《AI Agent 开发基础能力搭建》了，现在帮我生成一门新课",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_3", "courses": []},
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
            "messages": [],
        }
        result = evaluate(state)

        assert result.force_call == AGENT_COURSE_KNOWLEDGE

    def test_profile_refinement_query_with_existing_path_forces_profile(self):
        state = {
            "query": "大3，软件工程，ai，周末集中",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_3", "courses": []},
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
                            ],
                        },
                    },
                },
            },
            "messages": [],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_PROFILE

    def test_profile_update_query_with_existing_path_forces_profile(self):
        state = {
            "query": "更新个人画像",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_3", "courses": []},
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
                            ],
                        },
                    },
                },
            },
            "messages": [],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_PROFILE

    def test_completed_tasks_followup_with_profile_details_forces_profile(self):
        state = {
            "query": "大三，软件工程，AI，周末集中",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
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
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
                HumanMessage(content="大三，软件工程，AI，周末集中"),
            ],
        }

        result = evaluate(state)

        assert has_pending_profile_update_followup(state) is True
        assert result.force_call == AGENT_PROFILE

    def test_profile_completion_after_completed_tasks_auto_continues_learning_path(self):
        state = {
            "query": "大三，软件工程，AI，周末集中",
            "profile": {
                "type": "basic_profile",
                "summary_text": "大三软件工程学生，继续强化 AI 应用开发。",
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
                    "short_term_goal": "更新项目方向",
                    "long_term_goal": "完成 AI 应用开发项目",
                    "weekly_available_time": "每周 8 小时",
                    "constraints": "周末集中",
                },
            },
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
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
                HumanMessage(content="大三，软件工程，AI，周末集中"),
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_PROFILE,
                        "args": {"conversation_summary": "大三，软件工程，AI，周末集中"},
                        "id": "force_profile_agent",
                    }],
                ),
                ToolMessage(
                    content=json.dumps({"profile": {"type": "basic_profile"}}, ensure_ascii=False),
                    tool_call_id="force_profile_agent",
                ),
            ],
        }

        result = evaluate(state)

        assert should_auto_continue_learning_path_after_profile(state) is True
        assert result.force_call == AGENT_LEARNING_PATH

    def test_learning_path_refresh_query_with_existing_path_forces_learning_path(self):
        state = {
            "query": "继续生成学习路径",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_3", "courses": []},
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
                            ],
                        },
                    },
                },
            },
            "messages": [],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_LEARNING_PATH

    def test_navigation_query_no_path_produces_hints(self):
        """Navigation query when profile completed but no path should produce hints."""
        state = {
            "query": "下一步",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": None,
            "messages": [],
        }
        result = evaluate(state)

        assert result.blocked_agents == {AGENT_COURSE_KNOWLEDGE}
        assert len(result.system_hints) > 0

    def test_review_plan_query_with_existing_path_blocks_all_agents(self):
        state = {
            "query": "我的学习路径里面要学哪些课？",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
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
                    "current_learning_course": {
                        "grade_id": "year_3",
                        "course_node_id": "year_3_course_1",
                    },
                },
            },
            "messages": [],
        }

        result = evaluate(state)

        assert result.force_call is None
        assert result.blocked_agents == {AGENT_PROFILE, AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}
        assert result.allowed_agents == set()

    def test_course_knowledge_completion_blocks_repeated_course_call_in_same_turn(self):
        state = {
            "query": "开始第一门课",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": {"grade_year": "year_1", "courses": []},
            "year_learning_paths": {"year_1": {"courses": []}},
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_COURSE_KNOWLEDGE,
                        "args": {"course_id": ""},
                        "id": "tool-course-1",
                    }],
                ),
                ToolMessage(
                    content=json.dumps({"course_knowledge": {"course_name": "AI 应用开发基础能力搭建"}}, ensure_ascii=False),
                    tool_call_id="tool-course-1",
                ),
            ],
        }

        result = evaluate(state)

        assert result.force_call is None
        assert result.blocked_agents == {AGENT_PROFILE, AGENT_LEARNING_PATH, AGENT_COURSE_KNOWLEDGE}
        assert result.allowed_agents == set()
