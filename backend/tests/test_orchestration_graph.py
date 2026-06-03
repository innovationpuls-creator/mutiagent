from __future__ import annotations

import asyncio

from app.orchestration.dify_client import DifyResponse
from app.orchestration.graph import create_orchestration_graph, stream_orchestration_events
from app.orchestration.state import OrchestrationState
from tests.test_agent_plan import build_course_knowledge_outline_result, build_learning_path_result


class FakeDifyClient:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[dict] = []
        self.uploaded_contexts: list[dict] = []

    async def chat_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
        files: list[dict] | None = None,
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

    async def chat_streaming_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
        files: list[dict] | None = None,
        on_event=None,
    ) -> DifyResponse:
        return await self.chat_blocking(query, user_id, conversation_id, inputs, files)

    async def upload_contexts(self, user_id: str, contexts: dict) -> list[dict]:
        self.uploaded_contexts.append(contexts)
        return [{"type": "document", "transfer_method": "local_file", "upload_file_id": "fake-file-id"}]


class FailingDifyClient:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict] = []
        self.uploaded_contexts: list[dict] = []

    async def chat_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
        files: list[dict] | None = None,
    ) -> DifyResponse:
        self.calls.append(
            {
                "query": query,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "inputs": inputs or {},
            }
        )
        raise self.error

    async def chat_streaming_blocking(
        self,
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
        files: list[dict] | None = None,
        on_event=None,
    ) -> DifyResponse:
        return await self.chat_blocking(query, user_id, conversation_id, inputs, files)

    async def upload_contexts(self, user_id: str, contexts: dict) -> list[dict]:
        self.uploaded_contexts.append(contexts)
        return [{"type": "document", "transfer_method": "local_file", "upload_file_id": "fake-file-id"}]


class FakeExecutor:
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results
        self.calls = []

    async def execute_calls(self, calls: list, on_event=None) -> dict[str, dict]:
        self.calls = calls
        return self.results

    async def execute_call(self, call, on_event=None) -> dict:
        self.calls.append(call)
        return self.results[call.call_id]


class FailingExecutor:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = []

    async def execute_calls(self, calls: list, on_event=None) -> dict[str, dict]:
        self.calls = calls
        raise self.error

    async def execute_call(self, call, on_event=None) -> dict:
        self.calls.append(call)
        raise self.error


def question_option(label: str, field: str = "learning_stage") -> dict:
    return {
        "label": label,
        "value": label,
        "description": label,
        "target_fields": [field],
        "fills": {field: label},
    }


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


def test_graph_sets_error_when_main_agent_request_fails() -> None:
    main = FailingDifyClient(TimeoutError("主智能体请求超时"))
    graph = create_orchestration_graph(main_client=main)

    result = asyncio.run(graph.ainvoke(make_state("你好"), {"configurable": {"thread_id": "graph-main-timeout"}}))

    assert result["error"] == "主智能体请求超时"
    assert result["completed"] is False
    assert result["agent_trace"][-1]["step_id"] == "main_agent"
    assert result["agent_trace"][-1]["status"] == "failed"


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
    assert result["completed"] is True
    assert main.calls[1]["inputs"] == {"userinput.query": "请基于 agent 结果生成最终回复"}
    assert main.calls[1]["query"].endswith("[User Query]\n请基于 agent 结果生成最终回复")
    assert "agent_results" in main.calls[1]["query"]
    assert "画像" in main.calls[1]["query"]
    assert executor.calls[0].agent_key == "profile_agent"


def test_graph_persists_main_agent_conversation_with_callbacks() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"继续主智能体会话。","question_box":null},'
                '"control":{"action":"reply_only","calls":[]}}'
            )
        ]
    )
    writes: list[tuple[str, str, str]] = []
    graph = create_orchestration_graph(
        main_client=main,
        conversation_getter=lambda user_uid, agent_key: "main-conv-saved",
        conversation_setter=lambda user_uid, agent_key, conversation_id: writes.append(
            (user_uid, agent_key, conversation_id)
        ),
    )

    result = asyncio.run(graph.ainvoke(make_state("继续"), {"configurable": {"thread_id": "graph-main-conv"}}))

    assert result["answer"]["user_message"] == "继续主智能体会话。"
    assert main.calls[0]["conversation_id"] == "main-conv-saved"
    assert writes == [("user-1", "main_agent", "main-conv-saved")]


def test_graph_returns_to_main_agent_after_agent_failure() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会调用学习路径智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"learning",'
                '"agent_key":"learning_path_agent",'
                '"label":"学习路径智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"goal":"后端就业"}'
                '}]}}'
            ),
            (
                '{"response":{"user_message":"学习路径暂时无法生成，我会说明下一步。","question_box":null},'
                '"control":{"action":"final_answer","calls":[]}}'
            ),
        ]
    )
    executor = FailingExecutor(RuntimeError("请先完成基础画像，再生成学习路径。"))
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(
        graph.ainvoke(make_state("生成学习路径"), {"configurable": {"thread_id": "graph-agent-failure"}})
    )

    assert result["answer"]["user_message"] == "学习路径暂时无法生成，我会说明下一步。"
    assert result["agent_results"]["__error__"]["type"] == "agent_error"
    assert result["agent_results"]["__error__"]["next_action"] == "main_agent_final"
    assert main.calls[1]["query"].endswith("请基于 agent 结果生成最终回复")
    assert "请先完成基础画像，再生成学习路径。" in main.calls[1]["query"]
    assert result["completed"] is True


def test_graph_sets_error_when_main_agent_final_request_fails() -> None:
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

    async def fail_final(
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
        files: list[dict] | None = None,
        on_event=None,
    ) -> DifyResponse:
        if "请基于 agent 结果生成最终回复" in query:
            raise TimeoutError("主智能体最终整合超时")
        return await FakeDifyClient.chat_streaming_blocking(main, query, user_id, conversation_id, inputs, files, on_event)

    main.chat_streaming_blocking = fail_final
    profile = {"type": "basic_profile", "stage": "generated", "text": "画像"}
    executor = FakeExecutor({"profile": profile})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(graph.ainvoke(make_state("完善画像"), {"configurable": {"thread_id": "graph-final-timeout"}}))

    assert result["error"] == "主智能体最终整合超时"
    assert result["completed"] is False
    assert result["agent_trace"][-1]["step_id"] == "main_agent_final"
    assert result["agent_trace"][-1]["phase"] == "final"
    assert result["agent_trace"][-1]["status"] == "failed"


def test_graph_routes_learning_path_plan_to_profile_when_profile_is_missing() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会先生成学习路径。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"learning",'
                '"agent_key":"learning_path_agent",'
                '"label":"学习路径智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"goal":"FastAPI 后端实习"}'
                '}]}}'
            )
        ]
    )
    profile = {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "question_md": "",
        "question_box": {
            "question": "你目前处于哪个学习阶段？",
            "options": [question_option("刚入门"), question_option("有基础")],
        },
        "text": "你目前处于哪个学习阶段？",
    }
    executor = FakeExecutor({"profile": profile})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(
        graph.ainvoke(make_state("我想生成 FastAPI 学习路径"), {"configurable": {"thread_id": "graph-profile-first"}})
    )

    assert result["awaiting_profile"] is True
    assert result["profile"] == profile
    assert result["learning_path"] is None
    assert result["answer"]["question_box"] == {
        "question": "你目前处于哪个学习阶段？",
        "options": [question_option("刚入门"), question_option("有基础")],
    }
    assert executor.calls[0].agent_key == "profile_agent"
    assert executor.calls[0].agent_input == {"query": "我想生成 FastAPI 学习路径"}
    assert len(main.calls) == 1


def test_graph_uses_canonical_label_for_known_agent_key() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会调用用户画像收集智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"profile_agent_call",'
                '"agent_key":"profile_agent",'
                '"label":"用户画像收集智能体",'
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
        "question_md": "请说明你的年级和专业。",
        "question_box": {"question": "", "options": []},
        "text": "请说明你的年级和专业。",
    }
    executor = FakeExecutor({"profile_agent_call": profile})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(graph.ainvoke(make_state("我现在的基础信息"), {"configurable": {"thread_id": "graph-label"}}))

    assert result["agent_trace"][-1]["label"] == "基础画像智能体"
    assert result["agent_trace"][-1]["message"] == "基础画像智能体已完成。"


def test_graph_routes_main_question_box_to_profile_when_profile_is_missing() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"请先说明你的技术基础。",'
                '"question_box":{"question":"请选择你当前的技术基础水平：","options":['
                '{"label":"Python 基础扎实","value":"Python 基础扎实","description":"Python 基础扎实",'
                '"target_fields":["knowledge_foundation"],"fills":{"knowledge_foundation":"Python 基础扎实"}},'
                '{"label":"完全零基础","value":"完全零基础","description":"完全零基础",'
                '"target_fields":["knowledge_foundation"],"fills":{"knowledge_foundation":"完全零基础"}}]}},'
                '"control":{"action":"reply_only","calls":[]}}'
            )
        ]
    )
    profile = {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "question_md": "",
        "question_box": {
            "question": "你目前处于哪个学习阶段？",
            "options": [question_option("刚入门"), question_option("有基础")],
        },
        "text": "你目前处于哪个学习阶段？",
    }
    executor = FakeExecutor({"profile": profile})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)

    result = asyncio.run(
        graph.ainvoke(make_state("我想生成 FastAPI 学习路径"), {"configurable": {"thread_id": "graph-qbox-profile"}})
    )

    assert result["awaiting_profile"] is True
    assert result["profile"] == profile
    assert result["answer"]["question_box"] == {
        "question": "你目前处于哪个学习阶段？",
        "options": [question_option("刚入门"), question_option("有基础")],
    }
    assert executor.calls[0].agent_key == "profile_agent"


def test_graph_keeps_learning_path_plan_when_profile_is_completed() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会生成学习路径。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"learning",'
                '"agent_key":"learning_path_agent",'
                '"label":"学习路径智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"goal":"FastAPI 后端实习"}'
                '}]}}'
            ),
            (
                '{"response":{"user_message":"学习路径已生成。","question_box":null},'
                '"control":{"action":"final_answer","calls":[]}}'
            ),
        ]
    )
    learning_path = build_learning_path_result()
    executor = FakeExecutor({"learning": learning_path})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)
    state = make_state("生成学习路径")
    state["user_profile"] = {"type": "basic_profile", "stage": "generated"}

    result = asyncio.run(graph.ainvoke(state, {"configurable": {"thread_id": "graph-learning-after-profile"}}))

    assert result["learning_path"] == learning_path
    assert result["completed"] is True
    assert executor.calls[0].agent_key == "learning_path_agent"


def test_graph_keeps_course_knowledge_plan_when_profile_is_completed() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会生成当前课程章节。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"course_knowledge",'
                '"agent_key":"course_knowledge_agent",'
                '"label":"课程知识点规划智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{}'
                '}]}}'
            ),
            (
                '{"response":{"user_message":"课程章节已生成。","question_box":null},'
                '"control":{"action":"final_answer","calls":[]}}'
            ),
        ]
    )
    outline = build_course_knowledge_outline_result()
    executor = FakeExecutor({"course_knowledge": outline})
    graph = create_orchestration_graph(main_client=main, executor_factory=lambda _state: executor)
    state = make_state("生成当前课程教学资源")
    state["user_profile"] = {"type": "basic_profile", "stage": "generated"}

    result = asyncio.run(graph.ainvoke(state, {"configurable": {"thread_id": "graph-course-knowledge-after-profile"}}))

    assert result["course_knowledge_outline"] == outline
    assert result["completed"] is True
    assert executor.calls[0].agent_key == "course_knowledge_agent"


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
        "question_box": {
            "question": "你熟悉哪些技术？",
            "options": [question_option("Java", "knowledge_foundation"), question_option("Python", "knowledge_foundation")],
        },
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
    assert result["answer"]["question_box"] == {
        "question": "你熟悉哪些技术？",
        "options": [question_option("Java", "knowledge_foundation"), question_option("Python", "knowledge_foundation")],
    }
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
        ("agent_completed", "context_user_input"),
        ("agent_completed", "context_profile"),
        ("agent_completed", "context_agent_registry"),
        ("agent_completed", "context_main_inputs"),
        ("agent_started", "main_agent"),
        ("agent_completed", "main_agent"),
        ("agent_completed", "profile_context"),
        ("agent_started", "profile"),
        ("agent_completed", "profile"),
        ("agent_started", "main_agent_final"),
        ("agent_completed", "main_agent_final"),
        ("completed", "main_agent_final"),
    ]
    assert events[5]["message"] == "主智能体已返回调用计划：基础画像智能体。"
    assert events[6]["message"] == "基础画像智能体已接收本轮补充信息。"
    assert events[7]["message"] == "基础画像智能体开始处理。"
    assert events[8]["message"] == "基础画像智能体结果返回成功。"
    assert events[9]["message"] == "主智能体开始整合智能体结果。"
    assert events[-1]["answer"]["user_message"] == "画像已经生成。"


def test_stream_orchestration_events_emits_main_agent_failure() -> None:
    main = FailingDifyClient(TimeoutError("主智能体请求超时"))

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                make_state("你好"),
                main_client=main,
                executor_factory=lambda _state: FakeExecutor({}),
            )
        ]

    events = asyncio.run(collect_events())

    assert events[-1]["event"] == "error"
    assert events[-1]["step_id"] == "main_agent"
    assert events[-1]["agent_key"] == "main_agent"
    assert events[-1]["label"] == "主智能体"
    assert events[-1]["message"] == "主智能体请求超时"
    assert events[-1]["state"]["agent_trace"][-1]["status"] == "failed"


def test_stream_orchestration_events_returns_to_main_agent_after_agent_failure() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会调用学习路径智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"learning",'
                '"agent_key":"learning_path_agent",'
                '"label":"学习路径智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"goal":"后端就业"}'
                '}]}}'
            ),
            (
                '{"response":{"user_message":"学习路径暂时无法生成，我会说明下一步。","question_box":null},'
                '"control":{"action":"final_answer","calls":[]}}'
            ),
        ]
    )
    executor = FailingExecutor(RuntimeError("请先完成基础画像，再生成学习路径。"))

    async def collect_events() -> list[dict]:
        state = make_state("生成学习路径")
        state["user_profile"] = {"type": "basic_profile", "stage": "generated"}
        return [
            event
            async for event in stream_orchestration_events(
                state,
                main_client=main,
                executor_factory=lambda _state: executor,
            )
        ]

    events = asyncio.run(collect_events())

    assert ("agent_failed", "learning") in [(event["event"], event["step_id"]) for event in events]
    assert ("agent_started", "main_agent_final") in [(event["event"], event["step_id"]) for event in events]
    assert ("agent_completed", "main_agent_final") in [(event["event"], event["step_id"]) for event in events]
    assert events[-1]["event"] == "completed"
    assert events[-1]["answer"]["user_message"] == "学习路径暂时无法生成，我会说明下一步。"
    assert "main_agent_final" in main.calls[1]["query"]


def test_stream_orchestration_events_emits_main_agent_final_failure() -> None:
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

    async def fail_final(
        query: str,
        user_id: str,
        conversation_id: str = "",
        inputs: dict | None = None,
        files: list[dict] | None = None,
        on_event=None,
    ) -> DifyResponse:
        if "请基于 agent 结果生成最终回复" in query:
            raise TimeoutError("主智能体最终整合超时")
        return await FakeDifyClient.chat_streaming_blocking(main, query, user_id, conversation_id, inputs, files, on_event)

    main.chat_streaming_blocking = fail_final
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

    assert events[-1]["event"] == "error"
    assert events[-1]["step_id"] == "main_agent_final"
    assert events[-1]["agent_key"] == "main_agent"
    assert events[-1]["label"] == "主智能体"
    assert events[-1]["message"] == "主智能体最终整合超时"
    assert events[-1]["state"]["agent_trace"][-1]["step_id"] == "main_agent_final"
    assert events[-1]["state"]["agent_trace"][-1]["status"] == "failed"


def test_stream_orchestration_events_routes_learning_path_plan_to_profile_when_profile_is_missing() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会先生成学习路径。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"learning",'
                '"agent_key":"learning_path_agent",'
                '"label":"学习路径智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"goal":"FastAPI 后端实习"}'
                '}]}}'
            )
        ]
    )
    profile = {
        "type": "collecting",
        "stage": "basic_info",
        "question_mode": "question_box",
        "question_md": "",
        "question_box": {
            "question": "你目前处于哪个学习阶段？",
            "options": [question_option("刚入门"), question_option("有基础")],
        },
        "text": "你目前处于哪个学习阶段？",
    }
    executor = FakeExecutor({"profile": profile})

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                make_state("我想生成 FastAPI 学习路径"),
                main_client=main,
                executor_factory=lambda _state: executor,
            )
        ]

    events = asyncio.run(collect_events())

    assert ("agent_started", "profile") in [(event["event"], event["step_id"]) for event in events]
    assert ("agent_started", "learning") not in [(event["event"], event["step_id"]) for event in events]
    assert events[-1]["event"] == "completed"
    assert events[-1]["answer"]["question_box"] == {
        "question": "你目前处于哪个学习阶段？",
        "options": [question_option("刚入门"), question_option("有基础")],
    }
    assert events[-1]["state"]["awaiting_profile"] is True
    assert executor.calls[0].agent_key == "profile_agent"


def test_stream_orchestration_events_uses_canonical_label_for_known_agent_key() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会调用用户画像收集智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"profile_agent_call",'
                '"agent_key":"profile_agent",'
                '"label":"用户画像收集智能体",'
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
        "question_md": "请说明你的年级和专业。",
        "question_box": {"question": "", "options": []},
        "text": "请说明你的年级和专业。",
    }
    executor = FakeExecutor({"profile_agent_call": profile})

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                make_state("我现在的基础信息"),
                main_client=main,
                executor_factory=lambda _state: executor,
            )
        ]

    events = asyncio.run(collect_events())
    profile_events = [event for event in events if event.get("step_id") == "profile_agent_call"]

    assert profile_events[0]["label"] == "基础画像智能体"
    assert profile_events[0]["message"] == "基础画像智能体开始处理。"
    assert profile_events[1]["label"] == "基础画像智能体"
    assert profile_events[1]["message"] == "基础画像智能体结果返回成功。"
    assert events[-1]["label"] == "基础画像智能体"
    assert events[-1]["state"]["agent_trace"][-1]["label"] == "基础画像智能体"


def test_stream_orchestration_events_describes_learning_path_context_inputs() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我会调用学习路径智能体。","question_box":null},'
                '"control":{"action":"call_agents","calls":[{'
                '"call_id":"learning",'
                '"agent_key":"learning_path_agent",'
                '"label":"学习路径智能体",'
                '"depends_on":[],'
                '"parallel_group":null,'
                '"agent_input":{"goal":"后端就业"}'
                '}]}}'
            ),
            (
                '{"response":{"user_message":"学习路径已经生成。","question_box":null},'
                '"control":{"action":"final_answer","calls":[]}}'
            ),
        ]
    )
    learning_path = build_learning_path_result()
    executor = FakeExecutor({"learning": learning_path})
    state = make_state("生成学习路径")
    state["user_profile"] = {"type": "basic_profile", "stage": "generated"}

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                state,
                main_client=main,
                executor_factory=lambda _state: executor,
            )
        ]

    events = asyncio.run(collect_events())

    assert any(
        event["step_id"] == "learning_context" and event["message"] == "学习路径智能体已接收画像与学习目标。"
        for event in events
    )


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


def test_stream_orchestration_events_emits_context_preparation_for_reply_only() -> None:
    main = FakeDifyClient(
        [
            (
                '{"response":{"user_message":"我先追问学习路径侧重点。","question_box":null},'
                '"control":{"action":"reply_only","calls":[]}}'
            )
        ]
    )
    state = make_state("我是大三学生")
    state["user_profile"] = {"type": "basic_profile", "stage": "generated"}

    async def collect_events() -> list[dict]:
        return [
            event
            async for event in stream_orchestration_events(
                state,
                main_client=main,
                executor_factory=lambda _state: FakeExecutor({}),
            )
        ]

    events = asyncio.run(collect_events())

    assert [(event["event"], event["step_id"], event["message"]) for event in events[:5]] == [
        ("agent_completed", "context_user_input", "已读取本轮用户输入。"),
        ("agent_completed", "context_profile", "已加载基础画像上下文。"),
        ("agent_completed", "context_agent_registry", "已配置可调用智能体。"),
        ("agent_completed", "context_main_inputs", "已注入主智能体上下文。"),
        ("agent_started", "main_agent", "主智能体开始处理。"),
    ]
