from __future__ import annotations

import json
import logging
import re

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from collections.abc import AsyncGenerator

from app.orchestration.dify_client import DIFY_INTENT_RECOGNITION_API_KEY, DIFY_PROFILE_AGENT_API_KEY, DifyClient
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

PROFILE_AGENT_INTENT = "profile_agent"
INTENT_AGENT_KEY = "intent_recognition_agent"
PROFILE_AGENT_KEY = "profile_agent"
SUPPORTED_INTENTS = {
    "profile_agent",
    "learning_path_agent",
    "course_knowledge_agent",
    "learning_resource_agent",
    "dynamic_update_agent",
    "chat",
}

AGENT_LABELS = {
    INTENT_AGENT_KEY: "意图识别智能体",
    PROFILE_AGENT_KEY: "基础画像智能体",
    "learning_path_agent": "学习路径智能体",
    "course_knowledge_agent": "课程知识智能体",
    "learning_resource_agent": "资源推荐智能体",
    "dynamic_update_agent": "动态更新智能体",
    "chat": "日常对话智能体",
}


def _parse_answer(raw: dict) -> dict:
    raw_answer = raw.get("answer", "")
    if not isinstance(raw_answer, str):
        return {"type": "unknown", "text": str(raw_answer)}

    cleaned = raw_answer.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        logger.warning("answer is not valid JSON: %s", cleaned[:200])
        return {"type": "unknown", "text": raw_answer}


def _parse_intent(raw: dict) -> str:
    raw_answer = str(raw.get("answer", "")).strip()
    intent = raw_answer.splitlines()[0].strip().strip("`").strip()
    if intent in SUPPORTED_INTENTS:
        return intent
    logger.warning("unknown intent response: %s", raw_answer[:200])
    return "chat"


async def _call_intent_dify(state: OrchestrationState, client: DifyClient) -> dict:
    logger.info(
        "calling intent Dify: query=%s conv_id=%s",
        state["query"][:50],
        state.get("intent_conversation_id", ""),
    )
    response = await client.chat_blocking(
        query=state["query"],
        user_id=state["user_id"],
        conversation_id=state.get("intent_conversation_id", ""),
    )
    intent = _parse_intent(response.raw)
    has_active_profile_conversation = bool(state.get("conversation_id"))
    return {
        "intent_raw": response.raw,
        "intent_conversation_id": response.conversation_id,
        "intent": intent,
        "route_status": "supported" if intent == PROFILE_AGENT_INTENT or has_active_profile_conversation else "unsupported",
    }


def _route_by_intent(state: OrchestrationState) -> str:
    if state.get("intent") == PROFILE_AGENT_INTENT or state.get("conversation_id"):
        return "profile"
    return "unsupported"


async def _call_profile_dify(state: OrchestrationState, client: DifyClient) -> dict:
    logger.info("calling profile Dify: query=%s conv_id=%s", state["query"][:50], state["conversation_id"])
    response = await client.chat_blocking(
        query=state["query"],
        user_id=state["user_id"],
        conversation_id=state.get("conversation_id", ""),
    )
    return {
        "dify_raw": response.raw,
        "conversation_id": response.conversation_id,
    }


async def _parse_response(state: OrchestrationState) -> dict:
    raw = state.get("dify_raw", {})
    parsed = _parse_answer(raw)
    logger.info(
        "parsed response: type=%s stage=%s",
        parsed.get("type"),
        parsed.get("stage"),
    )
    return {"answer_json": parsed}


async def _check_completion(state: OrchestrationState) -> dict:
    aj = state.get("answer_json", {})
    if aj.get("type") == "basic_profile" and aj.get("stage") == "generated":
        return {"phase": "completed"}
    return {"phase": "collecting"}


async def _unsupported_route(state: OrchestrationState) -> dict:
    return {
        "phase": "unsupported",
        "answer_json": {},
        "error": "当前仅支持基础画像对话，请告诉我你的年级、专业、学习偏好或学习目标。",
    }


async def stream_orchestration_events(
    state: OrchestrationState,
    profile_client: DifyClient | None = None,
    intent_client: DifyClient | None = None,
) -> AsyncGenerator[dict, None]:
    profile = profile_client or DifyClient(api_key=DIFY_PROFILE_AGENT_API_KEY)
    intent = intent_client or DifyClient(api_key=DIFY_INTENT_RECOGNITION_API_KEY)

    yield {
        "event": "agent_started",
        "agent": INTENT_AGENT_KEY,
        "label": AGENT_LABELS[INTENT_AGENT_KEY],
        "message": "正在判断这次对话应该交给哪个智能体。",
    }
    intent_update = await _call_intent_dify(state, intent)
    state.update(intent_update)
    yield {
        "event": "agent_completed",
        "agent": INTENT_AGENT_KEY,
        "label": AGENT_LABELS[INTENT_AGENT_KEY],
        "intent": state.get("intent", ""),
        "route_status": state.get("route_status", ""),
        "message": "意图识别完成。",
    }

    route = _route_by_intent(state)
    routed_agent = PROFILE_AGENT_KEY if route == "profile" else state.get("intent", "chat")
    yield {
        "event": "route_decided",
        "agent": routed_agent,
        "label": AGENT_LABELS.get(routed_agent, routed_agent),
        "intent": state.get("intent", ""),
        "route_status": state.get("route_status", ""),
        "message": "路由已完成，准备进入具体智能体。",
    }

    if route == "unsupported":
        state.update(await _unsupported_route(state))
        yield {
            "event": "completed",
            "agent": routed_agent,
            "label": AGENT_LABELS.get(routed_agent, routed_agent),
            "state": state,
            "answer": state.get("answer_json", {}),
            "completed": False,
            "phase": state.get("phase", ""),
            "error": state.get("error", ""),
        }
        return

    yield {
        "event": "agent_started",
        "agent": PROFILE_AGENT_KEY,
        "label": AGENT_LABELS[PROFILE_AGENT_KEY],
        "message": "正在整理基础画像信息。",
    }
    profile_update = await _call_profile_dify(state, profile)
    state.update(profile_update)
    yield {
        "event": "agent_completed",
        "agent": PROFILE_AGENT_KEY,
        "label": AGENT_LABELS[PROFILE_AGENT_KEY],
        "message": "基础画像智能体已返回结果。",
    }

    state.update(await _parse_response(state))
    state.update(await _check_completion(state))
    yield {
        "event": "completed",
        "agent": PROFILE_AGENT_KEY,
        "label": AGENT_LABELS[PROFILE_AGENT_KEY],
        "state": state,
        "answer": state.get("answer_json", {}),
        "completed": state.get("phase") == "completed",
        "phase": state.get("phase", ""),
    }


def create_orchestration_graph(
    profile_client: DifyClient | None = None,
    intent_client: DifyClient | None = None,
) -> StateGraph:
    profile = profile_client or DifyClient(api_key=DIFY_PROFILE_AGENT_API_KEY)
    intent = intent_client or DifyClient(api_key=DIFY_INTENT_RECOGNITION_API_KEY)

    async def call_intent_dify(state: OrchestrationState) -> dict:
        return await _call_intent_dify(state, intent)

    async def call_profile_dify(state: OrchestrationState) -> dict:
        return await _call_profile_dify(state, profile)

    builder = StateGraph(OrchestrationState)
    builder.add_node("call_intent_dify", call_intent_dify)
    builder.add_node("call_profile_dify", call_profile_dify)
    builder.add_node("parse_response", _parse_response)
    builder.add_node("check_completion", _check_completion)
    builder.add_node("unsupported_route", _unsupported_route)

    builder.set_entry_point("call_intent_dify")
    builder.add_conditional_edges(
        "call_intent_dify",
        _route_by_intent,
        {
            "profile": "call_profile_dify",
            "unsupported": "unsupported_route",
        },
    )
    builder.add_edge("call_profile_dify", "parse_response")
    builder.add_edge("parse_response", "check_completion")
    builder.add_edge("check_completion", END)
    builder.add_edge("unsupported_route", END)

    return builder.compile(checkpointer=MemorySaver())
