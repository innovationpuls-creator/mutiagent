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
from app.orchestration.rule_engine import AGENT_LEARNING_PATH, AGENT_PROFILE, evaluate


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
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local default profile path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-fast-path.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "query": "你直接按照默认给我一份基础画像",
        "messages": [HumanMessage(content="大3，软件工程，ai，平时学习")],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["type"] == "basic_profile"
    assert result["profile"]["stage"] == "generated"
    assert result["profile"]["defaulted_fields"]
    assert result["response"] == result["profile"]["text"]
    assert result["profile"]["confirmed_info"]["current_grade"] == "大3"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["type"] == "basic_profile"
    assert row.profile_data["confirmed_info"]["current_grade"] == "大3"


def test_run_profile_agent_default_profile_ignores_greeting_as_major(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local default profile path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-ignore-greeting.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "query": "你直接按照默认给我一份基础画像",
        "messages": [HumanMessage(content="你好")],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert "你好" not in result["profile"]["summary_text"]


def test_run_profile_agent_keeps_pace_segment_out_of_major(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-major-pace.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000009",
        "query": "大四，计算机科学，AI，周末集中",
        "profile": _profile(),
        "messages": [HumanMessage(content="大四，计算机科学，AI，周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大四"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"


def test_run_profile_agent_returns_collecting_for_unsupported_postgraduate_grade(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-unsupported-grade.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000015",
        "query": "研一，软件工程，AI，周末集中",
        "messages": [HumanMessage(content="研一，软件工程，AI，周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

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
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-explicit-major.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000010",
        "query": "专业改成计算机科学",
        "profile": _profile(),
        "messages": [HumanMessage(content="专业改成计算机科学")],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert "专业改成计算机科学" not in result["profile"]["summary_text"]


def test_run_profile_agent_rewrites_system_generated_knowledge_foundation_after_major_update(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

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

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert (
        result["profile"]["confirmed_info"]["knowledge_foundation"]
        == "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    )


def test_run_profile_agent_restores_generated_knowledge_foundation_when_existing_complete_profile_field_is_empty(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

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

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"
    assert (
        result["profile"]["confirmed_info"]["knowledge_foundation"]
        == "已具备计算机科学基础，AI 应用开发方向可从入门到基础逐步补全"
    )


def test_run_profile_agent_updates_multiple_explicit_fields_in_one_sentence(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-explicit-multi-field.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000011",
        "query": "专业改成计算机科学，当前限制改成周末集中",
        "profile": _profile(),
        "messages": [HumanMessage(content="专业改成计算机科学，当前限制改成周末集中")],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"
    assert "当前限制改成周末集中" not in result["profile"]["summary_text"]


def test_run_profile_agent_prefers_latest_explicit_profile_update_from_history(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

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

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["major"] == "人工智能"
    assert result["profile"]["confirmed_info"]["constraints"] == "每天少量"
    assert (
        result["profile"]["confirmed_info"]["knowledge_foundation"]
        == "已具备人工智能基础，AI 应用开发方向可从入门到基础逐步补全"
    )


def test_run_profile_agent_prefers_latest_implicit_grade_and_major_from_history(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile update path should not call structured llm")

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

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["confirmed_info"]["current_grade"] == "大四"
    assert result["profile"]["confirmed_info"]["major"] == "计算机科学"
    assert result["profile"]["confirmed_info"]["constraints"] == "周末集中"


def test_run_profile_agent_first_profile_requests_missing_major_in_collecting_mode(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("collecting fallback should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-first-signal.db'}")
    set_engine(engine)
    init_db(engine)

    state = {
        "user_id": "00000000-0000-0000-0000-000000000002",
        "query": "我现在大三，你看看我的个人画像，你推荐什么？",
        "messages": [
            HumanMessage(content="你好"),
            HumanMessage(content="我现在大三，你看看我的个人画像，你推荐什么？"),
        ],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["type"] == "collecting"
    assert result["profile"]["stage"] == "basic_info"
    assert result["profile"]["question_mode"] == "question_md"
    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == ""
    assert "请先告诉我你的专业" in result["response"]
    assert result["response"] == result["profile"]["text"]

    with Session(engine) as session:
        row = session.get(UserProfile, state["user_id"])

    assert row is not None
    assert row.profile_data["type"] == "collecting"
    assert row.profile_data["confirmed_info"]["current_grade"] == "大三"


def test_run_profile_agent_uses_existing_collecting_profile_to_finish_basic_profile(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local follow-up profile completion should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-follow-up.db'}")
    set_engine(engine)
    init_db(engine)

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

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    assert result["profile"]["type"] == "basic_profile"
    assert result["profile"]["stage"] == "generated"
    assert result["profile"]["confirmed_info"]["current_grade"] == "大三"
    assert result["profile"]["confirmed_info"]["major"] == "软件工程"
    assert result["response"] == result["profile"]["text"]


def test_run_profile_agent_maps_user_delimited_profile_without_fake_fields(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-delimited-real-input.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = "大三、软件工程、找工作、喜欢自己摸索，学习vibecoding"
    state = {
        "user_id": "00000000-0000-0000-0000-000000000004",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    confirmed = result["profile"]["confirmed_info"]
    assert result["profile"]["type"] == "basic_profile"
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
    assert "喜欢自己摸索" not in result["profile"]["summary_text"].split("软件工程", 1)[0]


def test_run_profile_agent_maps_major_before_grade_in_delimited_profile(tmp_path: Path) -> None:
    class ExplodingLlm:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("local profile path should not call structured llm")

    engine = build_engine(f"sqlite:///{tmp_path / 'profile-delimited-major-before-grade.db'}")
    set_engine(engine)
    init_db(engine)

    user_text = "软件工程、大三、找工作、喜欢自己摸索，学习vibecoding"
    state = {
        "user_id": "00000000-0000-0000-0000-000000000005",
        "query": user_text,
        "messages": [HumanMessage(content=user_text)],
    }

    result = asyncio.run(run_profile_agent(state, ExplodingLlm()))

    confirmed = result["profile"]["confirmed_info"]
    assert result["profile"]["type"] == "basic_profile"
    assert confirmed["current_grade"] == "大三"
    assert confirmed["major"] == "软件工程"
    assert confirmed["short_term_goal"] == "找工作，学习vibecoding"
    assert confirmed["learning_method_preference"] == "喜欢自己摸索"
