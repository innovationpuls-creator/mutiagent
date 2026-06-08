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
    is_course_outline_regeneration_query,
    is_learning_path_refresh_query,
    has_pending_profile_update_followup,
    is_navigation_query,
    is_course_start_query,
    is_review_plan_query,
    should_auto_continue_learning_path_after_profile,
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


class TestIntentDetection:
    def test_navigation_query_keywords(self):
        assert is_navigation_query("下一步")
        assert is_navigation_query("下一步是什么？")
        assert is_navigation_query("然后呢")
        assert is_navigation_query("现在我应该干嘛")
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
        assert is_review_plan_query("我的学习路径？")
        assert is_review_plan_query("我现在的学习路径是什么")
        assert is_review_plan_query("现在的学习路径是什么")
        assert is_review_plan_query("我的学习路径里面要学哪些课？")
        assert not is_review_plan_query("我先看看我的个人画像，你推荐什么？")
        assert not is_review_plan_query("开始学习")

    def test_learning_path_refresh_query_accepts_grade_specific_phrase(self):
        assert is_learning_path_refresh_query("继续生成大三学习路径")
        assert is_learning_path_refresh_query("重新生成 year_3 学习路径")
        assert not is_learning_path_refresh_query("继续补充个人画像")


class TestHardRules:
    def test_no_profile_blocks_path_and_course(self):
        """Rule 1: No completed profile → both path and course_knowledge blocked."""
        state = {"query": "hello", "profile": None, "learning_path": None}
        result = evaluate(state)

        assert AGENT_PROFILE in result.allowed_agents
        assert AGENT_LEARNING_PATH in result.blocked_agents
        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents

    def test_no_profile_with_profile_details_forces_profile(self):
        state = {
            "query": "大三、软件工程、找工作、喜欢自己摸索，学习vibecoding",
            "profile": None,
            "learning_path": None,
            "messages": [HumanMessage(content="大三、软件工程、找工作、喜欢自己摸索，学习vibecoding")],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_PROFILE
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

    def test_summary_only_basic_profile_is_not_treated_as_completed(self):
        state = {
            "query": "hello",
            "profile": {"type": "basic_profile", "summary_text": "Test"},
            "learning_path": None,
            "messages": [],
        }

        result = evaluate(state)

        assert AGENT_PROFILE in result.allowed_agents
        assert AGENT_LEARNING_PATH in result.blocked_agents
        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents

    def test_basic_profile_no_path_blocks_course(self):
        """Rule 2: Has profile but no path → course_knowledge blocked."""
        state = {
            "query": "hello",
            "profile": _complete_profile(),
            "learning_path": None,
            "messages": [],
        }
        result = evaluate(state)

        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents
        assert AGENT_LEARNING_PATH in result.allowed_agents
        assert AGENT_PROFILE in result.allowed_agents

    def test_basic_profile_no_path_navigation_forces_learning_path(self):
        state = {
            "query": "下一步是什么？",
            "profile": _complete_profile("大三软件工程，想学习vibecoding。"),
            "learning_path": None,
            "year_learning_paths": None,
            "messages": [],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_LEARNING_PATH
        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents

    def test_basic_profile_no_path_refresh_query_forces_learning_path(self):
        state = {
            "query": "继续生成学习路径",
            "profile": _complete_profile("大三软件工程，想学习vibecoding。"),
            "learning_path": None,
            "year_learning_paths": None,
            "messages": [],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_LEARNING_PATH
        assert AGENT_COURSE_KNOWLEDGE in result.blocked_agents

    def test_profile_result_followed_by_grade_specific_refresh_still_forces_learning_path(self):
        state = {
            "query": "继续生成大三学习路径，方向就是 AI Agent 开发与部署",
            "profile": _complete_profile("大三软件工程，想学习 AI Agent 开发与部署。"),
            "learning_path": None,
            "year_learning_paths": None,
            "messages": [
                HumanMessage(content="我现在大三，软件工程专业，想做 AI Agent 项目。"),
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_PROFILE,
                        "args": {"conversation_summary": "我现在大三，软件工程专业，想做 AI Agent 项目。"},
                        "id": "profile_after_collecting",
                    }],
                ),
                ToolMessage(
                    content=json.dumps({"profile": _complete_profile("大三软件工程，想学习 AI Agent 开发与部署。")}, ensure_ascii=False),
                    tool_call_id="profile_after_collecting",
                ),
            ],
        }

        result = evaluate(state)

        assert result.force_call == AGENT_LEARNING_PATH
        assert AGENT_LEARNING_PATH not in result.blocked_agents

    def test_has_profile_and_path_allows_all(self):
        """Rule 3: Profile completed + path exists → all agents allowed."""
        state = {
            "query": "hello",
            "profile": _complete_profile(),
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
            "profile": _complete_profile(),
            "learning_path": {"grade_year": "year_1", "courses": []},
            "year_learning_paths": {"year_1": {"courses": []}},
            "messages": [],
        }
        result = evaluate(state)

        assert result.force_call == AGENT_COURSE_KNOWLEDGE

    def test_course_change_query_forces_course_knowledge(self):
        state = {
            "query": "我不想要《AI Agent 开发基础能力搭建》了，现在帮我生成一门新课",
            "profile": _complete_profile(),
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
            "profile": _complete_profile(),
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
            "query": "完善我的个人画像",
            "profile": _complete_profile(),
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

    def test_profile_update_question_alignment_query_with_existing_path_forces_profile(self):
        state = {
            "query": "我现在想更新一下我的个人画像，进入提问环节",
            "profile": _complete_profile(),
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

    def test_single_field_profile_update_with_existing_path_forces_profile(self):
        state = {
            "query": "专业改成计算机科学",
            "profile": _complete_profile(),
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
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
                HumanMessage(content="大三，软件工程，AI，周末集中"),
            ],
        }

        result = evaluate(state)

        assert has_pending_profile_update_followup(state) is True
        assert result.force_call == AGENT_PROFILE

    def test_completed_tasks_followup_with_navigation_query_stays_in_profile_update_flow(self):
        state = {
            "query": "下一步",
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
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
                HumanMessage(content="下一步"),
            ],
        }

        result = evaluate(state)

        assert has_pending_profile_update_followup(state) is True
        assert result.force_call == AGENT_PROFILE

    def test_completed_tasks_followup_with_generic_path_refresh_stays_in_profile_update_flow(self):
        state = {
            "query": "更新学习路径",
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
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
                HumanMessage(content="更新学习路径"),
            ],
        }

        result = evaluate(state)

        assert has_pending_profile_update_followup(state) is True
        assert result.force_call == AGENT_PROFILE

    def test_completed_tasks_followup_with_pause_query_stays_in_profile_update_flow(self):
        state = {
            "query": "先不用了",
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
            "messages": [
                AIMessage(content="当前所有任务已经完成。如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"),
                HumanMessage(content="先不用了"),
            ],
        }

        result = evaluate(state)

        assert has_pending_profile_update_followup(state) is True
        assert result.force_call == AGENT_PROFILE

    def test_profile_update_prompt_followup_with_no_change_uses_profile_force_call_text_gate(self):
        state = {
            "query": "没有具体变化，只是看看",
            "profile": _complete_profile(),
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
            "messages": [
                AIMessage(content="可以。更新个人画像前，我需要先确认这次是否值得更新。请先告诉我你想更新哪一块。"),
                HumanMessage(content="没有具体变化，只是看看"),
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
                    content=json.dumps({"profile": _complete_profile("大三软件工程学生，继续强化 AI 应用开发。")}, ensure_ascii=False),
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
            "profile": _complete_profile(),
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
            "profile": _complete_profile(),
            "learning_path": None,
            "messages": [],
        }
        result = evaluate(state)

        assert result.blocked_agents == {AGENT_COURSE_KNOWLEDGE}
        assert len(result.system_hints) > 0

    def test_review_plan_query_with_existing_path_blocks_all_agents(self):
        state = {
            "query": "我的学习路径里面要学哪些课？",
            "profile": _complete_profile(),
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
            "profile": _complete_profile(),
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


from app.orchestration.rule_engine import (
    AGENT_SECTION_MARKDOWN,
    AGENT_SECTION_VIDEO_SEARCH,
    AGENT_SECTION_HTML_ANIMATION,
    is_course_resource_generation_query,
)


def test_course_resource_generation_query_keywords() -> None:
    assert is_course_resource_generation_query("生成当前课程教学内容")
    assert is_course_resource_generation_query("生成第一章内容")
    assert is_course_resource_generation_query(
        "Please generate chapter 2 markdown, video resources, and HTML animations for this course.",
    )
    assert not is_course_resource_generation_query("开始学习这门课")
    assert not is_course_resource_generation_query("先看看学习路径")


def test_course_outline_regeneration_query_accepts_named_chapter_outline_request() -> None:
    assert is_course_outline_regeneration_query("帮我重新生成AI Agent 开发基础能力搭建的章节大纲")
    assert is_course_outline_regeneration_query("帮我生成AI应用核心架构与RAG实战的章节大纲")
    assert is_course_outline_regeneration_query("帮我生成构建本地知识库问答系统 (RAG基础)的大纲")


def test_named_chapter_outline_regeneration_forces_course_knowledge() -> None:
    state = {
        "query": "帮我重新生成AI Agent 开发基础能力搭建的章节大纲",
        "profile": _complete_profile(),
        "year_learning_paths": {
            "year_3": {
                "current_learning_course": {"grade_id": "year_3", "course_node_id": "year_3_course_1"},
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
        "course_knowledge": {"course_id": "year_3_course_1", "sections": [{"section_id": "1"}]},
        "messages": [],
    }

    result = evaluate(state)

    assert result.force_call == AGENT_COURSE_KNOWLEDGE


def test_profile_path_and_outline_forces_course_knowledge_for_outline_regeneration() -> None:
    state = {
        "query": "重新生成该课程的大纲",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": {"course_id": "year_3_course_1", "sections": [{"section_id": "1"}]},
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_COURSE_KNOWLEDGE


def test_profile_and_path_without_outline_forces_course_knowledge_for_resources() -> None:
    state = {
        "query": "生成当前课程教学内容",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": None,
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_COURSE_KNOWLEDGE
    assert AGENT_SECTION_MARKDOWN in result.blocked_agents
    assert AGENT_SECTION_VIDEO_SEARCH in result.blocked_agents
    assert AGENT_SECTION_HTML_ANIMATION in result.blocked_agents


def test_profile_path_and_outline_forces_section_markdown_for_resources() -> None:
    state = {
        "query": "生成当前课程教学内容",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": {"course_id": "year_3_course_1", "sections": []},
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_SECTION_MARKDOWN


def test_profile_path_and_outline_treats_start_course_as_outline_generation() -> None:
    state = {
        "query": "开始学习这门课",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": {"course_id": "year_3_course_1", "sections": []},
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_COURSE_KNOWLEDGE


def test_profile_path_without_outline_treats_ok_start_as_outline_generation() -> None:
    state = {
        "query": "ok，开始",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": None,
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_COURSE_KNOWLEDGE


def test_resource_query_after_course_knowledge_forces_section_markdown() -> None:
    state = {
        "query": "生成当前课程教学内容",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": {"course_id": "year_3_course_1", "sections": [{"section_id": "1"}]},
        "messages": [
            HumanMessage(content="生成当前课程教学内容"),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": AGENT_COURSE_KNOWLEDGE,
                    "args": {"course_id": "year_3_course_1"},
                    "id": "force_course_knowledge_agent",
                }],
            ),
            ToolMessage(
                content='{"course_id": "year_3_course_1"}',
                tool_call_id="force_course_knowledge_agent",
            ),
        ],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_SECTION_MARKDOWN
