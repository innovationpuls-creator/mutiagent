from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from app.orchestration.agent_executor import AgentExecutor
from app.orchestration.agent_plan import AgentCall, MainAgentResult, validate_call_graph
from app.orchestration.dify_client import DIFY_CHAT_API_KEY, DifyClient
from app.orchestration.response_parser import DifyAnswerParseError, parse_json_answer
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

MAIN_AGENT_KEY = "main_agent"
MAIN_AGENT_LABEL = "主智能体"
FINAL_REPLY_QUERY = "请基于 agent 结果生成最终回复"

AGENT_LABELS = {
    MAIN_AGENT_KEY: MAIN_AGENT_LABEL,
    "intent_recognition_agent": "意图识别智能体",
    "profile_agent": "基础画像智能体",
    "learning_path_agent": "学习路径智能体",
}

ExecutorFactory = Callable[[OrchestrationState], Any]


def _trace_step(
    *,
    step_id: str,
    agent_key: str,
    label: str,
    phase: str,
    status: str,
    message: str,
    depends_on: list[str] | None = None,
    parallel_group: str | None = None,
) -> dict:
    return {
        "step_id": step_id,
        "agent_key": agent_key,
        "label": label,
        "phase": phase,
        "status": status,
        "message": message,
        "depends_on": depends_on or [],
        "parallel_group": parallel_group,
    }


def _append_trace(state: OrchestrationState, step: dict) -> list[dict]:
    trace = state.get("agent_trace", [])
    if not isinstance(trace, list):
        trace = []
    return [*trace, step]


def _parse_main_response(raw: dict) -> MainAgentResult:
    parsed = parse_json_answer(raw)
    result = MainAgentResult.model_validate(parsed)
    validate_call_graph(result.control.calls)
    return result


def _main_conversation_key(state: OrchestrationState) -> str:
    return f"{state['user_id']}:{MAIN_AGENT_KEY}"


def _query_with_profile_context(state: OrchestrationState, query: str) -> str:
    user_profile = state.get("user_profile", {})
    if not isinstance(user_profile, dict) or not user_profile:
        return query
    return (
        "【后端上下文】当前用户基础画像已完成。"
        "如果用户请求学习路径，不要再次调用 profile_agent；"
        "请基于这份画像判断是否应调用 learning_path_agent。"
        f"\n当前用户基础画像 JSON：{user_profile}"
        f"\n【用户请求】{query}"
    )


async def _call_main_agent(
    *,
    state: OrchestrationState,
    client: DifyClient,
    conversation_ids: dict[str, str],
    query: str,
    inputs: dict | None = None,
) -> tuple[dict, MainAgentResult]:
    conversation_key = _main_conversation_key(state)
    response = await client.chat_blocking(
        query=_query_with_profile_context(state, query),
        user_id=state["user_id"],
        conversation_id=conversation_ids.get(conversation_key, ""),
        inputs={**(inputs or {}), "user_profile": state.get("user_profile", {})},
    )
    conversation_ids[conversation_key] = response.conversation_id
    return response.raw, _parse_main_response(response.raw)


def _error_update(state: OrchestrationState, error: Exception) -> dict:
    logger.warning("main-agent graph failed: %s", error)
    return {
        "error": str(error),
        "completed": False,
        "agent_trace": _append_trace(
            state,
            _trace_step(
                step_id=MAIN_AGENT_KEY,
                agent_key=MAIN_AGENT_KEY,
                label=MAIN_AGENT_LABEL,
                phase="main",
                status="failed",
                message=str(error),
            ),
        ),
    }


def _call_trace(call: AgentCall, status: str, message: str) -> dict:
    return _trace_step(
        step_id=call.call_id,
        agent_key=call.agent_key,
        label=call.label or AGENT_LABELS.get(call.agent_key, call.agent_key),
        phase="agent",
        status=status,
        message=message,
        depends_on=call.depends_on,
        parallel_group=call.parallel_group,
    )


def _result_for_agent(calls: list[AgentCall], results: dict[str, dict], agent_key: str) -> dict | None:
    for call in calls:
        if call.agent_key == agent_key and call.call_id in results:
            return results[call.call_id]
    return None


def _completed_profile(calls: list[AgentCall], results: dict[str, dict]) -> dict | None:
    profile = _result_for_agent(calls, results, "profile_agent")
    if profile is None:
        return None
    if profile.get("type") == "basic_profile" and profile.get("stage") == "generated":
        return profile
    return None


def _profile_result(calls: list[AgentCall], results: dict[str, dict]) -> dict | None:
    return _result_for_agent(calls, results, "profile_agent")


def _learning_path(calls: list[AgentCall], results: dict[str, dict]) -> dict | None:
    return _result_for_agent(calls, results, "learning_path_agent")


def _calls_with_default_query(calls: list[AgentCall], query: str) -> list[AgentCall]:
    enriched: list[AgentCall] = []
    for call in calls:
        if call.agent_key not in {"intent_recognition_agent", "profile_agent"}:
            enriched.append(call)
            continue
        raw_query = call.agent_input.get("query")
        if isinstance(raw_query, str) and raw_query.strip():
            enriched.append(call)
            continue
        enriched.append(call.model_copy(update={"agent_input": {**call.agent_input, "query": query}}))
    return enriched


def _route_after_main(state: OrchestrationState) -> str:
    if state.get("error"):
        return "end"

    main_result = state.get("main_result", {})
    control = main_result.get("control", {}) if isinstance(main_result, dict) else {}
    if control.get("action") == "call_agents":
        return "execute_agents"
    return "end"


def _route_after_agent_execution(state: OrchestrationState) -> str:
    if state.get("error"):
        return "end"
    if state.get("awaiting_profile"):
        return "end"
    return "call_main_final"


def _default_executor_factory(state: OrchestrationState) -> AgentExecutor:
    raise RuntimeError("AgentExecutor requires an injected executor_factory")


async def stream_orchestration_events(
    state: OrchestrationState,
    main_client: DifyClient | None = None,
    executor_factory: ExecutorFactory | None = None,
) -> AsyncGenerator[dict, None]:
    yield {
        "event": "agent_started",
        "step_id": MAIN_AGENT_KEY,
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "message": "主智能体开始处理。",
    }

    graph = create_orchestration_graph(main_client=main_client, executor_factory=executor_factory)
    result = await graph.ainvoke(state, {"configurable": {"thread_id": state["session_id"] or state["user_id"]}})

    if result.get("error"):
        yield {
            "event": "error",
            "step_id": MAIN_AGENT_KEY,
            "agent_key": MAIN_AGENT_KEY,
            "agent": MAIN_AGENT_KEY,
            "label": MAIN_AGENT_LABEL,
            "message": result["error"],
            "state": result,
        }
        return

    for step in result.get("agent_trace", []):
        if not isinstance(step, dict):
            continue
        if step.get("step_id") == MAIN_AGENT_KEY:
            continue
        yield {
            "event": "agent_completed" if step.get("status") == "completed" else "agent_failed",
            "step_id": step.get("step_id", ""),
            "agent_key": step.get("agent_key", ""),
            "agent": step.get("agent_key", ""),
            "label": step.get("label", ""),
            "message": step.get("message", ""),
            "phase": step.get("phase", ""),
            "depends_on": step.get("depends_on", []),
            "parallel_group": step.get("parallel_group"),
        }

    yield {
        "event": "completed",
        "step_id": MAIN_AGENT_KEY,
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "message": "主智能体已完成。",
        "state": result,
        "answer": result.get("answer", {}),
        "completed": result.get("completed", False),
    }


def create_orchestration_graph(
    main_client: DifyClient | None = None,
    executor_factory: ExecutorFactory | None = None,
):
    main = main_client or DifyClient(api_key=DIFY_CHAT_API_KEY)
    build_executor = executor_factory or _default_executor_factory
    main_conversation_ids: dict[str, str] = {}

    async def call_main_agent(state: OrchestrationState) -> dict:
        try:
            raw, result = await _call_main_agent(
                state=state,
                client=main,
                conversation_ids=main_conversation_ids,
                query=state["query"],
            )
        except (DifyAnswerParseError, ValidationError, ValueError) as exc:
            return _error_update(state, exc)

        action = result.control.action
        return {
            "main_raw": raw,
            "main_result": result.model_dump(),
            "answer": result.response.model_dump(),
            "completed": action == "final_answer",
            "error": "",
            "agent_trace": _append_trace(
                state,
                _trace_step(
                    step_id=MAIN_AGENT_KEY,
                    agent_key=MAIN_AGENT_KEY,
                    label=MAIN_AGENT_LABEL,
                    phase="main",
                    status="completed",
                    message="主智能体已返回控制结果。",
                ),
            ),
        }

    async def execute_agent_calls(state: OrchestrationState) -> dict:
        result = MainAgentResult.model_validate(state["main_result"])
        calls = _calls_with_default_query(result.control.calls, state["query"])
        trace = state.get("agent_trace", [])
        if not isinstance(trace, list):
            trace = []

        try:
            executor = build_executor(state)
            agent_results = await executor.execute_calls(calls)
        except Exception as exc:
            logger.warning("agent execution failed: %s", exc)
            return {
                "error": str(exc),
                "completed": False,
                "agent_trace": [
                    *trace,
                    *[_call_trace(call, "failed", str(exc)) for call in calls],
                ],
            }

        profile_result = _profile_result(calls, agent_results)
        completed_profile = _completed_profile(calls, agent_results)
        if profile_result is not None and completed_profile is None:
            return {
                "agent_results": agent_results,
                "answer": {
                    "user_message": str(profile_result.get("question_md") or profile_result.get("text") or ""),
                    "question_box": profile_result.get("question_box"),
                },
                "profile": profile_result,
                "learning_path": None,
                "completed": False,
                "awaiting_profile": True,
                "agent_trace": [
                    *trace,
                    *[_call_trace(call, "completed", f"{call.label}已完成。") for call in calls],
                ],
            }

        return {
            "agent_results": agent_results,
            "profile": completed_profile,
            "learning_path": _learning_path(calls, agent_results),
            "awaiting_profile": False,
            "agent_trace": [
                *trace,
                *[_call_trace(call, "completed", f"{call.label}已完成。") for call in calls],
            ],
        }

    async def call_main_final(state: OrchestrationState) -> dict:
        try:
            raw, result = await _call_main_agent(
                state=state,
                client=main,
                conversation_ids=main_conversation_ids,
                query=FINAL_REPLY_QUERY,
                inputs={"agent_results": state.get("agent_results", {})},
            )
        except (DifyAnswerParseError, ValidationError, ValueError) as exc:
            return _error_update(state, exc)

        return {
            "main_raw": raw,
            "main_result": result.model_dump(),
            "answer": result.response.model_dump(),
            "completed": True,
            "error": "",
            "agent_trace": _append_trace(
                state,
                _trace_step(
                    step_id="main_agent_final",
                    agent_key=MAIN_AGENT_KEY,
                    label=MAIN_AGENT_LABEL,
                    phase="final",
                    status="completed",
                    message="主智能体已整合智能体结果。",
                ),
            ),
        }

    builder = StateGraph(OrchestrationState)
    builder.add_node("call_main_agent", call_main_agent)
    builder.add_node("execute_agent_calls", execute_agent_calls)
    builder.add_node("call_main_final", call_main_final)

    builder.set_entry_point("call_main_agent")
    builder.add_conditional_edges(
        "call_main_agent",
        _route_after_main,
        {
            "execute_agents": "execute_agent_calls",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "execute_agent_calls",
        _route_after_agent_execution,
        {
            "call_main_final": "call_main_final",
            "end": END,
        },
    )
    builder.add_edge("call_main_final", END)

    return builder.compile(checkpointer=MemorySaver())
