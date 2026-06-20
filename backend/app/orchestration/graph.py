from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from app.orchestration.agents.course_knowledge import create_course_knowledge_agent_node
from app.orchestration.agents.course_resources import (
    create_section_html_animation_agent_node,
    create_section_markdown_agent_node,
    create_section_video_search_agent_node,
)
from app.orchestration.agents.learning_path import create_learning_path_agent_node
from app.orchestration.agents.learning_path_intake import (
    create_learning_path_intake_agent_node,
)
from app.orchestration.agents.profile import (
    create_profile_agent_node,
    is_complete_profile_data,
)
from app.orchestration.agents.supervisor import create_supervisor_node
from app.orchestration.llm import (
    get_search_worker_llm,
    get_supervisor_llm,
    get_thinking_worker_llm,
    get_worker_llm,
)
from app.orchestration.rule_engine import (
    _extract_last_tool_agent,
    is_course_resource_generation_query,
    should_auto_continue_learning_path_after_profile,
)
from app.orchestration.state import OrchestrationState
from app.services.learning_path_service import get_preferred_year_learning_path

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    "profile_agent": "画像智能体",
    "learning_path_intake_agent": "课程草案智能体",
    "learning_path_agent": "学习路径智能体",
    "course_knowledge_agent": "课程大纲智能体",
    "section_markdown_agent": "小节文档智能体",
    "section_video_search_agent": "视频搜索智能体",
    "section_html_animation_agent": "HTML 动画智能体",
}

WORKER_AGENTS = {
    "profile_agent",
    "learning_path_intake_agent",
    "learning_path_agent",
    "course_knowledge_agent",
    "section_markdown_agent",
    "section_video_search_agent",
    "section_html_animation_agent",
}
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


def route_after_worker(state: OrchestrationState) -> str:
    """Allow profile update to hand off to learning-path refresh when required."""
    last_agent = _extract_last_tool_agent(state)
    if (
        last_agent == "course_knowledge_agent"
        and is_course_resource_generation_query(str(state.get("query", "")))
        and isinstance(state.get("course_knowledge"), dict)
    ):
        return SUPERVISOR_NODE

    resource_plan = state.get("course_resource_plan")
    if isinstance(resource_plan, dict) and not isinstance(
        state.get("course_resource_result"), dict
    ):
        target_section_ids = resource_plan.get("target_section_ids")
        video_section_ids = resource_plan.get("video_section_ids")
        animation_section_ids = resource_plan.get("animation_section_ids")
        if (
            isinstance(target_section_ids, list)
            and target_section_ids
            and not video_section_ids
        ):
            return "section_video_search_agent"
        if (
            isinstance(target_section_ids, list)
            and target_section_ids
            and video_section_ids
            and not animation_section_ids
        ):
            return "section_html_animation_agent"

    if isinstance(state.get("course_resource_result"), dict):
        return END

    if (
        last_agent == "profile_agent"
        and is_complete_profile_data(state.get("profile"))
        and not state.get("year_learning_paths")
    ):
        return SUPERVISOR_NODE

    intake = state.get("learning_path_intake")
    if (
        last_agent == "learning_path_intake_agent"
        and isinstance(intake, dict)
        and intake.get("status") == "confirmed"
    ):
        return SUPERVISOR_NODE

    if should_auto_continue_learning_path_after_profile(state):
        return SUPERVISOR_NODE
    return END


def build_orchestration_graph():
    """Build and return the compiled LangGraph — no checkpoint."""
    global _graph
    if _graph is not None:
        return _graph

    supervisor_llm = get_supervisor_llm()
    worker_llm = get_worker_llm()
    thinking_worker_llm = get_thinking_worker_llm()
    search_worker_llm = get_search_worker_llm()
    learning_path_llm = (
        worker_llm
        if hasattr(worker_llm, "with_structured_output")
        else thinking_worker_llm
    )
    learning_path_intake_llm = (
        worker_llm
        if hasattr(worker_llm, "with_structured_output")
        else thinking_worker_llm
    )

    supervisor_node = create_supervisor_node(supervisor_llm)
    profile_node = create_profile_agent_node(supervisor_llm)
    learning_path_intake_node = create_learning_path_intake_agent_node(
        learning_path_intake_llm
    )
    learning_path_node = create_learning_path_agent_node(learning_path_llm)
    course_knowledge_node = create_course_knowledge_agent_node(worker_llm)
    section_markdown_node = create_section_markdown_agent_node(worker_llm)
    section_video_search_node = create_section_video_search_agent_node(
        search_worker_llm
    )
    section_html_animation_node = create_section_html_animation_agent_node(worker_llm)

    builder = StateGraph(OrchestrationState)

    builder.add_node(SUPERVISOR_NODE, supervisor_node)
    builder.add_node("profile_agent", profile_node)
    builder.add_node("learning_path_intake_agent", learning_path_intake_node)
    builder.add_node("learning_path_agent", learning_path_node)
    builder.add_node("course_knowledge_agent", course_knowledge_node)
    builder.add_node("section_markdown_agent", section_markdown_node)
    builder.add_node("section_video_search_agent", section_video_search_node)
    builder.add_node("section_html_animation_agent", section_html_animation_node)

    builder.add_edge("__start__", SUPERVISOR_NODE)

    builder.add_conditional_edges(
        SUPERVISOR_NODE,
        route_after_supervisor,
        {
            "profile_agent": "profile_agent",
            "learning_path_intake_agent": "learning_path_intake_agent",
            "learning_path_agent": "learning_path_agent",
            "course_knowledge_agent": "course_knowledge_agent",
            "section_markdown_agent": "section_markdown_agent",
            "section_video_search_agent": "section_video_search_agent",
            "section_html_animation_agent": "section_html_animation_agent",
            END: END,
        },
    )

    for worker in WORKER_AGENTS:
        builder.add_conditional_edges(
            worker,
            route_after_worker,
            {
                SUPERVISOR_NODE: SUPERVISOR_NODE,
                "section_video_search_agent": "section_video_search_agent",
                "section_html_animation_agent": "section_html_animation_agent",
                END: END,
            },
        )

    _graph = builder.compile()
    logger.info("Orchestration graph compiled (no checkpoint)")
    return _graph


# ── SSE streaming ────────────────────────────────────────────────────────


def _emit(event_name: str, **kwargs: object) -> dict:
    return {"event": event_name, **kwargs}


def _is_hard_agent_error(payload: dict) -> bool:
    return bool(payload.get("hard_error")) and bool(payload.get("error"))


def _event_for_agent_error(agent: str, message: str) -> dict:
    event = {
        "event": "error",
        "agent": agent,
        "label": AGENT_LABELS.get(agent, agent),
        "message": message,
        "recoverable": True,
        "retryable": False,
    }
    if agent == "learning_path_agent":
        event["retryable"] = True
        event["retryAction"] = "retry_learning_path"
    return event


def _extract_current_learning_course(
    final_state: dict[str, Any],
) -> dict[str, Any] | None:
    year_learning_path = final_state.get("year_learning_path")
    if isinstance(year_learning_path, dict):
        current_learning_course = year_learning_path.get("current_learning_course")
        if isinstance(current_learning_course, dict):
            return current_learning_course

    year_learning_paths = final_state.get("year_learning_paths")
    if not isinstance(year_learning_paths, dict):
        return None

    latest_grade_year = final_state.get("latest_grade_year")
    if isinstance(latest_grade_year, str):
        preferred_path = get_preferred_year_learning_path(
            year_learning_paths, latest_grade_year
        )
        if isinstance(preferred_path, dict):
            current_learning_course = preferred_path.get("current_learning_course")
            if isinstance(current_learning_course, dict):
                return current_learning_course

    grade_year = final_state.get("grade_year")
    if isinstance(grade_year, str):
        scoped_path = year_learning_paths.get(grade_year)
        if isinstance(scoped_path, dict):
            current_learning_course = scoped_path.get("current_learning_course")
            if isinstance(current_learning_course, dict):
                return current_learning_course

    for path in year_learning_paths.values():
        if not isinstance(path, dict):
            continue
        current_learning_course = path.get("current_learning_course")
        if isinstance(current_learning_course, dict):
            return current_learning_course

    return None


def _has_learning_paths(final_state: dict[str, Any]) -> bool:
    year_learning_paths = final_state.get("year_learning_paths")
    if isinstance(year_learning_paths, dict) and year_learning_paths:
        return True

    learning_path = final_state.get("learning_path")
    if isinstance(learning_path, dict) and learning_path:
        return True

    year_learning_path = final_state.get("year_learning_path")
    return isinstance(year_learning_path, dict) and bool(year_learning_path)


def _has_course_knowledge(final_state: dict[str, Any]) -> bool:
    course_knowledge = final_state.get("course_knowledge")
    return isinstance(course_knowledge, dict) and bool(course_knowledge)


async def _iter_graph_events_with_idle_status(
    graph_events: AsyncGenerator[dict, None],
    idle_timeout_seconds: float,
) -> AsyncGenerator[dict, None]:
    iterator = graph_events.__aiter__()
    pending = asyncio.create_task(iterator.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=idle_timeout_seconds)
            if not done:
                yield {"event": "__idle_timeout__"}
                continue

            try:
                event = pending.result()
            except StopAsyncIteration:
                break

            yield event
            pending = asyncio.create_task(iterator.__anext__())
    finally:
        if not pending.done():
            pending.cancel()


def _final_response_from_state(
    final_state: dict[str, Any], supervisor_streaming_text: str
) -> str:
    response = final_state.get("response")
    if isinstance(response, str) and response.strip():
        return response.strip()

    profile = final_state.get("profile")
    if isinstance(profile, dict) and profile.get("type") == "collecting":
        question_md = profile.get("question_md")
        if isinstance(question_md, str) and question_md.strip():
            return question_md.strip()
        text = profile.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    if supervisor_streaming_text.strip():
        return supervisor_streaming_text.strip()

    course_knowledge = final_state.get("course_knowledge")
    course_knowledges = final_state.get("course_knowledges")
    if isinstance(course_knowledges, list) and course_knowledges:
        count = len([item for item in course_knowledges if isinstance(item, dict)])
        if count > 1:
            return f"本年级 {count} 门课程的章节大纲已生成。"

    if isinstance(course_knowledge, dict):
        course_name = course_knowledge.get("course_name")
        personalization_summary = course_knowledge.get("personalization_summary")
        parts: list[str] = []
        if isinstance(course_name, str) and course_name.strip():
            parts.append(f"课程大纲已生成：《{course_name.strip()}》")
        if isinstance(personalization_summary, str) and personalization_summary.strip():
            parts.append(personalization_summary.strip())
        if parts:
            return "，".join(parts) + "。"

    current_learning_course = _extract_current_learning_course(final_state)
    if isinstance(current_learning_course, dict):
        theme = current_learning_course.get("course_or_chapter_theme")
        next_action = current_learning_course.get("next_action")
        clauses = ["学习路径已生成"]
        if isinstance(theme, str) and theme.strip():
            clauses.append(f"当前建议先学习《{theme.strip()}》")
        if isinstance(next_action, str) and next_action.strip():
            clauses.append(f"下一步：{next_action.strip()}")
        return "，".join(clauses) + "。"

    profile = final_state.get("profile")
    if isinstance(profile, dict):
        for key in ("text", "summary_text"):
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


async def stream_orchestration_events(
    state: OrchestrationState,
    idle_timeout_seconds: float = 8.0,
) -> AsyncGenerator[dict, None]:
    """Stream LangGraph execution as fine-grained SSE events."""
    graph = build_orchestration_graph()

    current_agent: str | None = None
    supervisor_streaming_text = ""
    generated_paths_this_turn = False
    generated_outline_this_turn = False
    announced_agents: set[str] = set()

    try:
        yield _emit(
            "agent_calling",
            stepId="intent-routing",
            kind="route",
            agent="intent_agent",
            label="意图识别智能体",
            message="正在判断本轮要调用的智能体",
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

        graph_events = graph.astream_events(state, version="v2")
        async for event in _iter_graph_events_with_idle_status(
            graph_events, idle_timeout_seconds
        ):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "__idle_timeout__":
                yield _emit(
                    "supervisor_thinking",
                    message="仍在处理，请稍等一下...",
                )
                continue

            if kind == "on_chain_start":
                if name in AGENT_LABELS:
                    current_agent = name
                    if name not in announced_agents:
                        announced_agents.add(name)
                        yield _emit(
                            "agent_calling",
                            agent=name,
                            label=AGENT_LABELS.get(name, name),
                            message=f"{AGENT_LABELS.get(name, name)}开始处理本轮请求",
                        )

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue

                content = chunk.content if hasattr(chunk, "content") else ""
                tool_call_chunks = (
                    chunk.tool_call_chunks if hasattr(chunk, "tool_call_chunks") else []
                )

                if name == SUPERVISOR_NODE or current_agent == SUPERVISOR_NODE:
                    if tool_call_chunks:
                        for tc in tool_call_chunks:
                            tc_name = (
                                tc.get("name")
                                if isinstance(tc, dict)
                                else getattr(tc, "name", None)
                            )
                            tc_args = (
                                tc.get("args")
                                if isinstance(tc, dict)
                                else getattr(tc, "args", "")
                            )
                            if tc_name:
                                announced_agents.add(tc_name)
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

                                data = (
                                    json.loads(str(msg.content))
                                    if isinstance(msg.content, str)
                                    else msg.content
                                )
                                if isinstance(data, dict) and _is_hard_agent_error(
                                    data
                                ):
                                    yield _emit(
                                        "agent_result",
                                        stepId=f"{name}-result",
                                        kind="agent",
                                        agent=name,
                                        label=AGENT_LABELS.get(name, name),
                                        success=False,
                                        error=str(data["error"]),
                                    )
                                    yield _event_for_agent_error(
                                        name, str(data["error"])
                                    )
                                    return
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
                        if name == "learning_path_agent":
                            generated_paths_this_turn = True
                        if name == "course_knowledge_agent":
                            generated_outline_this_turn = True
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
                        full_text=_final_response_from_state(
                            final_state, supervisor_streaming_text
                        ),
                    )
                    yield _emit(
                        "session_completed",
                        session_id=state.get("session_id", ""),
                        has_profile=is_complete_profile_data(
                            final_state.get("profile")
                        ),
                        has_paths=_has_learning_paths(final_state),
                        has_outline=_has_course_knowledge(final_state),
                    )

    except Exception as exc:
        logger.exception("stream_orchestration_events failed")
        yield _emit(
            "error",
            message=str(exc) or "对话请求失败，请稍后重试。",
            recoverable=True,
        )
