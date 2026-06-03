from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from app.orchestration.agents.supervisor import create_supervisor_node
from app.orchestration.agents.profile import create_profile_agent_node
from app.orchestration.agents.learning_path import create_learning_path_agent_node
from app.orchestration.agents.course_knowledge import create_course_knowledge_agent_node
from app.orchestration.llm import get_supervisor_llm, get_worker_llm
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    "profile_agent": "画像智能体",
    "learning_path_agent": "学习路径智能体",
    "course_knowledge_agent": "课程大纲智能体",
}

WORKER_AGENTS = {"profile_agent", "learning_path_agent", "course_knowledge_agent"}
SUPERVISOR_NODE = "supervisor"

_graph = None


def route_after_supervisor(state: OrchestrationState) -> str:
    """Route based on the last message's tool_calls — ~8 lines total."""
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        tool_name = last_msg.tool_calls[0]["name"]
        if tool_name in WORKER_AGENTS:
            return tool_name
    return END


def build_orchestration_graph():
    """Build and return the compiled LangGraph — no checkpoint."""
    global _graph
    if _graph is not None:
        return _graph

    supervisor_llm = get_supervisor_llm()
    worker_llm = get_worker_llm()

    supervisor_node = create_supervisor_node(supervisor_llm)
    profile_node = create_profile_agent_node(supervisor_llm)
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
        route_after_supervisor,
        {
            "profile_agent": "profile_agent",
            "learning_path_agent": "learning_path_agent",
            "course_knowledge_agent": "course_knowledge_agent",
            END: END,
        },
    )

    # All workers route back to supervisor for further decision-making
    for worker in WORKER_AGENTS:
        builder.add_edge(worker, SUPERVISOR_NODE)

    _graph = builder.compile()
    logger.info("Orchestration graph compiled (no checkpoint)")
    return _graph


# ── SSE streaming ────────────────────────────────────────────────────────

def _emit(event_name: str, **kwargs: object) -> dict:
    return {"event": event_name, **kwargs}


async def stream_orchestration_events(
    state: OrchestrationState,
) -> AsyncGenerator[dict, None]:
    """Stream LangGraph execution as fine-grained SSE events."""
    graph = build_orchestration_graph()

    current_agent: str | None = None
    supervisor_streaming_text = ""

    try:
        yield _emit(
            "session_started",
            session_id=state.get("session_id", ""),
            query=state.get("query", ""),
        )

        yield _emit(
            "supervisor_thinking",
            message="正在分析你的需求...",
        )

        # Pre-loaded context notifications
        if state.get("profile"):
            yield _emit(
                "data_update",
                update_type="profile_loaded",
                summary="已加载历史学习画像",
            )
        if state.get("year_learning_paths"):
            paths = state["year_learning_paths"]
            yield _emit(
                "data_update",
                update_type="paths_loaded",
                years=list(paths.keys()),
                summary=f"已加载 {len(paths)} 个年级的学习路径",
            )

        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chain_start":
                if name in AGENT_LABELS:
                    current_agent = name

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue

                content = chunk.content if hasattr(chunk, "content") else ""
                tool_call_chunks = (
                    chunk.tool_call_chunks if hasattr(chunk, "tool_call_chunks") else []
                )

                if name == SUPERVISOR_NODE:
                    if tool_call_chunks:
                        for tc in tool_call_chunks:
                            tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                            tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", "")
                            if tc_name:
                                yield _emit(
                                    "supervisor_plan",
                                    agent=tc_name,
                                    label=AGENT_LABELS.get(tc_name, tc_name),
                                    reason=f"调用 {AGENT_LABELS.get(tc_name, tc_name)}",
                                )
                                yield _emit(
                                    "agent_calling",
                                    agent=tc_name,
                                    label=AGENT_LABELS.get(tc_name, tc_name),
                                    args=str(tc_args)[:200],
                                )
                    elif content:
                        supervisor_streaming_text += str(content)
                        yield _emit(
                            "text_chunk",
                            chunk=str(content),
                        )

            elif kind == "on_chain_end":
                if name in AGENT_LABELS:
                    output = event.get("data", {}).get("output", {})
                    agent_key = name.replace("_agent", "")

                    has_error = False
                    error_msg = ""
                    # Check messages for error in ToolMessage
                    for msg in reversed(output.get("messages", [])):
                        from langchain_core.messages import ToolMessage
                        if isinstance(msg, ToolMessage):
                            try:
                                import json
                                data = json.loads(str(msg.content)) if isinstance(msg.content, str) else msg.content
                                if isinstance(data, dict) and data.get("error"):
                                    has_error = True
                                    error_msg = data["error"]
                            except Exception:
                                pass
                            break

                    if has_error:
                        yield _emit(
                            "agent_result",
                            agent=name,
                            label=AGENT_LABELS.get(name, name),
                            success=False,
                            error=error_msg,
                        )
                    else:
                        yield _emit(
                            "agent_progress",
                            agent=name,
                            message=f"{AGENT_LABELS.get(name, name)}已完成",
                        )
                        yield _emit(
                            "agent_result",
                            agent=name,
                            label=AGENT_LABELS.get(name, name),
                            success=True,
                            summary=f"{AGENT_LABELS.get(name, name)}结果已生成",
                        )

                    current_agent = None

                elif name == "LangGraph":
                    final_state = event.get("data", {}).get("output", state)
                    yield _emit(
                        "message_completed",
                        full_text=final_state.get("response", supervisor_streaming_text),
                    )
                    yield _emit(
                        "session_completed",
                        session_id=state.get("session_id", ""),
                        has_profile=bool(final_state.get("profile")),
                        has_paths=bool(final_state.get("year_learning_paths")),
                        has_outline=bool(final_state.get("course_knowledge")),
                    )

    except Exception as exc:
        logger.exception("stream_orchestration_events failed")
        yield _emit(
            "error",
            message=str(exc) or "对话请求失败，请稍后重试。",
            recoverable=True,
        )
