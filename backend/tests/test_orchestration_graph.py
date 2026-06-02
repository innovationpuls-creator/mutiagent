from __future__ import annotations

import asyncio

from app.orchestration.dify_client import DifyResponse
from app.orchestration.graph import create_orchestration_graph, stream_orchestration_events
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

    async def execute_call(self, call) -> dict:
        self.calls.append(call)
        return self.results[call.call_id]


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
        "agent_trace": [],
        "user_profile": {},
        "profile": None,
        "learning_path": None,
        "awaiting_profile": False,
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
    assert main.calls[1]["inputs"] == {"agent_results": {"profile": profile}, "user_profile": {}}
    assert executor.calls[0].agent_key == "profile_agent"


def test_graph_supplies_current_query_when_agent_call_query_is_missing() -> None:
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
                '"agent_input":{}'
                '}]}}'
            ),
        ]
    )
    executor = FakeExecutor({"profile": {"type": "collecting", "stage": "basic_info", "text": "继续"}})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(
        graph.ainvoke(make_state("我想完善基础画像"), {"configurable": {"thread_id": "graph-main-4"}})
    )

    assert result["answer"]["user_message"] == "继续"
    assert executor.calls[0].agent_input == {"query": "我想完善基础画像"}
    assert len(main.calls) == 1


def test_graph_returns_collecting_profile_without_main_final_summary() -> None:
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
            )
        ]
    )
    profile = {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_md",
        "confirmed_info": {},
        "defaulted_fields": [],
        "question_md": "请继续介绍你的技术基础。",
        "question_box": {"question": "你熟悉哪些技术？", "options": ["Java", "Python"]},
        "text": "请继续介绍你的技术基础。",
    }
    executor = FakeExecutor({"profile": profile})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(
        graph.ainvoke(make_state("完善画像"), {"configurable": {"thread_id": "graph-main-5"}})
    )

    assert result["completed"] is False
    assert result["profile"] == profile
    assert result["answer"]["user_message"] == "请继续介绍你的技术基础。"
    assert result["answer"]["question_box"] == {"question": "你熟悉哪些技术？", "options": ["Java", "Python"]}
    assert len(main.calls) == 1


def test_stream_orchestration_events_emits_detailed_agent_flow() -> None:
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

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                make_state("完善画像"),
                main_client=main,
                executor_factory=lambda _state: executor,
            )
        ]

    events = asyncio.run(collect_events())

    assert [(event["event"], event["step_id"]) for event in events] == [
        ("agent_started", "main_agent"),
        ("agent_completed", "main_agent"),
        ("agent_started", "profile"),
        ("agent_completed", "profile"),
        ("agent_started", "main_agent_final"),
        ("agent_completed", "main_agent_final"),
        ("completed", "main_agent_final"),
    ]
    assert events[1]["message"] == "主智能体已返回调用计划：基础画像智能体。"
    assert events[2]["message"] == "基础画像智能体开始处理。"
    assert events[3]["message"] == "基础画像智能体结果返回成功。"
    assert events[4]["message"] == "主智能体开始整合智能体结果。"
    assert events[-1]["answer"]["user_message"] == "画像已经生成。"


def test_stream_orchestration_events_marks_ready_agent_batch_as_parallel() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会并行调用智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"intent",'
                '"agent_key":"intent_recognition_agent",'
                '"label":"意图识别智能体",'
                '"depends_on":[],'
                '"parallel_group":"profile_batch",'
                '"agent_input":{"query":"完善画像"}'
                '},{'
                '"call_id":"profile",'
                '"agent_key":"profile_agent",'
                '"label":"基础画像智能体",'
                '"depends_on":[],'
                '"parallel_group":"profile_batch",'
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
    executor = FakeExecutor({"intent": {"intent": "profile"}, "profile": profile})

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                make_state("完善画像"),
                main_client=main,
                executor_factory=lambda _state: executor,
            )
        ]

    events = asyncio.run(collect_events())
    agent_events = [event for event in events if event.get("phase") == "agent"]

    assert [(event["event"], event["step_id"], event["parallel_group"]) for event in agent_events[:4]] == [
        ("agent_started", "intent", "profile_batch"),
        ("agent_started", "profile", "profile_batch"),
        ("agent_completed", "intent", "profile_batch"),
        ("agent_completed", "profile", "profile_batch"),
    ]
