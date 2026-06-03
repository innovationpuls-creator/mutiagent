from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.orchestration.llm import get_supervisor_llm, get_worker_llm
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    "profile_agent": "基础画像智能体",
    "learning_path_agent": "学习路径智能体",
    "course_knowledge_agent": "课程知识点规划智能体",
}

WORKER_AGENTS = {"profile_agent", "learning_path_agent", "course_knowledge_agent"}
SUPERVISOR_NODE = "supervisor"

# ── Module-level singleton ────────────────────────────────────────────────
_compiled_graph = None
_memory_saver = None


def _route_after_supervisor(state: OrchestrationState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END
    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        tool_name = last_msg.tool_calls[0]["name"]
        if tool_name in WORKER_AGENTS:
            return tool_name
    return END


def _route_after_worker(state: OrchestrationState) -> str:
    """After worker runs: skip supervisor re-invocation when the result is final.

    - profile collecting → END directly (user needs to answer)
    - learning_path / course_knowledge produced data → END directly (saves one LLM call)
    - otherwise → back to supervisor for further orchestration
    """
    profile = state.get("profile", {})
    if isinstance(profile, dict) and profile.get("type") == "collecting":
        return END

    # If learning_path or course_knowledge just produced output, skip supervisor
    if state.get("learning_path") is not None:
        return END
    if state.get("course_knowledge") is not None:
        return END

    return SUPERVISOR_NODE


def get_orchestration_graph():
    """Return the singleton compiled graph, building it on first call."""
    global _compiled_graph, _memory_saver

    if _compiled_graph is not None:
        return _compiled_graph

    from app.orchestration.agents.supervisor import create_supervisor_node
    from app.orchestration.agents.profile import create_profile_agent_node
    from app.orchestration.agents.learning_path import create_learning_path_agent_node
    from app.orchestration.agents.course_knowledge import create_course_knowledge_agent_node

    supervisor_llm = get_supervisor_llm()
    worker_llm = get_worker_llm()

    supervisor_node = create_supervisor_node(supervisor_llm)
    profile_node = create_profile_agent_node(supervisor_llm)  # profile uses shorter timeout
    learning_path_node = create_learning_path_agent_node(worker_llm)
    course_knowledge_node = create_course_knowledge_agent_node(worker_llm)

    builder = StateGraph(OrchestrationState)

    builder.add_node(SUPERVISOR_NODE, supervisor_node)
    builder.add_node("profile_agent", profile_node)
    builder.add_node("learning_path_agent", learning_path_node)
    builder.add_node("course_knowledge_agent", course_knowledge_node)

    builder.add_edge("__start__", SUPERVISOR_NODE)

    builder.add_conditional_edges(
        SUPERVISOR_NODE,
        _route_after_supervisor,
        {
            "profile_agent": "profile_agent",
            "learning_path_agent": "learning_path_agent",
            "course_knowledge_agent": "course_knowledge_agent",
            END: END,
        },
    )

    for agent_key in WORKER_AGENTS:
        builder.add_conditional_edges(
            agent_key,
            _route_after_worker,
            {SUPERVISOR_NODE: SUPERVISOR_NODE, END: END},
        )

    _memory_saver = MemorySaver()
    _compiled_graph = builder.compile(checkpointer=_memory_saver)
    logger.info("Orchestration graph compiled (singleton)")
    return _compiled_graph


async def stream_orchestration_events(
    state: OrchestrationState,
) -> AsyncGenerator[dict, None]:
    graph = get_orchestration_graph()
    config = {"configurable": {"thread_id": state["user_id"]}}

    current_agent_node: str | None = None
    active_tool_calls: dict[str, str] = {}
    message_started_sent = False
    supervisor_in_tool_calling = False

    def _emit(event_name: str, **kwargs: object) -> dict:
        return {"event": event_name, **kwargs}

    try:
        yield _emit(
            "orchestration_started",
            session_id=state.get("session_id", ""),
            query=state.get("query", ""),
        )

        if state.get("profile"):
            yield _emit(
                "context_loaded",
                key="profile",
                message="已加载历史学习画像。",
            )
        if state.get("learning_path"):
            yield _emit(
                "context_loaded",
                key="learning_path",
                message="已加载历史学习路径。",
            )

        async for event in graph.astream_events(state, config, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chain_start":
                if name in AGENT_LABELS:
                    current_agent_node = name
                    yield _emit(
                        "agent_started",
                        step_id=name,
                        agent_key=name,
                        agent=name,
                        label=AGENT_LABELS[name],
                        kind="agent",
                        message=f"{AGENT_LABELS[name]}开始处理。",
                    )
                    yield _emit(
                        "data_schema_started",
                        step_id=name,
                        schema_name=_schema_name_for_agent(name),
                        label=AGENT_LABELS[name],
                    )
                elif name == SUPERVISOR_NODE:
                    current_agent_node = SUPERVISOR_NODE
                    supervisor_in_tool_calling = False
                    message_started_sent = False

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue

                content = chunk.content if hasattr(chunk, "content") else ""
                tool_call_chunks = chunk.tool_call_chunks if hasattr(chunk, "tool_call_chunks") else []

                if current_agent_node == SUPERVISOR_NODE:
                    if tool_call_chunks:
                        for tc in tool_call_chunks:
                            tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                            tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                            tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", "")

                            if tc_id and tc_id not in active_tool_calls:
                                active_tool_calls[tc_id] = tc_name or "unknown"
                                yield _emit(
                                    "tool_call_started",
                                    step_id=current_agent_node,
                                    tool_name=tc_name,
                                    label=f"调用 {AGENT_LABELS.get(tc_name, tc_name or '未知工具')}",
                                )
                                supervisor_in_tool_calling = True

                            if tc_args:
                                yield _emit(
                                    "thought_chunk",
                                    step_id=current_agent_node,
                                    chunk=str(tc_args),
                                )
                    elif content:
                        if not supervisor_in_tool_calling:
                            if not message_started_sent:
                                yield _emit(
                                    "message_started",
                                    step_id=current_agent_node,
                                    role="assistant",
                                )
                                message_started_sent = True
                            yield _emit(
                                "text_chunk",
                                step_id=current_agent_node,
                                chunk=str(content),
                            )
                        else:
                            yield _emit(
                                "thought_chunk",
                                step_id=current_agent_node,
                                chunk=str(content),
                            )

                elif current_agent_node in WORKER_AGENTS and content:
                    yield _emit(
                        "data_chunk",
                        step_id=current_agent_node,
                        partial_data=str(content),
                    )

            elif kind == "on_chain_end":
                if name in AGENT_LABELS:
                    output = event.get("data", {}).get("output", {})
                    agent_result = output.get(name.replace("_agent", "")) or output
                    is_error = (
                        not isinstance(agent_result, dict)
                        or "error" in agent_result
                    )

                    yield _emit(
                        "agent_failed" if is_error else "agent_completed",
                        step_id=name,
                        agent_key=name,
                        agent=name,
                        label=AGENT_LABELS[name],
                        kind="agent",
                        message=(
                            str(agent_result.get("error", ""))
                            if is_error
                            else f"{AGENT_LABELS[name]}已完成。"
                        ),
                        phase="agent",
                        depends_on=[],
                        parallel_group=None,
                    )

                    final_data = agent_result.get(name.replace("_agent", ""), agent_result) if not is_error else None
                    yield _emit(
                        "data_completed",
                        step_id=name,
                        final_data=final_data,
                    )

                    for tc_id in list(active_tool_calls.keys()):
                        yield _emit(
                            "tool_call_completed",
                            step_id=name,
                            tool_name=active_tool_calls.pop(tc_id),
                            output="执行完毕",
                        )

                    current_agent_node = None

                elif name == "LangGraph":
                    final_state = event.get("data", {}).get("output", state)
                    answer = _extract_answer(final_state)
                    yield _emit(
                        "completed",
                        step_id=SUPERVISOR_NODE,
                        agent_key=SUPERVISOR_NODE,
                        agent=SUPERVISOR_NODE,
                        label="主智能体",
                        kind="system",
                        message="对话完成。",
                        state=final_state,
                        answer=answer,
                        completed=True,
                    )
                    current_agent_node = None

    except Exception as exc:
        logger.exception("stream_orchestration_events failed")
        yield _emit(
            "error",
            step_id=SUPERVISOR_NODE,
            agent_key=SUPERVISOR_NODE,
            agent=SUPERVISOR_NODE,
            label="主智能体",
            kind="system",
            message=str(exc) or "对话请求失败，请稍后重试。",
            state=state,
        )


def _schema_name_for_agent(agent_key: str) -> str:
    mapping = {
        "profile_agent": "ProfileAgentOutput",
        "learning_path_agent": "LearningPathResult",
        "course_knowledge_agent": "CourseKnowledgeOutlineResult",
    }
    return mapping.get(agent_key, "UnknownSchema")


def _extract_answer(state: dict) -> dict:
    response = state.get("response", "")
    question_box = state.get("question_box")
    answer = state.get("answer")

    if isinstance(answer, dict) and answer.get("user_message"):
        return answer

    profile = state.get("profile", {})
    if isinstance(profile, dict) and profile.get("question_mode"):
        qm = profile.get("question_md", "")
        qb = profile.get("question_box", {})
        return {
            "user_message": qm or profile.get("text", response) or "",
            "question_box": _normalize_question_box(qb),
        }

    return {"user_message": response or "", "question_box": question_box}


def _normalize_question_box(qb: dict) -> dict | None:
    if not qb or not qb.get("question"):
        return None
    options = qb.get("options", [])
    if isinstance(options, list) and options and isinstance(options[0], str):
        options = [
            {"label": o, "value": o, "description": "", "target_fields": [], "fills": {}}
            for o in options
        ]
    return {"question": qb["question"], "options": options}
