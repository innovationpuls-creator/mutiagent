from __future__ import annotations

import asyncio
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
ConversationGetter = Callable[[str, str], str]
ConversationSetter = Callable[[str, str, str], object]


def _trace_step(
    *,
    step_id: str,
    agent_key: str,
    label: str,
    phase: str,
    status: str,
    message: str,
    kind: str = "agent",
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
        "kind": kind,
        "depends_on": depends_on or [],
        "parallel_group": parallel_group,
    }


def _append_trace(state: OrchestrationState, step: dict) -> list[dict]:
    trace = state.get("agent_trace", [])
    if not isinstance(trace, list):
        trace = []
    return [*trace, step]


def _context_event(step_id: str, label: str, message: str) -> dict:
    return {
        "event": "agent_completed",
        "step_id": step_id,
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": label,
        "phase": "context",
        "kind": "data",
        "message": message,
    }


def _agent_context_message(call: AgentCall) -> str:
    if call.agent_key == "learning_path_agent":
        return "学习路径智能体已接收画像与学习目标。"
    if call.agent_key == "profile_agent":
        return "基础画像智能体已接收本轮补充信息。"
    if call.agent_key == "intent_recognition_agent":
        return "意图识别智能体已接收本轮输入。"
    return f"{call.label or AGENT_LABELS.get(call.agent_key, call.agent_key)}已接收上下文。"


def _parse_main_response(raw: dict) -> MainAgentResult:
    parsed = parse_json_answer(raw)
    result = MainAgentResult.model_validate(parsed)
    validate_call_graph(result.control.calls)
    return result


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
    conversation_getter: ConversationGetter | None = None,
    conversation_setter: ConversationSetter | None = None,
) -> tuple[dict, MainAgentResult]:
    conversation_id = (
        conversation_getter(state["user_id"], MAIN_AGENT_KEY)
        if conversation_getter is not None
        else conversation_ids.get(state["user_id"], "")
    )
    response = await client.chat_blocking(
        query=_query_with_profile_context(state, query),
        user_id=state["user_id"],
        conversation_id=conversation_id,
        inputs={**(inputs or {}), "user_profile": state.get("user_profile", {})},
    )
    if conversation_setter is not None:
        conversation_setter(state["user_id"], MAIN_AGENT_KEY, response.conversation_id)
    else:
        conversation_ids[state["user_id"]] = response.conversation_id
    return response.raw, _parse_main_response(response.raw)


def _agent_error_results(error: Exception) -> dict[str, dict]:
    return {
        "__error__": {
            "type": "agent_error",
            "message": str(error) or "智能体执行失败，请稍后重试。",
            "next_action": "main_agent_final",
        }
    }


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
        kind="agent",
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


def _has_completed_profile_context(state: OrchestrationState) -> bool:
    user_profile = state.get("user_profile", {})
    if not isinstance(user_profile, dict):
        return False
    return user_profile.get("type") == "basic_profile" and user_profile.get("stage") == "generated"


def _requires_profile_before_learning_path(state: OrchestrationState, calls: list[AgentCall]) -> bool:
    if _has_completed_profile_context(state):
        return False
    return any(call.agent_key == "learning_path_agent" for call in calls)


def _requires_profile_for_main_result(state: OrchestrationState, result: MainAgentResult) -> bool:
    if _has_completed_profile_context(state):
        return False
    if any(call.agent_key == "profile_agent" for call in result.control.calls):
        return False
    if any(call.agent_key != "profile_agent" for call in result.control.calls):
        return True
    return result.control.action != "call_agents" and result.response.question_box is not None


def _profile_first_calls(state: OrchestrationState) -> list[AgentCall]:
    return [
        AgentCall(
            call_id="profile",
            agent_key="profile_agent",
            label=AGENT_LABELS["profile_agent"],
            depends_on=[],
            parallel_group=None,
            agent_input={"query": state["query"]},
        )
    ]


def _calls_for_profile_state(state: OrchestrationState, calls: list[AgentCall]) -> list[AgentCall]:
    if _requires_profile_before_learning_path(state, calls):
        return _profile_first_calls(state)
    return calls


def _main_result_for_profile_state(state: OrchestrationState, result: MainAgentResult) -> MainAgentResult:
    if not _requires_profile_for_main_result(state, result):
        return result
    return result.model_copy(
        update={
            "control": result.control.model_copy(
                update={
                    "action": "call_agents",
                    "calls": _profile_first_calls(state),
                }
            )
        }
    )


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
    conversation_getter: ConversationGetter | None = None,
    conversation_setter: ConversationSetter | None = None,
) -> AsyncGenerator[dict, None]:
    main = main_client or DifyClient(api_key=DIFY_CHAT_API_KEY)
    build_executor = executor_factory or _default_executor_factory
    conversation_ids: dict[str, str] = {}
    current_state: OrchestrationState = {**state, "agent_trace": state.get("agent_trace", [])}
    has_profile_context = isinstance(current_state.get("user_profile"), dict) and bool(current_state.get("user_profile"))

    yield _context_event("context_user_input", "读取用户输入", "已读取本轮用户输入。")
    yield _context_event(
        "context_profile",
        "加载用户画像",
        "已加载基础画像上下文。" if has_profile_context else "未检测到完整基础画像。",
    )
    yield _context_event(
        "context_agent_registry",
        "配置智能体能力",
        "已配置可调用智能体。",
    )
    yield _context_event("context_main_inputs", "整理主智能体上下文", "已注入主智能体上下文。")

    yield {
        "event": "agent_started",
        "step_id": MAIN_AGENT_KEY,
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "kind": "agent",
        "message": "主智能体开始处理。",
    }

    try:
        raw, main_result = await _call_main_agent(
            state=current_state,
            client=main,
            conversation_ids=conversation_ids,
            query=current_state["query"],
            conversation_getter=conversation_getter,
            conversation_setter=conversation_setter,
        )
    except (DifyAnswerParseError, ValidationError, ValueError) as exc:
        result = {**current_state, **_error_update(current_state, exc)}
        yield {
            "event": "error",
            "step_id": MAIN_AGENT_KEY,
            "agent_key": MAIN_AGENT_KEY,
            "agent": MAIN_AGENT_KEY,
            "label": MAIN_AGENT_LABEL,
            "kind": "agent",
            "message": result["error"],
            "state": result,
        }
        return

    main_result = _main_result_for_profile_state(current_state, main_result)
    action = main_result.control.action
    plan_labels = "、".join(call.label or AGENT_LABELS.get(call.agent_key, call.agent_key) for call in main_result.control.calls)
    current_state = {
        **current_state,
        "main_raw": raw,
        "main_result": main_result.model_dump(),
        "answer": main_result.response.model_dump(),
        "completed": action == "final_answer",
        "error": "",
        "agent_trace": _append_trace(
            current_state,
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

    yield {
        "event": "agent_completed",
        "step_id": MAIN_AGENT_KEY,
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "phase": "main",
        "kind": "agent",
        "message": f"主智能体已返回调用计划：{plan_labels}。" if plan_labels else "主智能体已完成本轮判断。",
    }

    if action != "call_agents":
        yield {
            "event": "completed",
            "step_id": MAIN_AGENT_KEY,
            "agent_key": MAIN_AGENT_KEY,
            "agent": MAIN_AGENT_KEY,
            "label": MAIN_AGENT_LABEL,
            "kind": "agent",
            "message": "主智能体已完成。",
            "state": current_state,
            "answer": current_state.get("answer", {}),
            "completed": current_state.get("completed", False),
        }
        return

    calls = _calls_with_default_query(
        _calls_for_profile_state(current_state, main_result.control.calls),
        current_state["query"],
    )
    trace = current_state.get("agent_trace", [])
    if not isinstance(trace, list):
        trace = []

    agent_results: dict[str, dict] = {}
    pending = {call.call_id: call for call in calls}

    executor = build_executor(current_state)
    agent_error: Exception | None = None
    while pending:
        ready = [
            call
            for call in pending.values()
            if all(dependency in agent_results for dependency in call.depends_on)
        ]
        if not ready:
            agent_error = RuntimeError("Agent call graph has unresolved dependencies")
            for call in pending.values():
                trace = [*trace, _call_trace(call, "failed", str(agent_error))]
                yield {
                    "event": "agent_failed",
                    "step_id": call.call_id,
                    "agent_key": call.agent_key,
                    "agent": call.agent_key,
                    "label": call.label or AGENT_LABELS.get(call.agent_key, call.agent_key),
                    "phase": "agent",
                    "kind": "agent",
                    "message": str(agent_error),
                    "depends_on": call.depends_on,
                    "parallel_group": call.parallel_group,
                }
            break

        for call in ready:
            yield _context_event(
                f"{call.call_id}_context",
                "准备智能体上下文",
                _agent_context_message(call),
            )
            yield {
                "event": "agent_started",
                "step_id": call.call_id,
                "agent_key": call.agent_key,
                "agent": call.agent_key,
                "label": call.label or AGENT_LABELS.get(call.agent_key, call.agent_key),
                "phase": "agent",
                "kind": "agent",
                "message": f"{call.label or AGENT_LABELS.get(call.agent_key, call.agent_key)}开始处理。",
                "depends_on": call.depends_on,
                "parallel_group": call.parallel_group,
            }

        batch = await asyncio.gather(*(executor.execute_call(call) for call in ready), return_exceptions=True)
        for call, call_result in zip(ready, batch, strict=True):
            pending.pop(call.call_id)
            if isinstance(call_result, Exception):
                agent_error = call_result
                trace = [*trace, _call_trace(call, "failed", str(call_result))]
                yield {
                    "event": "agent_failed",
                    "step_id": call.call_id,
                    "agent_key": call.agent_key,
                    "agent": call.agent_key,
                    "label": call.label or AGENT_LABELS.get(call.agent_key, call.agent_key),
                    "phase": "agent",
                    "kind": "agent",
                    "message": str(call_result) or "智能体执行失败，请稍后重试。",
                    "depends_on": call.depends_on,
                    "parallel_group": call.parallel_group,
                }
                continue

            agent_results[call.call_id] = call_result
            trace = [
                *trace,
                _call_trace(call, "completed", f"{call.label or AGENT_LABELS.get(call.agent_key, call.agent_key)}已完成。"),
            ]
            yield {
                "event": "agent_completed",
                "step_id": call.call_id,
                "agent_key": call.agent_key,
                "agent": call.agent_key,
                "label": call.label or AGENT_LABELS.get(call.agent_key, call.agent_key),
                "phase": "agent",
                "kind": "agent",
                "message": f"{call.label or AGENT_LABELS.get(call.agent_key, call.agent_key)}结果返回成功。",
                "depends_on": call.depends_on,
                "parallel_group": call.parallel_group,
            }

        if agent_error is not None:
            agent_results.update(_agent_error_results(agent_error))
            break

    profile_result = _profile_result(calls, agent_results)
    completed_profile = _completed_profile(calls, agent_results)
    if profile_result is not None and completed_profile is None:
        result = {
            **current_state,
            "agent_results": agent_results,
            "answer": {
                "user_message": str(profile_result.get("question_md") or profile_result.get("text") or ""),
                "question_box": profile_result.get("question_box"),
            },
            "profile": profile_result,
            "learning_path": None,
            "completed": False,
            "awaiting_profile": True,
            "agent_trace": trace,
        }
        yield {
            "event": "completed",
            "step_id": calls[-1].call_id,
            "agent_key": calls[-1].agent_key,
            "agent": calls[-1].agent_key,
            "label": calls[-1].label or AGENT_LABELS.get(calls[-1].agent_key, calls[-1].agent_key),
            "kind": "agent",
            "message": "智能体结果已返回，等待用户补充信息。",
            "state": result,
            "answer": result.get("answer", {}),
            "completed": False,
        }
        return

    current_state = {
        **current_state,
        "agent_results": agent_results,
        "profile": completed_profile,
        "learning_path": _learning_path(calls, agent_results),
        "awaiting_profile": False,
        "agent_trace": trace,
    }

    yield {
        "event": "agent_started",
        "step_id": "main_agent_final",
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "phase": "final",
        "kind": "agent",
        "message": "主智能体开始整合智能体结果。",
    }

    try:
        raw, final_result = await _call_main_agent(
            state=current_state,
            client=main,
            conversation_ids=conversation_ids,
            query=FINAL_REPLY_QUERY,
            inputs={"agent_results": current_state.get("agent_results", {})},
            conversation_getter=conversation_getter,
            conversation_setter=conversation_setter,
        )
    except (DifyAnswerParseError, ValidationError, ValueError) as exc:
        result = {**current_state, **_error_update(current_state, exc)}
        yield {
            "event": "error",
            "step_id": "main_agent_final",
            "agent_key": MAIN_AGENT_KEY,
            "agent": MAIN_AGENT_KEY,
            "label": MAIN_AGENT_LABEL,
            "kind": "agent",
            "message": result["error"],
            "state": result,
        }
        return

    result = {
        **current_state,
        "main_raw": raw,
        "main_result": final_result.model_dump(),
        "answer": final_result.response.model_dump(),
        "completed": True,
        "error": "",
        "agent_trace": _append_trace(
            current_state,
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

    yield {
        "event": "agent_completed",
        "step_id": "main_agent_final",
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "phase": "final",
        "kind": "agent",
        "message": "主智能体已整合智能体结果。",
    }

    yield {
        "event": "completed",
        "step_id": "main_agent_final",
        "agent_key": MAIN_AGENT_KEY,
        "agent": MAIN_AGENT_KEY,
        "label": MAIN_AGENT_LABEL,
        "kind": "agent",
        "message": "主智能体已完成。",
        "state": result,
        "answer": result.get("answer", {}),
        "completed": result.get("completed", False),
    }


async def complete_with_main_agent_final(
    state: OrchestrationState,
    main_client: DifyClient | None = None,
    conversation_getter: ConversationGetter | None = None,
    conversation_setter: ConversationSetter | None = None,
) -> OrchestrationState:
    main = main_client or DifyClient(api_key=DIFY_CHAT_API_KEY)
    conversation_ids: dict[str, str] = {}
    try:
        raw, result = await _call_main_agent(
            state=state,
            client=main,
            conversation_ids=conversation_ids,
            query=FINAL_REPLY_QUERY,
            inputs={"agent_results": state.get("agent_results", {})},
            conversation_getter=conversation_getter,
            conversation_setter=conversation_setter,
        )
    except (DifyAnswerParseError, ValidationError, ValueError) as exc:
        return {**state, **_error_update(state, exc)}

    return {
        **state,
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


def create_orchestration_graph(
    main_client: DifyClient | None = None,
    executor_factory: ExecutorFactory | None = None,
    conversation_getter: ConversationGetter | None = None,
    conversation_setter: ConversationSetter | None = None,
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
                conversation_getter=conversation_getter,
                conversation_setter=conversation_setter,
            )
        except (DifyAnswerParseError, ValidationError, ValueError) as exc:
            return _error_update(state, exc)

        result = _main_result_for_profile_state(state, result)
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
        calls = _calls_with_default_query(_calls_for_profile_state(state, result.control.calls), state["query"])
        trace = state.get("agent_trace", [])
        if not isinstance(trace, list):
            trace = []

        try:
            executor = build_executor(state)
            agent_results = await executor.execute_calls(calls)
        except Exception as exc:
            logger.warning("agent execution failed: %s", exc)
            return {
                "agent_results": _agent_error_results(exc),
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
                conversation_getter=conversation_getter,
                conversation_setter=conversation_setter,
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
