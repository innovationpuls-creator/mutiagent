from __future__ import annotations

import asyncio

from app.orchestration.dify_client import DifyResponse
from app.orchestration.graph import create_orchestration_graph
from app.orchestration.state import OrchestrationState


class FakeDifyClient:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[dict] = []

    async def chat_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
    ) -> DifyResponse:
        self.calls.append(
            {
                "query": query,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "inputs": inputs or {},
            }
        )
        answer = self.answers.pop(0)
        return DifyResponse(
            answer=answer,
            conversation_id=conversation_id or "main-conv-1",
            task_id="task-1",
            message_id="msg-1",
            raw={"answer": answer, "conversation_id": conversation_id or "main-conv-1"},
        )


class FakeExecutor:
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results
        self.calls = []

    async def execute_calls(self, calls: list) -> dict[str, dict]:
        self.calls = calls
        return self.results


def make_state(query: str = "我想规划学习") -> OrchestrationState:
    return {
        "query": query,
        "user_id": "user-1",
        "session_id": "session-1",
        "mode": "session",
        "main_raw": {},
        "main_result": {},
        "agent_results": {},
        "answer": {},
        "profile": None,
        "learning_path": None,
        "completed": False,
        "error": "",
    }


def test_graph_returns_reply_only_main_agent_answer() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"你好，我会先了解你的目标。","question_box":null},'
                '"control":{"action":"reply_only","calls":[]}}'
            )
        ]
    )
    graph = create_orchestration_graph(main_client=main)

    result = asyncio.run(graph.ainvoke(make_state("你好"), {"configurable": {"thread_id": "graph-main-1"}}))

    assert result["answer"]["user_message"] == "你好，我会先了解你的目标。"
    assert result["completed"] is False


def test_graph_sets_error_when_main_agent_json_is_invalid() -> None:
    main = FakeDifyClient(["不是 JSON"])
    graph = create_orchestration_graph(main_client=main)

    result = asyncio.run(graph.ainvoke(make_state("你好"), {"configurable": {"thread_id": "graph-main-2"}}))

    assert "valid JSON" in result["error"]


def test_graph_executes_agent_calls_and_returns_final_main_agent_answer() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我先调用画像智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"profile",'
                '"agent_key":"profile_agent",'
                '"label":"基础画像智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"query":"完善画像"}'
                '}]}}'
            ),
            (
                '{"response":{"user_message":"画像已经生成。","question_box":null},'
                '"control":{"action":"final_answer","calls":[]}}'
            ),
        ]
    )
    profile = {"type": "basic_profile", "stage": "generated", "text": "画像"}
    executor = FakeExecutor({"profile": profile})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(
        graph.ainvoke(make_state("完善画像"), {"configurable": {"thread_id": "graph-main-3"}})
    )

    assert result["answer"]["user_message"] == "画像已经生成。"
    assert result["agent_results"] == {"profile": profile}
    assert result["profile"] == profile
    assert result["completed"] is True
    assert main.calls[1]["query"] == "请基于 agent 结果生成最终回复"
    assert main.calls[1]["inputs"] == {"agent_results": {"profile": profile}}
    assert executor.calls[0].agent_key == "profile_agent"
