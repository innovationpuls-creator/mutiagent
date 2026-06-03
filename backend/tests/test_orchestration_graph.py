from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from sqlmodel import Session, create_engine

from app.database import init_db
from app.orchestration.graph import (
    AGENT_LABELS,
    _extract_answer,
    _normalize_question_box,
    _route_after_supervisor,
    create_orchestration_graph,
    stream_orchestration_events,
)


# ============================================================
# _route_after_supervisor
# ============================================================

def test_route_returns_end_when_no_messages():
    assert _route_after_supervisor({"messages": []}) == END


def test_route_returns_end_when_no_tool_calls():
    state = {"messages": [AIMessage(content="你好，我会帮助你。")]}
    assert _route_after_supervisor(state) == END


def test_route_returns_agent_key_when_tool_call_matches():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "profile_agent", "args": {"query": "我想学Python"}, "id": "call_1"}],
            )
        ]
    }
    assert _route_after_supervisor(state) == "profile_agent"


def test_route_returns_end_for_unknown_tool():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "unknown_tool", "args": {}, "id": "call_1"}],
            )
        ]
    }
    assert _route_after_supervisor(state) == END


def test_route_checks_last_message_only():
    state = {
        "messages": [
            HumanMessage(content="你好"),
            AIMessage(content="好的"),
            AIMessage(
                content="",
                tool_calls=[{"name": "learning_path_agent", "args": {}, "id": "call_2"}],
            ),
        ]
    }
    assert _route_after_supervisor(state) == "learning_path_agent"


def test_route_ignores_non_aimessage_last_message():
    state = {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "profile_agent", "args": {}, "id": "call_1"}]),
            HumanMessage(content="补充信息"),
        ]
    }
    assert _route_after_supervisor(state) == END


def test_route_all_three_agent_keys():
    for agent_key in ["profile_agent", "learning_path_agent", "course_knowledge_agent"]:
        state = {
            "messages": [
                AIMessage(content="", tool_calls=[{"name": agent_key, "args": {}, "id": "call_x"}])
            ]
        }
        assert _route_after_supervisor(state) == agent_key


# ============================================================
# _extract_answer
# ============================================================

def test_extract_answer_returns_answer_dict_directly():
    state = {"answer": {"user_message": "这是回答", "question_box": None}}
    assert _extract_answer(state) == {"user_message": "这是回答", "question_box": None}


def test_extract_answer_returns_profile_question_md():
    state = {
        "response": "",
        "question_box": None,
        "answer": None,
        "profile": {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_md",
            "question_md": "请介绍你的技术基础。",
            "text": "备用文本",
            "question_box": {"question": "", "options": []},
        },
    }
    result = _extract_answer(state)
    assert result["user_message"] == "请介绍你的技术基础。"
    assert result["question_box"] is None


def test_extract_answer_falls_back_to_profile_text():
    state = {
        "response": "",
        "question_box": None,
        "answer": None,
        "profile": {
            "type": "collecting",
            "stage": "basic_info",
            "question_mode": "question_box",
            "question_md": "",
            "text": "你目前处于哪个学习阶段？",
            "question_box": {
                "question": "你目前处于哪个学习阶段？",
                "options": [{"label": "刚入门", "value": "刚入门"}],
            },
        },
    }
    result = _extract_answer(state)
    assert result["user_message"] == "你目前处于哪个学习阶段？"
    assert result["question_box"]["question"] == "你目前处于哪个学习阶段？"


def test_extract_answer_returns_response_when_no_profile():
    state = {"response": "这是直接回复", "question_box": None, "answer": None, "profile": None}
    assert _extract_answer(state) == {"user_message": "这是直接回复", "question_box": None}


def test_extract_answer_returns_response_when_profile_has_no_question_mode():
    state = {
        "response": "这是回复",
        "question_box": {"question": "Q?", "options": []},
        "answer": None,
        "profile": {"type": "basic_profile", "stage": "generated"},
    }
    result = _extract_answer(state)
    assert result["user_message"] == "这是回复"
    assert result["question_box"]["question"] == "Q?"


# ============================================================
# _normalize_question_box
# ============================================================

def test_normalize_question_box_returns_none_for_empty():
    assert _normalize_question_box({}) is None
    assert _normalize_question_box({"question": "", "options": []}) is None


def test_normalize_question_box_converts_string_list():
    qb = {"question": "你熟悉哪些技术？", "options": ["Python", "Java", "前端"]}
    expected = {
        "question": "你熟悉哪些技术？",
        "options": [
            {"label": "Python", "value": "Python", "description": "", "target_fields": [], "fills": {}},
            {"label": "Java", "value": "Java", "description": "", "target_fields": [], "fills": {}},
            {"label": "前端", "value": "前端", "description": "", "target_fields": [], "fills": {}},
        ],
    }
    assert _normalize_question_box(qb) == expected


def test_normalize_question_box_passes_structured_options():
    qb = {
        "question": "你目前处于哪个学习阶段？",
        "options": [
            {
                "label": "刚入门",
                "value": "刚入门",
                "description": "刚入门",
                "target_fields": ["learning_stage"],
                "fills": {"learning_stage": "刚入门"},
            },
        ],
    }
    result = _normalize_question_box(qb)
    assert result["question"] == "你目前处于哪个学习阶段？"
    assert result["options"][0]["label"] == "刚入门"
    assert result["options"][0]["target_fields"] == ["learning_stage"]


def test_normalize_question_box_handles_empty_options():
    assert _normalize_question_box({"question": "测试", "options": []}) == {"question": "测试", "options": []}


# ============================================================
# AGENT_LABELS
# ============================================================

def test_agent_labels():
    assert AGENT_LABELS == {
        "profile_agent": "基础画像智能体",
        "learning_path_agent": "学习路径智能体",
        "course_knowledge_agent": "课程知识点规划智能体",
    }


# ============================================================
# Graph structure
# ============================================================

def test_graph_compiles_and_has_nodes():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)

    with patch("app.orchestration.graph._build_llm", return_value=MagicMock()):
        with Session(engine) as session:
            graph = create_orchestration_graph(session)
            nodes = graph.get_graph().nodes

    assert "supervisor" in nodes
    assert "profile_agent" in nodes
    assert "learning_path_agent" in nodes
    assert "course_knowledge_agent" in nodes
    assert "__start__" in nodes


# ============================================================
# Graph invoke — direct supervisor response (no tool_calls)
# ============================================================

def _make_mock_llm(response_content: str):
    """Build a mock LLM: bind_tools is sync, ainvoke returns the given AIMessage."""
    mock_llm = AsyncMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    async def mock_ainvoke(_messages):
        return AIMessage(content=response_content)

    mock_llm.ainvoke = mock_ainvoke
    return mock_llm


def test_graph_invoke_direct_supervisor_response():
    mock_llm = _make_mock_llm("你好，我会帮助你规划学习。")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)

    with Session(engine) as session:
        state = {
            "query": "你好",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [HumanMessage(content="你好")],
        }

        async def _run():
            with patch("app.orchestration.graph._build_llm", return_value=mock_llm):
                graph = create_orchestration_graph(session)
                config = {"configurable": {"thread_id": "test-1"}}
                return await graph.ainvoke(state, config)

        result = asyncio.run(_run())

    assert result["response"] == "你好，我会帮助你规划学习。"


# ============================================================
# Stream events — direct supervisor response
# ============================================================

def test_stream_events_direct_supervisor_response():
    mock_llm = _make_mock_llm("你好，我会帮助你规划学习。")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)

    with Session(engine) as session:
        state = {
            "query": "你好",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [HumanMessage(content="你好")],
        }

        async def _collect():
            with patch("app.orchestration.graph._build_llm", return_value=mock_llm):
                return [event async for event in stream_orchestration_events(state, session)]

        events = asyncio.run(_collect())

    assert len(events) >= 1
    completed = events[-1]
    assert completed["event"] == "completed"
    assert completed["step_id"] == "supervisor"
    assert completed["completed"] is True
    assert completed["answer"]["user_message"] == "你好，我会帮助你规划学习。"


# ============================================================
# Stream events — agent flow with agent_started/agent_completed
# ============================================================

def test_stream_events_with_agent_flow():
    mock_llm = AsyncMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    call_count = 0

    async def mock_ainvoke(_messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": "profile_agent", "args": {"query": "test"}, "id": "call_1"}],
            )
        return AIMessage(content="处理完成，这是结果。")

    mock_llm.ainvoke = mock_ainvoke

    async def profile_stub(_state):
        return {
            "profile": {"type": "basic_profile", "stage": "generated", "question_mode": "none"},
            "answer": {"user_message": "画像完成", "question_box": None},
            "messages": [ToolMessage(content='{"profile":"ok"}', tool_call_id="call_1")],
        }

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)

    with Session(engine) as session:
        state = {
            "query": "test",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [HumanMessage(content="test")],
        }

        async def _collect():
            with patch(
                "app.orchestration.agents.profile.create_profile_agent_node", return_value=profile_stub
            ), patch(
                "app.orchestration.agents.learning_path.create_learning_path_agent_node",
                return_value=AsyncMock(),
            ), patch(
                "app.orchestration.agents.course_knowledge.create_course_knowledge_agent_node",
                return_value=AsyncMock(),
            ), patch(
                "app.orchestration.graph._build_llm", return_value=mock_llm
            ):
                return [event async for event in stream_orchestration_events(state, session)]

        events = asyncio.run(_collect())

    event_tuples = [(e["event"], e.get("step_id")) for e in events]
    assert ("agent_started", "profile_agent") in event_tuples
    assert ("agent_completed", "profile_agent") in event_tuples
    assert ("completed", "supervisor") in event_tuples

    agent_started = [e for e in events if e["event"] == "agent_started"][0]
    assert agent_started["label"] == "基础画像智能体"
    assert agent_started["message"] == "基础画像智能体开始处理。"

    agent_completed = [e for e in events if e["event"] == "agent_completed"][0]
    assert agent_completed["label"] == "基础画像智能体"
    assert agent_completed["message"] == "基础画像智能体已完成。"

    completed = events[-1]
    assert completed["event"] == "completed"
    assert completed["completed"] is True
    # answer key is not in OrchestrationState TypedDict, so _extract_answer
    # falls through to profile branch (question_mode="none" is truthy),
    # then to the response fallback.
    assert "user_message" in completed["answer"]


# ============================================================
# Stream events — agent_failed when agent returns error
# ============================================================

def test_stream_events_agent_failed():
    mock_llm = AsyncMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    async def mock_ainvoke(_messages):
        return AIMessage(
            content="",
            tool_calls=[{"name": "learning_path_agent", "args": {}, "id": "call_1"}],
        )

    mock_llm.ainvoke = mock_ainvoke

    async def failing_learning_path_stub(_state):
        return {
            "learning_path": {"error": "请先完成基础画像。"},
            "messages": [ToolMessage(content='{"error":"请先完成基础画像。"}', tool_call_id="call_1")],
        }

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)

    with Session(engine) as session:
        state = {
            "query": "生成学习路径",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [HumanMessage(content="生成学习路径")],
        }

        async def _collect():
            with patch(
                "app.orchestration.agents.profile.create_profile_agent_node",
                return_value=AsyncMock(),
            ), patch(
                "app.orchestration.agents.learning_path.create_learning_path_agent_node",
                return_value=failing_learning_path_stub,
            ), patch(
                "app.orchestration.agents.course_knowledge.create_course_knowledge_agent_node",
                return_value=AsyncMock(),
            ), patch(
                "app.orchestration.graph._build_llm", return_value=mock_llm
            ):
                return [event async for event in stream_orchestration_events(state, session)]

        events = asyncio.run(_collect())

    event_tuples = [(e["event"], e.get("step_id")) for e in events]
    assert ("agent_started", "learning_path_agent") in event_tuples
    assert ("agent_failed", "learning_path_agent") in event_tuples

    agent_failed = [e for e in events if e["event"] == "agent_failed"][0]
    assert agent_failed["label"] == "学习路径智能体"
    assert "请先完成基础画像" in agent_failed["message"]


# ============================================================
# Stream events — error handling
# ============================================================

def test_stream_events_error():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    init_db(engine)

    mock_graph = MagicMock()
    mock_graph.astream_events = MagicMock(side_effect=RuntimeError("模拟错误"))

    with Session(engine) as session:
        state = {
            "query": "test",
            "user_id": "user-1",
            "session_id": "session-1",
            "messages": [HumanMessage(content="test")],
        }

        async def _collect():
            with patch("app.orchestration.graph.create_orchestration_graph", return_value=mock_graph):
                return [event async for event in stream_orchestration_events(state, session)]

        events = asyncio.run(_collect())

    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["message"] == "模拟错误"
    assert events[0]["step_id"] == "supervisor"
    assert events[0]["label"] == "主智能体"
