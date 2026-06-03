"""Unit tests for the rule engine — pure logic, no LLM calls."""

from __future__ import annotations

import pytest

from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_PROFILE,
    evaluate,
    is_navigation_query,
    is_course_start_query,
    is_review_plan_query,
)


class TestIntentDetection:
    def test_navigation_query_keywords(self):
        assert is_navigation_query("下一步")
        assert is_navigation_query("然后呢")
        assert is_navigation_query("好的")
        assert is_navigation_query("ok")
        assert not is_navigation_query("我想学Python")

    def test_course_start_query(self):
        assert is_course_start_query("开始第一门课")
        assert is_course_start_query("开始学习")
        assert is_course_start_query("生成课程")
        assert not is_course_start_query("先看看")

    def test_review_plan_query(self):
        assert is_review_plan_query("先看看学习路径")
        assert is_review_plan_query("回顾规划")
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
