from __future__ import annotations

import asyncio
from pathlib import Path

from langchain_core.messages import HumanMessage
from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.orchestration.agents.learning_path_intake import (
    is_intake_confirmation_query,
    is_intake_modification_query,
    latest_intake_from_state,
    run_learning_path_intake_agent,
)
from app.orchestration.agents.prompts import LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
from app.services.conversation_session_service import load_or_create_session, latest_learning_path_intake


def _profile() -> dict:
    return {
        "type": "basic_profile",
        "stage": "generated",
        "confirmed_info": {
            "current_grade": "大三",
            "major": "软件工程",
            "learning_stage": "刚入门",
            "has_clear_goal": "否",
            "learning_method_preference": "项目驱动学习",
            "learning_pace_preference": "每天少量",
            "content_preference": ["文档"],
            "need_guidance": "需要强引导",
            "knowledge_foundation": "没有基础",
            "strengths": "没有",
            "weaknesses": "缺少系统训练",
            "experience": "没有经验",
            "short_term_goal": "学习数据结构",
            "long_term_goal": "逐步形成数据结构方向的系统学习能力",
            "weekly_available_time": "每周 6-10 小时",
            "constraints": "平时学习节奏，避免过高强度",
        },
        "summary_text": "【基础学习画像总结】大三软件工程，目标是学习数据结构。",
    }


def test_intake_confirmation_query_accepts_natural_language() -> None:
    assert is_intake_confirmation_query("可以")
    assert is_intake_confirmation_query("就按这个来")
    assert is_intake_confirmation_query("听你的，可以开始")
    assert not is_intake_confirmation_query("第二门课换成算法")


def test_intake_modification_query_accepts_course_change() -> None:
    assert is_intake_modification_query("第二门课换成算法")
    assert is_intake_modification_query("我想学前端")
    assert is_intake_modification_query("不想学这个")
    assert not is_intake_modification_query("就按这个来")


def test_intake_prompt_allows_required_statuses() -> None:
    assert "`draft`" in LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
    assert "`confirmed`" in LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
    assert "`risk_pending`" in LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT


def test_run_intake_agent_creates_data_structure_draft(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-draft.db'}")
    set_engine(engine)
    init_db(engine)

    with Session(engine) as session:
        load_or_create_session(session, "session-intake-draft", "user-1")

    result = asyncio.run(run_learning_path_intake_agent({
        "user_id": "user-1",
        "session_id": "session-intake-draft",
        "query": "请根据我的基础画像生成学习路径。",
        "profile": _profile(),
        "messages": [HumanMessage(content="我现在大三、软件工程、想学习数据结构、目前不知道怎么学")],
    }, object()))

    intake = result["learning_path_intake"]
    assert intake["type"] == "learning_path_intake"
    assert intake["status"] == "draft"
    assert intake["grade_year"] == "year_3"
    assert intake["learning_topic"] == "数据结构"
    assert 4 <= len(intake["courses"]) <= 10
    assert "AI 应用开发" not in result["response"]
    assert "LangChain" not in result["response"]

    with Session(engine) as session:
        row = load_or_create_session(session, "session-intake-draft", "user-1")
        stored = latest_learning_path_intake(row.messages)

    assert stored == intake


def test_run_intake_agent_marks_existing_draft_confirmed(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'intake-confirm.db'}")
    set_engine(engine)
    init_db(engine)

    draft = {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": "year_3",
        "grade_name": "大三",
        "learning_topic": "数据结构",
        "courses": [
            {"title": "数据结构入门与复杂度基础", "purpose": "建立基础"},
            {"title": "线性结构实践", "purpose": "练习线性结构"},
            {"title": "树与递归基础", "purpose": "理解递归结构"},
            {"title": "图与综合项目", "purpose": "完成综合应用"},
        ],
        "recommendation_reasons": ["目标是学习数据结构"],
        "user_modification_summary": "",
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }
    state = {
        "user_id": "user-1",
        "session_id": "session-intake-confirm",
        "query": "就按这个来",
        "profile": _profile(),
        "learning_path_intake": draft,
        "messages": [],
    }

    result = asyncio.run(run_learning_path_intake_agent(state, object()))
    assert result["learning_path_intake"]["status"] == "confirmed"
    assert result["response"].startswith("好的")
    assert latest_intake_from_state(result)["status"] == "confirmed"
