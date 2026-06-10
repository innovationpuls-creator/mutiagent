from __future__ import annotations

import asyncio
from pathlib import Path

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import UserProfile
from langchain_core.messages import AIMessage, HumanMessage

from app.orchestration.agents.profile import _build_profile_input, _is_complete_profile, run_profile_agent
from app.orchestration.agents.models import ProfileOutput
from app.orchestration.rule_engine import AGENT_LEARNING_PATH, AGENT_PROFILE, evaluate


class ScriptedStructuredLlm:
    def __init__(self, responses: list[object]) -> None:
        self.calls = 0
        self._responses = list(responses)

    def with_structured_output(self, *_args, **_kwargs):
        async def invoke(_messages):
            if self.calls >= len(self._responses):
                raise AssertionError("unexpected extra structured llm call")
            response = self._responses[self.calls]
            self.calls += 1
            if isinstance(response, Exception):
                raise response
            if isinstance(response, ProfileOutput):
                return response
            if isinstance(response, dict):
                return ProfileOutput(**response)
            raise AssertionError(f"unsupported scripted response: {type(response)!r}")

        return invoke


def _profile() -> dict:
    return {
        "type": "basic_profile",
        "stage": "generated",
        "question_mode": "question_box",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "有基础",
            "has_clear_goal": "大致有方向",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "按项目里程碑推进",
            "content_preference": ["代码实践", "项目案例", "AI 对话调试"],
            "need_guidance": "需要轻量提醒",
            "knowledge_foundation": "软件工程基础",
            "strengths": "工程实现",
            "weaknesses": "大型项目实战经验、数据库设计能力、英文阅读速度",
            "experience": "平时学习",
            "short_term_goal": "在 3 个月内独立开发一个具备完整前后端功能的 Web 应用，并部署上线",
            "long_term_goal": "形成 AI 应用开发能力",
            "weekly_available_time": "每周 6-10 小时",
            "constraints": "平时学习节奏",
        },
        "defaulted_fields": ["learning_stage"],
        "question_md": "画像已生成，是否继续生成学习路径？",
        "question_box": {"question": "下一步做什么？", "options": []},
        "text": "【基础学习画像总结】大三软件工程 AI 方向。",
    }


def test_complete_profile_requires_session_message_shape() -> None:
    assert _is_complete_profile(_profile()) is True
    assert _is_complete_profile({"current_grade": "大三", "major": "软件工程"}) is False


def test_complete_profile_rejects_unsupported_postgraduate_grade() -> None:
    profile = _profile()
    profile["confirmed_info"]["current_grade"] = "研一"

    assert _is_complete_profile(profile) is False


def test_build_profile_input_includes_history_and_default_instruction() -> None:
    state = {
        "query": "直接帮我生成，不确定的你随便帮我填",
        "messages": [
            HumanMessage(content="大3，软件工程，ai，平时学习"),
            AIMessage(content="生成学习路径时遇到问题"),
            HumanMessage(content="直接帮我生成，不确定的你随便帮我填"),
        ],
    }

    text = _build_profile_input(state, "直接帮我生成，不确定的你随便帮我填")

    assert "大3，软件工程，ai，平时学习" in text
    assert "允许系统补全所有缺失字段" in text
    assert "输出 SessionMessage JSON" in text


def test_build_profile_input_does_not_allow_default_fill_from_summary_only() -> None:
    state = {
        "query": "我现在大三、软件工程、想学习agent开发vibe coding",
        "messages": [
            HumanMessage(content="我现在大三、软件工程、想学习agent开发vibe coding"),
            AIMessage(content="我先继续帮你整理基础画像。请直接补充你当前还没确认的学习阶段、目标、学习方式、时间安排或能力基础。"),
            HumanMessage(content="我现在大三、软件工程、想学习agent开发vibe coding"),
        ],
    }
    conversation_summary = (
        "我先继续帮你整理基础画像。"
        "请直接补充你当前还没确认的学习阶段、目标、学习方式、时间安排或能力基础。\n"
        "我现在大三、软件工程、想学习agent开发vibe coding"
    )

    text = _build_profile_input(state, conversation_summary)

    assert "是否允许系统补全缺失字段：否" in text
    assert "允许系统补全所有缺失字段" not in text


def test_rule_engine_allows_learning_path_after_complete_profile() -> None:
    result = evaluate({"query": "继续", "profile": _profile(), "year_learning_paths": None})

    assert AGENT_LEARNING_PATH in result.allowed_agents
    assert AGENT_PROFILE in result.allowed_agents


def test_rule_engine_force_calls_profile_for_default_fill_query() -> None:
    result = evaluate({"query": "你直接按照默认给我一份基础画像", "messages": []})

    assert result.force_call == AGENT_PROFILE


def test_rule_engine_force_calls_profile_for_profile_refinement_query() -> None:
    result = evaluate({
        "query": "大3，软件工程，ai，平时学习",
        "profile": _profile(),
        "year_learning_paths": None,
        "messages": [],
    })

    assert result.force_call == AGENT_PROFILE


def test_rule_engine_force_calls_learning_path_for_direct_generate_after_profile() -> None:
    result = evaluate({
        "query": "直接帮我生成，不确定的你随便帮我填",
        "profile": _profile(),
        "year_learning_paths": None,
        "messages": [],
    })

    assert result.force_call == AGENT_LEARNING_PATH


def test_rule_engine_does_not_chain_learning_path_in_same_turn_as_profile_generation() -> None:
    result = evaluate({
        "query": "你直接按照默认给我一份基础画像",
        "profile": _profile(),
        "year_learning_paths": None,
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": AGENT_PROFILE,
                    "args": {"conversation_summary": "用户说：你直接按照默认给我一份基础画像"},
                    "id": "tool-profile-1",
                }],
            ),
            ToolMessage(
                content=json.dumps({"profile": _profile()}, ensure_ascii=False),
                tool_call_id="tool-profile-1",
            ),
        ],
    })

    assert result.force_call is None
    assert AGENT_LEARNING_PATH in result.blocked_agents


def test_rule_engine_does_not_recall_agents_in_same_turn_as_learning_path_generation() -> None:
    result = evaluate({
        "query": "直接帮我生成，不确定的你随便帮我填",
        "profile": _profile(),
        "year_learning_paths": {
            "year_3": {
                "schema_version": "learning_path.v2.course_node",
                "grade_plans": {"year_3": {"course_nodes": []}},
                "current_learning_course": {
                    "grade_id": "year_3",
                    "course_node_id": "year_3_course_1",
                },
            },
        },
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": AGENT_LEARNING_PATH,
                    "args": {
                        "grade_year": "",
                        "learning_topic": "AI 应用开发",
                        "specific_requirements": "",
                    },
                    "id": "tool-learning-path-1",
                }],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "year_learning_path": {
                            "schema_version": "learning_path.v2.course_node",
                            "grade_plans": {"year_3": {"course_nodes": []}},
                            "current_learning_course": {
                                "grade_id": "year_3",
                                "course_node_id": "year_3_course_1",
                            },
                        },
                        "grade_year": "year_3",
                    },
                    ensure_ascii=False,
                ),
                tool_call_id="tool-learning-path-1",
            ),
        ],
    })

    assert result.force_call is None
    assert not result.allowed_agents
    assert AGENT_LEARNING_PATH in result.blocked_agents


def test_run_profile_agent_local_default_profile_persists(tmp_path: Path) -> None:
    profile = _profile()
    profile["confirmed_info"]["current_grade"] = "大3"
    profile["text"] = "【基础学习画像总结】大3软件工程 AI 方向。"
    llm = ScriptedStructuredLlm([profile])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-fast-path.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "query": "你直接按照默认给我一份基础画像",
        "messages": [HumanMessage(content="大3，软件工程，ai，平时学习")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "basic_profile"
    assert result["profile"]["stage"] == "generated"
    assert result["profile"]["defaulted_fields"]
    assert result["response"] == result["profile"]["text"]
    assert result["profile"]["summary_text"] == result["profile"]["text"]
    assert result["profile"]["confirmed_info"]["current_grade"] == "大3"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert llm.calls == 1

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["type"] == "basic_profile"
    assert row.profile_data["confirmed_info"]["current_grade"] == "大3"
    assert row.profile_data["summary_text"] == "【基础学习画像总结】大3软件工程 AI 方向。"


def test_run_profile_agent_default_profile_ignores_greeting_as_major(tmp_path: Path) -> None:
    llm = ScriptedStructuredLlm([_profile()])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-ignore-greeting.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "query": "你直接按照默认给我一份基础画像",
        "messages": [HumanMessage(content="你好")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert "你好" not in result["profile"]["summary_text"]
    assert llm.calls == 1


def test_run_profile_agent_keeps_pace_segment_out_of_major(tmp_path: Path) -> None:
    profile = _profile()
    profile["confirmed_info"]["current_grade"] = "大四"
    profile["confirmed_info"]["major"] = "计算机科学"
    profile["confirmed_info"]["constraints"] = "周末集中"
    profile["text"] = "【基础学习画像总结】大四计算机科学，继续围绕 AI 应用开发推进。"
    llm = ScriptedStructuredLlm([profile])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-major-pace.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000009",
        "query": "大四，计算机科学，AI，周末集中",
        "profile": _profile(),
        "messages": [HumanMessage(content="大四，计算机科学，AI，周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大四"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"
    assert llm.calls == 0


def test_run_profile_agent_returns_collecting_for_unsupported_postgraduate_grade(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-unsupported-grade.db'}")
    set_engine(engine)
    init_db(engine)

    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "研一",
            "major": "软件工程",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": [],
            "need_guidance": "",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "当前学习路径只支持大一到大四。如果你想继续生成学习路径，请先告诉我对应的本科年级（大一到大四）。",
        "question_box": {
            "question": "当前学习路径只支持大一到大四。如果你想继续生成学习路径，请先告诉我对应的本科年级（大一到大四）。",
            "options": [],
        },
        "text": "当前学习路径只支持大一到大四。如果你想继续生成学习路径，请先告诉我对应的本科年级（大一到大四）。",
    }])

    state = {
        "user_id": "00000000-0000-0000-0000-000000000015",
        "query": "研一，软件工程，AI，周末集中",
        "messages": [HumanMessage(content="研一，软件工程，AI，周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "basic_info"
    assert result["profile"]["confirmed_info"]["current_grade"] == "研一"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert result["response"] == result["profile"]["text"]
    assert "当前学习路径只支持大一到大四" in result["response"]
    assert "本科年级" in result["response"]

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["type"] == "collecting"
    assert row.profile_data["confirmed_info"]["current_grade"] == "研一"


def test_run_profile_agent_updates_explicit_major_field_without_treating_whole_sentence_as_major(tmp_path: Path) -> None:
    profile = _profile()
    profile["confirmed_info"]["major"] = "计算机科学"
    profile["text"] = "【基础学习画像总结】大三计算机科学 AI 方向。"
    llm = ScriptedStructuredLlm([profile])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-explicit-major.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000010",
        "query": "专业改成计算机科学",
        "profile": _profile(),
        "messages": [HumanMessage(content="专业改成计算机科学")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert "专业改成计算机科学" not in result["profile"]["summary_text"]
    assert llm.calls == 0


def test_run_profile_agent_rewrites_system_generated_knowledge_foundation_after_major_update(tmp_path: Path) -> None:
    profile_response = _profile()
    profile_response["confirmed_info"]["major"] = "计算机科学"
    profile_response["confirmed_info"]["knowledge_foundation"] = "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    profile_response["text"] = "【基础学习画像总结】大三计算机科学 AI 方向。"
    llm = ScriptedStructuredLlm([profile_response])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-generated-knowledge-foundation.db'}")
    set_engine(engine)
    init_db(engine)

    profile = _profile()
    profile["confirmed_info"]["knowledge_foundation"] = "已具备软件工程基础，AI 应用开发方向可从入门到基础逐步补全"

    state = {
        "user_id": "00000000-0000-0000-0000-000000000012",
        "query": "专业改成计算机科学",
        "profile": profile,
        "messages": [HumanMessage(content="专业改成计算机科学")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert (
        result["profile"]["confirmed_info"]["knowledge_foundation"]
        == "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    )
    assert llm.calls == 0


def test_run_profile_agent_restores_generated_knowledge_foundation_when_existing_complete_profile_field_is_empty(tmp_path: Path) -> None:
    profile_response = _profile()
    profile_response["confirmed_info"]["major"] = "计算机科学"
    profile_response["confirmed_info"]["constraints"] = "周末集中"
    profile_response["confirmed_info"]["knowledge_foundation"] = "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    profile_response["text"] = "【基础学习画像总结】大三计算机科学，当前限制为周末集中。"
    llm = ScriptedStructuredLlm([profile_response])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-empty-generated-knowledge-foundation.db'}")
    set_engine(engine)
    init_db(engine)

    profile = _profile()
    profile["confirmed_info"]["knowledge_foundation"] = ""

    state = {
        "user_id": "00000000-0000-0000-0000-000000000014",
        "query": "专业改成计算机科学，当前限制改成周末集中",
        "profile": profile,
        "messages": [HumanMessage(content="专业改成计算机科学，当前限制改成周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"
    assert (
        result["profile"]["confirmed_info"]["knowledge_foundation"]
        == "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    )
    assert llm.calls == 0


def test_run_profile_agent_updates_multiple_explicit_fields_in_one_sentence(tmp_path: Path) -> None:
    profile = _profile()
    profile["confirmed_info"]["major"] = "计算机科学"
    profile["confirmed_info"]["constraints"] = "周末集中"
    profile["text"] = "【基础学习画像总结】大三计算机科学，当前限制为周末集中。"
    llm = ScriptedStructuredLlm([profile])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-explicit-multi-field.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000011",
        "query": "专业改成计算机科学，当前限制改成周末集中",
        "profile": _profile(),
        "messages": [HumanMessage(content="专业改成计算机科学，当前限制改成周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"
    assert "当前限制改成周末集中" not in result["profile"]["summary_text"]
    assert llm.calls == 0


def test_run_profile_agent_prefers_latest_explicit_profile_update_from_history(tmp_path: Path) -> None:
    profile_response = _profile()
    profile_response["confirmed_info"]["major"] = "人工智能"
    profile_response["confirmed_info"]["constraints"] = "每天少量"
    profile_response["confirmed_info"]["knowledge_foundation"] = "已具备人工智能基础，AI 应用开发方向可从入门到基础逐步补全"
    profile_response["text"] = "【基础学习画像总结】大三人工智能，当前以每天少量的节奏推进。"
    llm = ScriptedStructuredLlm([profile_response])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-explicit-history-latest.db'}")
    set_engine(engine)
    init_db(engine)

    profile = _profile()
    profile["confirmed_info"]["knowledge_foundation"] = "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    state = {
        "user_id": "00000000-0000-0000-0000-000000000013",
        "query": "专业改成人工智能，当前限制改成每天少量",
        "profile": profile,
        "messages": [
            HumanMessage(content="专业改成计算机科学，当前限制改成周末集中"),
            HumanMessage(content="专业改成人工智能，当前限制改成每天少量"),
        ],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["major"] == "人工智能"
    assert result["profile"]["confirmed_info"]["constraints"] == "每天少量"
    assert (
        result["profile"]["confirmed_info"]["knowledge_foundation"]
        == "已具备人工智能基础，AI 应用开发方向可从入门到基础逐步补全"
    )
    assert llm.calls == 0


def test_run_profile_agent_prefers_latest_implicit_grade_and_major_from_history(tmp_path: Path) -> None:
    profile = _profile()
    profile["confirmed_info"]["current_grade"] = "大四"
    profile["confirmed_info"]["major"] = "计算机科学"
    profile["confirmed_info"]["constraints"] = "周末集中"
    profile["text"] = "【基础学习画像总结】大四计算机科学，当前限制为周末集中。"
    llm = ScriptedStructuredLlm([profile])

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-implicit-history-latest.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000016",
        "query": "大四，计算机科学，AI，周末集中",
        "profile": _profile(),
        "messages": [
            HumanMessage(content="大三，软件工程，AI，周末集中"),
            HumanMessage(content="继续生成学习路径"),
            HumanMessage(content="我不想要当前这门课了，现在帮我生成一门新课"),
            HumanMessage(content="大四，计算机科学，AI，周末集中"),
        ],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大四"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"
    assert llm.calls == 0


def test_run_profile_agent_first_profile_requests_missing_major_in_collecting_mode(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-first-signal.db'}")
    set_engine(engine)
    init_db(engine)

    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "大三",
            "major": "",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": [],
            "need_guidance": "",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "为了生成基础画像，请先告诉我你的专业。",
        "question_box": {
            "question": "为了生成基础画像，请先告诉我你的专业。",
            "options": [
                {"label": "软件工程", "value": "软件工程", "description": "常见软件开发相关专业方向", "target_fields": ["major"], "fills": {"major": "软件工程"}},
                {"label": "其他", "value": "__free_text__", "description": "以上都不符合，我来输入", "target_fields": [], "fills": {}},
            ],
        },
        "text": "为了生成基础画像，请先告诉我你的专业。",
    }])

    state = {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "query": "我现在大三，你看看我的个人画像，你推荐什么？",
        "messages": [
            HumanMessage(content="你好"),
            HumanMessage(content="我现在大三，你看看我的个人画像，你推荐什么？"),
        ],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "basic_info"
    assert result["profile"]["question_mode"] == "question_box"
    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == ""
    assert result["profile"]["question_box"]["question"] == "为了生成基础画像，请先告诉我你的专业。"
    assert result["profile"]["question_box"]["options"]
    assert "请先告诉我你的专业" in result["response"]
    assert result["response"] == result["profile"]["text"]

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["type"] == "collecting"
    assert row.profile_data["confirmed_info"]["current_grade"] == "大三"


def test_run_profile_agent_uses_existing_collecting_profile_to_finish_basic_profile(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-follow-up.db'}")
    set_engine(engine)
    init_db(engine)

    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "learning_preference",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": [],
            "need_guidance": "",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "你目前的学习阶段是？",
        "question_box": {
            "question": "你目前的学习阶段是？",
            "options": [
                {"label": "有基础", "value": "有基础", "description": "已学过相关课程，有一定基础", "target_fields": ["learning_stage"], "fills": {"learning_stage": "有基础"}},
                {"label": "其他", "value": "__free_text__", "description": "以上都不符合，我来输入", "target_fields": [], "fills": {}},
            ],
        },
        "text": "你目前的学习阶段是？",
    }])

    state = {
        "user_id": "00000000-0000-0000-0000-000000000003",
        "query": "软件工程",
        "profile": {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_md",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "",
                "learning_stage": "",
                "has_clear_goal": "",
                "learning_method_preference": "",
                "learning_pace_preference": "",
                "content_preference": [],
                "need_guidance": "",
                "knowledge_foundation": "",
                "strengths": "",
                "weaknesses": "",
                "experience": "",
                "short_term_goal": "",
                "long_term_goal": "",
                "weekly_available_time": "",
                "constraints": "",
            },
            "defaulted_fields": [],
            "question_md": "为了生成基础画像，请先告诉我你的专业。",
            "question_box": {"question": "", "options": []},
            "text": "为了生成基础画像，请先告诉我你的专业。",
        },
        "messages": [
            HumanMessage(content="我现在大三"),
            HumanMessage(content="软件工程"),
        ],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "learning_preference"
    assert result["profile"]["question_mode"] == "question_box"
    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert result["profile"]["question_box"]["options"]
    assert result["response"] == result["profile"]["text"]


def test_run_profile_agent_uses_current_collecting_question_to_parse_free_text_answer(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-current-question-parse.db'}")
    set_engine(engine)
    init_db(engine)

    major_state = {
        "user_id": "00000000-0000-0000-0000-000000000022",
        "query": "软件工程",
        "profile": {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_box",
            "confirmed_info": {
                "current_grade": "大三",
                "major": "",
                "learning_stage": "",
                "has_clear_goal": "",
                "learning_method_preference": "",
                "learning_pace_preference": "",
                "content_preference": ["文档"],
                "need_guidance": "需要强引导",
                "knowledge_foundation": "",
                "strengths": "",
                "weaknesses": "",
                "experience": "",
                "short_term_goal": "学习vibecoding",
                "long_term_goal": "",
                "weekly_available_time": "",
                "constraints": "",
            },
            "defaulted_fields": [],
            "question_md": "为了生成基础画像，请先告诉我你的专业。",
            "question_box": {
                "question": "为了生成基础画像，请先告诉我你的专业。",
                "options": [
                    {"label": "计算机科学", "value": "计算机科学", "description": "", "target_fields": ["major"], "fills": {"major": "计算机科学"}},
                    {"label": "软件工程", "value": "软件工程", "description": "", "target_fields": ["major"], "fills": {"major": "软件工程"}},
                    {"label": "其他", "value": "__free_text__", "description": "", "target_fields": [], "fills": {}},
                ],
            },
            "text": "为了生成基础画像，请先告诉我你的专业。",
        },
        "messages": [HumanMessage(content="软件工程")],
    }

    major_llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "learning_preference",
        "question_mode": "question_box",
        "confirmed_info": {
            **major_state["profile"]["confirmed_info"],
            "major": "软件工程",
        },
        "defaulted_fields": [],
        "question_md": "你目前的学习阶段是？",
        "question_box": {
            "question": "你目前的学习阶段是？",
            "options": [
                {"label": "刚入门", "value": "刚入门", "description": "刚开始接触这个领域", "target_fields": ["learning_stage"], "fills": {"learning_stage": "刚入门"}},
                {"label": "其他", "value": "__free_text__", "description": "以上都不符合，我来输入", "target_fields": [], "fills": {}},
            ],
        },
        "text": "你目前的学习阶段是？",
    }])
    major_result = asyncio.run(run_profile_agent(major_state, major_llm))

    assert major_result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert major_result["profile"]["stage"] == "learning_preference"
    assert major_result["profile"]["question_mode"] == "question_box"
    assert major_result["profile"]["question_box"]["question"] == "你目前的学习阶段是？"

    learning_stage_state = {
        "user_id": "00000000-0000-0000-0000-000000000022",
        "query": "初学者",
        "profile": major_result["profile"],
        "messages": [HumanMessage(content="初学者")],
    }

    learning_stage_llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "learning_preference",
        "question_mode": "question_box",
        "confirmed_info": {
            **major_result["profile"]["confirmed_info"],
            "learning_stage": "刚入门",
        },
        "defaulted_fields": [],
        "question_md": "你的学习目标清晰吗？",
        "question_box": {
            "question": "你的学习目标清晰吗？",
            "options": [
                {"label": "目标明确", "value": "是", "description": "清楚自己要学什么", "target_fields": ["has_clear_goal"], "fills": {"has_clear_goal": "是"}},
                {"label": "其他", "value": "__free_text__", "description": "以上都不符合，我来输入", "target_fields": [], "fills": {}},
            ],
        },
        "text": "你的学习目标清晰吗？",
    }])
    learning_stage_result = asyncio.run(run_profile_agent(learning_stage_state, learning_stage_llm))

    assert learning_stage_result["profile"]["confirmed_info"]["learning_stage"] == "刚入门"
    assert learning_stage_result["profile"]["stage"] == "learning_preference"
    assert learning_stage_result["profile"]["question_mode"] == "question_box"
    assert learning_stage_result["profile"]["question_box"]["question"] == "你的学习目标清晰吗？"


def test_run_profile_agent_maps_user_delimited_profile_without_fake_fields(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-delimited-real-input.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = "大三、软件工程、找工作、喜欢自己摸索，学习vibecoding"
    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "learning_preference",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "喜欢自己摸索",
            "learning_pace_preference": "",
            "content_preference": [],
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
        "question_md": "你目前的学习阶段是？",
        "question_box": {"question": "你目前的学习阶段是？", "options": []},
        "text": "你目前的学习阶段是？",
    }])
    state = {
        "user_id": "00000000-0000-0000-0000-000000000004",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    confirmed = result["profile"]["confirmed_info"]
    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["question_mode"] == "question_box"
    assert confirmed["current_grade"] == "大三"
    assert confirmed["major"] == "软件工程"
    assert confirmed["short_term_goal"] == "找工作，学习vibecoding"
    assert confirmed["learning_method_preference"] == "喜欢自己摸索"
    assert confirmed["learning_stage"] == ""
    assert confirmed["knowledge_foundation"] == ""
    assert confirmed["strengths"] == ""
    assert confirmed["weaknesses"] == ""
    assert confirmed["experience"] == ""
    assert confirmed["weekly_available_time"] == ""
    assert result["profile"]["defaulted_fields"] == []
    assert result["profile"]["question_box"]["question"] == "你目前的学习阶段是？"


def test_run_profile_agent_rejects_llm_completed_profile_for_brief_profile_input(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-brief-no-fake-completion.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = "我现在大三、软件工程、想学习agent开发vibe coding"
    completed_profile = _profile()
    completed_profile["confirmed_info"]["learning_stage"] = "项目实践"
    completed_profile["confirmed_info"]["has_clear_goal"] = "是"
    completed_profile["confirmed_info"]["learning_method_preference"] = "AI 交互式学习"
    completed_profile["confirmed_info"]["learning_pace_preference"] = "按项目里程碑推进"
    completed_profile["confirmed_info"]["content_preference"] = ["代码实践", "项目案例", "AI 对话调试"]
    completed_profile["confirmed_info"]["need_guidance"] = "需要轻量提醒"
    completed_profile["confirmed_info"]["knowledge_foundation"] = "软件工程基础"
    completed_profile["confirmed_info"]["strengths"] = "工程能力强"
    completed_profile["confirmed_info"]["weaknesses"] = "缺少 Agent 开发全链路经验"
    completed_profile["confirmed_info"]["experience"] = "常规软件开发经验"
    completed_profile["confirmed_info"]["short_term_goal"] = "独立完成一个 AI Agent"
    completed_profile["confirmed_info"]["long_term_goal"] = "成为 AI Native 应用开发者"
    completed_profile["confirmed_info"]["weekly_available_time"] = "每周 10-15 小时"
    completed_profile["confirmed_info"]["constraints"] = "需要平衡学校课程"
    completed_profile["text"] = "用户为软件工程专业大三学生，目标明确指向 Agent 开发与 Vibe Coding 学习。"
    llm = ScriptedStructuredLlm([completed_profile])
    state = {
        "user_id": "00000000-0000-0000-0000-000000000024",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    confirmed = result["profile"]["confirmed_info"]
    assert llm.calls == 0
    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "learning_preference"
    assert confirmed["current_grade"] == "大三"
    assert confirmed["major"] == "软件工程"
    assert confirmed["short_term_goal"] == "学习agent开发vibe coding"
    assert confirmed["learning_stage"] == ""
    assert confirmed["has_clear_goal"] == ""
    assert confirmed["knowledge_foundation"] == ""
    assert confirmed["weekly_available_time"] == ""
    assert result["profile"]["defaulted_fields"] == []
    assert result["profile"]["question_box"]["question"] == "你目前的学习阶段是？"


def test_run_profile_agent_maps_major_before_grade_in_delimited_profile(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-delimited-major-before-grade.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = "软件工程、大三、找工作、喜欢自己摸索，学习vibecoding"
    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "learning_preference",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "喜欢自己摸索",
            "learning_pace_preference": "",
            "content_preference": [],
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
        "question_md": "你目前的学习阶段是？",
        "question_box": {"question": "你目前的学习阶段是？", "options": []},
        "text": "你目前的学习阶段是？",
    }])
    state = {
        "user_id": "00000000-0000-0000-0000-000000000005",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    confirmed = result["profile"]["confirmed_info"]
    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["question_mode"] == "question_box"
    assert confirmed["current_grade"] == "大三"
    assert confirmed["major"] == "软件工程"
    assert confirmed["short_term_goal"] == "找工作，学习vibecoding"
    assert confirmed["learning_method_preference"] == "喜欢自己摸索"
    assert result["profile"]["question_box"]["question"] == "你目前的学习阶段是？"


def test_run_profile_agent_collecting_profile_understands_english_grade_without_corrupting_major(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-english-grade.db'}")
    set_engine(engine)
    init_db(engine)

    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "大三",
            "major": "",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": [],
            "need_guidance": "",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "为了生成基础画像，请先告诉我你的专业。",
        "question_box": {"question": "为了生成基础画像，请先告诉我你的专业。", "options": []},
        "text": "为了生成基础画像，请先告诉我你的专业。",
    }])
    state = {
        "user_id": "00000000-0000-0000-0000-000000000018",
        "query": (
            "I am a third-year software engineering student. "
            "I want to study AI application architecture and build a local knowledge-base QA demo."
        ),
        "messages": [
            HumanMessage(content="开始学习这门课"),
            HumanMessage(
                content=(
                    "I am a third-year software engineering student. "
                    "I want to study AI application architecture and build a local knowledge-base QA demo."
                )
            ),
        ],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == ""
    assert "请先告诉我你的专业" in result["response"]


def test_run_profile_agent_does_not_treat_learning_preference_sentence_as_major(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-learning-preference-not-major.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = "我现在大三、准备学习agent开发和vibecoding、我喜欢看文档，一步一步跟着操作"
    llm = ScriptedStructuredLlm([{
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "current_grade": "大三",
            "major": "",
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": ["文档"],
            "need_guidance": "需要强引导",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "学习vibecoding",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "为了生成基础画像，请先告诉我你的专业。",
        "question_box": {
            "question": "为了生成基础画像，请先告诉我你的专业。",
            "options": [
                {"label": "软件工程", "value": "软件工程", "description": "", "target_fields": ["major"], "fills": {"major": "软件工程"}},
                {"label": "其他", "value": "__free_text__", "description": "", "target_fields": [], "fills": {}},
            ],
        },
        "text": "为了生成基础画像，请先告诉我你的专业。",
    }])
    state = {
        "user_id": "00000000-0000-0000-0000-000000000021",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "basic_info"
    assert result["profile"]["question_mode"] == "question_box"
    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == ""
    assert result["profile"]["confirmed_info"]["content_preference"] == ["文档"]
    assert result["profile"]["confirmed_info"]["need_guidance"] == "需要强引导"
    assert result["profile"]["question_box"]["question"] == "为了生成基础画像，请先告诉我你的专业。"
    assert result["profile"]["question_box"]["options"]
    assert result["response"] == result["profile"]["text"]
    assert "请先告诉我你的专业" in result["response"]


def test_run_profile_agent_uses_structured_llm_for_rich_first_profile_message(tmp_path: Path) -> None:
    class RecordingLlm:
        def __init__(self) -> None:
            self.calls = 0

        def with_structured_output(self, *_args, **_kwargs):
            async def invoke(_messages):
                self.calls += 1
                profile = _profile()
                profile["confirmed_info"]["learning_stage"] = "项目实践"
                profile["confirmed_info"]["learning_method_preference"] = "项目驱动"
                profile["confirmed_info"]["learning_pace_preference"] = "周末集中推进"
                profile["confirmed_info"]["content_preference"] = ["实践型内容"]
                profile["confirmed_info"]["need_guidance"] = "需要一定指导"
                profile["confirmed_info"]["knowledge_foundation"] = "Python、前后端基础和一些 LLM API 接入经验"
                profile["confirmed_info"]["strengths"] = "执行力强"
                profile["confirmed_info"]["weaknesses"] = "部署经验不足和工程稳定性经验不足"
                profile["confirmed_info"]["experience"] = "做过课程项目"
                profile["confirmed_info"]["short_term_goal"] = "完成一个 AI Agent 项目并上线可演示功能"
                profile["confirmed_info"]["long_term_goal"] = "成为 AI 应用开发者"
                profile["confirmed_info"]["weekly_available_time"] = "每周 8 小时"
                profile["confirmed_info"]["constraints"] = "平时课程比较满，只能周末集中学习"
                profile["text"] = "【基础学习画像总结】大三软件工程，当前以 AI Agent 项目实践为主线。"
                profile["summary_text"] = profile["text"]
                return ProfileOutput(**profile)

            return invoke

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-rich-first-message.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = (
        "我是软件工程专业的大三学生。"
        "我现在的学习阶段是项目实践。"
        "我的目标比较明确，短期目标是完成一个 AI Agent 项目并真正上线一个可演示功能，"
        "长期目标是成为 AI 应用开发者。"
        "我的学习方法偏项目驱动，喜欢从真实需求出发边做边学。"
        "学习节奏希望周末集中推进，每周大概能投入 8 小时。"
        "我更偏好实践型内容。"
        "我需要一定的指导和拆解。"
        "我的知识基础是 Python、前后端基础和一些 LLM API 接入经验。"
        "我做过课程项目，优势是执行力强，弱点是部署经验不足和工程稳定性经验不足。"
        "平时课程比较满，所以主要限制是只能在周末集中学习。"
        "请先生成我的基础画像。"
    )
    llm = RecordingLlm()
    state = {
        "user_id": "00000000-0000-0000-0000-000000000017",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert llm.calls == 1
    confirmed = result["profile"]["confirmed_info"]
    assert confirmed["current_grade"] == "大三"
    assert confirmed["major"] == "软件工程"
    assert confirmed["learning_stage"] == "项目实践"
    assert confirmed["learning_method_preference"] == "项目驱动"
    assert confirmed["weekly_available_time"] == "每周 8 小时"
    assert confirmed["constraints"] == "平时课程比较满，只能周末集中学习"
    assert result["response"] == result["profile"]["text"]

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["confirmed_info"]["major"] == "软件工程"


def test_run_profile_agent_converts_unknown_values_to_collecting(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-unknown-values.db'}")
    set_engine(engine)
    init_db(engine)

    existing_profile = _profile()
    existing_profile["type"] = "collecting"
    existing_profile["stage"] = "basic_info"
    existing_profile["confirmed_info"]["knowledge_foundation"] = ""
    existing_profile["confirmed_info"]["long_term_goal"] = ""
    existing_profile["confirmed_info"]["weekly_available_time"] = ""

    state = {
        "user_id": "00000000-0000-0000-0000-000000000019",
        "query": "和我讨论重新生成个人画像",
        "profile": existing_profile,
        "messages": [HumanMessage(content="和我讨论重新生成个人画像")],
    }

    llm = ScriptedStructuredLlm([
        {
            **_profile(),
            "confirmed_info": {
                **_profile()["confirmed_info"],
                "knowledge_foundation": "未知",
                "long_term_goal": "未知",
                "weekly_available_time": "未知",
            },
        },
        {
            "type": "collecting",
            "stage": "ability_basis",
            "question_mode": "question_box",
            "confirmed_info": {
                **existing_profile["confirmed_info"],
                "current_grade": "大三",
                "major": "软件工程",
            },
            "defaulted_fields": [],
            "question_md": "你目前的知识基础是什么？",
            "question_box": {
                "question": "你目前的知识基础是什么？",
                "options": [
                    {"label": "有前后端基础", "value": "有前后端基础", "description": "了解 Web 开发基本流程", "target_fields": ["knowledge_foundation"], "fills": {"knowledge_foundation": "有前后端基础"}},
                    {"label": "其他", "value": "__free_text__", "description": "以上都不符合，我来输入", "target_fields": [], "fills": {}},
                ],
            },
            "text": "你目前的知识基础是什么？",
        },
    ])

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["question_mode"] == "question_box"
    assert result["profile"]["confirmed_info"]["knowledge_foundation"] == ""
    assert result["profile"]["confirmed_info"]["long_term_goal"] == ""
    assert result["profile"]["confirmed_info"]["weekly_available_time"] == ""
    assert "未知" not in result["response"]
    assert result["profile"]["question_box"]["options"]

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["type"] == "collecting"


def test_run_profile_agent_converts_empty_llm_values_to_collecting(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-empty-values.db'}")
    set_engine(engine)
    init_db(engine)

    existing_profile = _profile()
    existing_profile["type"] = "collecting"
    existing_profile["confirmed_info"]["knowledge_foundation"] = ""
    existing_profile["confirmed_info"]["long_term_goal"] = ""
    existing_profile["confirmed_info"]["weekly_available_time"] = ""

    state = {
        "user_id": "00000000-0000-0000-0000-000000000020",
        "query": "和我讨论重新生成个人画像",
        "profile": existing_profile,
        "messages": [HumanMessage(content="和我讨论重新生成个人画像")],
    }

    llm = ScriptedStructuredLlm([
        {
            **_profile(),
            "confirmed_info": {
                **_profile()["confirmed_info"],
                "knowledge_foundation": "",
                "long_term_goal": "",
                "weekly_available_time": "",
                "content_preference": [],
            },
        },
        {
            "type": "collecting",
            "stage": "learning_preference",
            "question_mode": "question_box",
            "confirmed_info": {
                **existing_profile["confirmed_info"],
                "current_grade": "大三",
                "major": "软件工程",
            },
            "defaulted_fields": [],
            "question_md": "你偏好什么内容形式？",
            "question_box": {
                "question": "你偏好什么内容形式？",
                "options": [
                    {"label": "文档为主", "value": "文档", "description": "喜欢阅读文档学习", "target_fields": ["content_preference"], "fills": {"content_preference": ["文档"]}},
                    {"label": "其他", "value": "__free_text__", "description": "以上都不符合，我来输入", "target_fields": [], "fills": {}},
                ],
            },
            "text": "你偏好什么内容形式？",
        },
    ])

    result = asyncio.run(run_profile_agent(state, llm))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["question_mode"] == "question_box"
    assert result["profile"]["confirmed_info"]["knowledge_foundation"] == ""
    assert result["profile"]["confirmed_info"]["long_term_goal"] == ""
    assert result["profile"]["confirmed_info"]["weekly_available_time"] == ""
    assert result["profile"]["question_box"]["options"]


def test_run_profile_agent_repairs_stage_type_mismatch_before_persisting(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'profile-repair-stage-type.db'}")
    set_engine(engine)
    init_db(engine)

    broken_profile = {
        **_profile(),
        "type": "collecting",
        "stage": "generated",
        "text": "",
        "question_md": "",
        "question_box": {"question": "", "options": []},
    }
    repaired_profile = {
        "type": "collecting",
        "stage": "learning_preference",
        "question_mode": "question_box",
        "confirmed_info": {
            **_profile()["confirmed_info"],
            "learning_stage": "",
            "has_clear_goal": "",
            "learning_method_preference": "",
            "learning_pace_preference": "",
            "content_preference": [],
            "need_guidance": "",
            "knowledge_foundation": "",
            "strengths": "",
            "weaknesses": "",
            "experience": "",
            "short_term_goal": "",
            "long_term_goal": "",
            "weekly_available_time": "",
            "constraints": "",
        },
        "defaulted_fields": [],
        "question_md": "你目前的学习阶段是？",
        "question_box": {"question": "你目前的学习阶段是？", "options": []},
        "text": "你目前的学习阶段是？",
    }
    llm = ScriptedStructuredLlm([broken_profile, repaired_profile])

    state = {
        "user_id": "00000000-0000-0000-0000-000000000023",
        "query": "我现在大三，软件工程，想继续完善基础画像",
        "messages": [HumanMessage(content="我现在大三，软件工程，想继续完善基础画像")],
    }

    result = asyncio.run(run_profile_agent(state, llm))

    assert llm.calls == 2
    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "learning_preference"
    assert result["profile"]["question_box"]["question"] == "你目前的学习阶段是？"
