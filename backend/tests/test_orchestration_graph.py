from __future__ import annotations

import asyncio

from app.orchestration.dify_client import DifyResponse
from app.orchestration.graph import create_orchestration_graph
from app.orchestration.state import OrchestrationState


class FakeDifyClient:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    async def chat_blocking(self, query: str, user_id: str, conversation_id: str = "") -> DifyResponse:
        self.calls.append((query, conversation_id))
        answer = self.answers.pop(0)
        return DifyResponse(
            answer=answer,
            conversation_id=conversation_id or "conv-1",
            task_id="task-1",
            message_id="msg-1",
            raw={"answer": answer, "conversation_id": conversation_id or "conv-1"},
        )


def make_state(query: str = "我想完善基础画像") -> OrchestrationState:
    return {
        "query": query,
        "user_id": "user-1",
        "conversation_id": "",
        "intent_conversation_id": "",
        "intent_raw": {},
        "intent": "",
        "route_status": "",
        "dify_raw": {},
        "answer_json": {},
        "phase": "collecting",
        "error": "",
    }


def test_graph_routes_profile_intent_to_profile_agent() -> None:
    intent = FakeDifyClient(["profile_agent"])
    profile = FakeDifyClient(
        [
            (
                '{"type":"collecting","stage":"basic_info","question_mode":"question_md",'
                '"confirmed_info":{},"defaulted_fields":[],"question_md":"请介绍",'
                '"question_box":{"question":"","options":[]},"text":"请介绍"}'
            )
        ]
    )
    graph = create_orchestration_graph(profile_client=profile, intent_client=intent)

    result = asyncio.run(graph.ainvoke(make_state(), {"configurable": {"thread_id": "graph-test-1"}}))

    assert result["intent"] == "profile_agent"
    assert result["route_status"] == "supported"
    assert result["intent_conversation_id"] == "conv-1"
    assert result["phase"] == "collecting"
    assert result["conversation_id"] == "conv-1"
    assert result["answer_json"]["type"] == "collecting"
    assert len(profile.calls) == 1


def test_graph_hides_unsupported_routes() -> None:
    intent = FakeDifyClient(["learning_path_agent"])
    profile = FakeDifyClient([])
    graph = create_orchestration_graph(profile_client=profile, intent_client=intent)

    result = asyncio.run(
        graph.ainvoke(make_state("帮我规划学习路径"), {"configurable": {"thread_id": "graph-test-2"}})
    )

    assert result["intent"] == "learning_path_agent"
    assert result["intent_conversation_id"] == "conv-1"
    assert result["route_status"] == "unsupported"
    assert result["phase"] == "unsupported"
    assert "基础画像" in result["error"]
    assert profile.calls == []


def test_graph_keeps_active_profile_conversation_after_intent_check() -> None:
    intent = FakeDifyClient(["chat"])
    profile = FakeDifyClient(
        [
            (
                '{"type":"collecting","stage":"ability_basis","question_mode":"question_md",'
                '"confirmed_info":{},"defaulted_fields":[],"question_md":"继续",'
                '"question_box":{"question":"","options":[]},"text":"继续"}'
            )
        ]
    )
    graph = create_orchestration_graph(profile_client=profile, intent_client=intent)
    state = make_state("我有编程基础")
    state["conversation_id"] = "conv-existing"
    state["intent_conversation_id"] = "intent-existing"

    result = asyncio.run(graph.ainvoke(state, {"configurable": {"thread_id": "graph-test-3"}}))

    assert result["intent"] == "chat"
    assert result["intent_conversation_id"] == "intent-existing"
    assert result["route_status"] == "supported"
    assert result["phase"] == "collecting"
    assert profile.calls == [("我有编程基础", "conv-existing")]
    assert intent.calls == [("我有编程基础", "intent-existing")]
