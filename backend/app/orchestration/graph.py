from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    "profile_agent": "基础画像智能体",
    "learning_path_agent": "学习路径智能体",
    "course_knowledge_agent": "课程知识点规划智能体",
}


def _build_llm() -> ChatOpenAI:
    import os
    from dotenv import load_dotenv

    load_dotenv()

    return ChatOpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        temperature=0.7,
    )


def _route_after_supervisor(state: OrchestrationState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END
    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        tool_name = last_msg.tool_calls[0]["name"]
        if tool_name in {"profile_agent", "learning_path_agent", "course_knowledge_agent"}:
            return tool_name
    return END


def create_orchestration_graph(session):
    from app.orchestration.agents.supervisor import create_supervisor_node
    from app.orchestration.agents.profile import create_profile_agent_node
    from app.orchestration.agents.learning_path import create_learning_path_agent_node
    from app.orchestration.agents.course_knowledge import create_course_knowledge_agent_node

    llm = _build_llm()

    supervisor_node = create_supervisor_node(llm)
    profile_node = create_profile_agent_node(llm, session)
    learning_path_node = create_learning_path_agent_node(llm, session)
    course_knowledge_node = create_course_knowledge_agent_node(llm, session)

    builder = StateGraph(OrchestrationState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("profile_agent", profile_node)
    builder.add_node("learning_path_agent", learning_path_node)
    builder.add_node("course_knowledge_agent", course_knowledge_node)

    builder.add_edge("__start__", "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "profile_agent": "profile_agent",
            "learning_path_agent": "learning_path_agent",
            "course_knowledge_agent": "course_knowledge_agent",
            END: END,
        },
    )

    for agent_key in ["profile_agent", "learning_path_agent", "course_knowledge_agent"]:
        builder.add_edge(agent_key, "supervisor")

    graph = builder.compile(checkpointer=MemorySaver())
    return graph


async def stream_orchestration_events(
    state: OrchestrationState,
    session,
) -> AsyncGenerator[dict, None]:
    graph = create_orchestration_graph(session)
    config = {"configurable": {"thread_id": state["user_id"]}}

    try:
        async for event in graph.astream_events(state, config, version="v2"):
            kind = event.get("event", "")

            if kind == "on_chain_start":
                name = event.get("name", "")
                if name in AGENT_LABELS:
                    yield {
                        "event": "agent_started",
                        "step_id": name,
                        "agent_key": name,
                        "agent": name,
                        "label": AGENT_LABELS[name],
                        "kind": "agent",
                        "message": f"{AGENT_LABELS[name]}开始处理。",
                    }

            elif kind == "on_chain_end":
                name = event.get("name", "")
                if name in AGENT_LABELS:
                    output = event.get("data", {}).get("output", {})
                    agent_result = output.get(name.replace("_agent", "")) or output
                    is_error = (
                        not isinstance(agent_result, dict)
                        or "error" in agent_result
                    )

                    yield {
                        "event": "agent_failed" if is_error else "agent_completed",
                        "step_id": name,
                        "agent_key": name,
                        "agent": name,
                        "label": AGENT_LABELS[name],
                        "kind": "agent",
                        "message": (
                            str(agent_result.get("error", ""))
                            if is_error
                            else f"{AGENT_LABELS[name]}已完成。"
                        ),
                        "phase": "agent",
                        "depends_on": [],
                        "parallel_group": None,
                    }

                elif name == "LangGraph":
                    final_state = event.get("data", {}).get("output", state)
                    answer = _extract_answer(final_state)
                    yield {
                        "event": "completed",
                        "step_id": "supervisor",
                        "agent_key": "supervisor",
                        "agent": "supervisor",
                        "label": "主智能体",
                        "kind": "system",
                        "message": "对话完成。",
                        "state": final_state,
                        "answer": answer,
                        "completed": True,
                    }

    except Exception as exc:
        logger.exception("stream_orchestration_events failed")
        yield {
            "event": "error",
            "step_id": "supervisor",
            "agent_key": "supervisor",
            "agent": "supervisor",
            "label": "主智能体",
            "kind": "system",
            "message": str(exc) or "对话请求失败，请稍后重试。",
            "state": state,
        }


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
