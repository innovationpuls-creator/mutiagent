from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.orchestration.agent_plan import (
    AgentCall,
    LearningPathResult,
    MainAgentResult,
    validate_call_graph,
)
from app.orchestration.response_parser import parse_json_answer


def test_parse_json_answer_accepts_plain_json() -> None:
    result = parse_json_answer(
        {
            "answer": '{"response":{"user_message":"你好","question_box":null},'
            '"control":{"action":"reply_only","calls":[]}}'
        }
    )

    assert result["response"]["user_message"] == "你好"


def test_main_agent_result_requires_known_agent_key() -> None:
    with pytest.raises(ValidationError):
        MainAgentResult.model_validate(
            {
                "response": {"user_message": "处理中", "question_box": None},
                "control": {
                    "action": "call_agents",
                    "calls": [
                        {
                            "call_id": "bad_call",
                            "agent_key": "unknown_agent",
                            "label": "未知",
                            "depends_on": [],
                            "parallel_group": None,
                            "agent_input": {},
                        }
                    ],
                },
            }
        )


def test_validate_call_graph_rejects_missing_dependency() -> None:
    call = AgentCall(
        call_id="learning_path",
        agent_key="learning_path_agent",
        label="学习路径",
        depends_on=["profile_missing"],
        parallel_group=None,
        agent_input={},
    )

    with pytest.raises(ValueError, match="depends_on references unknown call_id"):
        validate_call_graph([call])


def test_learning_path_result_requires_four_sections() -> None:
    result = LearningPathResult.model_validate(
        {
            "learning_goal": {
                "target_course_or_skill": "数据结构",
                "target_completion_time": "大二结束前",
                "goal_type": "课程学习",
                "desired_outcome": "能完成课程项目",
            },
            "gap_analysis": {
                "current_mastered_content": ["Python 基础"],
                "current_weaknesses": ["算法复杂度"],
                "required_capabilities": ["线性表", "树", "图"],
                "main_gaps": ["缺少系统刷题"],
            },
            "foundation_path": {
                "stages": [
                    {
                        "stage_id": "year_1",
                        "stage_name": "大一基础",
                        "learning_goal": "打牢编程基础",
                        "learning_content": ["Python", "C 语言"],
                        "learning_tasks": ["完成 20 个基础练习"],
                        "recommended_methods": ["课程学习"],
                        "completion_standard": ["能独立写小程序"],
                    }
                ]
            },
            "generated_path": {
                "overall_goal": "形成数据结构学习路径",
                "stage_routes": [{"stage_id": "year_1", "route_summary": "先补编程基础"}],
                "schedule": [{"period": "大一上", "focus": "编程基础", "milestone": "完成基础项目"}],
                "task_checklist": ["每周练习 3 次"],
                "recommended_resource_types": ["教材", "题库"],
                "stage_acceptance_criteria": [{"stage_id": "year_1", "criteria": ["完成项目"]}],
                "next_actions": ["本周开始复习数组和链表"],
            },
        }
    )

    assert result.learning_goal.target_course_or_skill == "数据结构"
