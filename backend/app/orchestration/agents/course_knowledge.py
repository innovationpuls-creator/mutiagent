from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.orchestration.agent_plan import CourseKnowledgeOutlineResult
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _build_course_knowledge_chain(llm: BaseChatModel) -> Runnable:
    prompt = ChatPromptTemplate.from_messages([
        ("system", COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{query}"),
    ])
    return prompt | llm.with_structured_output(CourseKnowledgeOutlineResult)


async def run_course_knowledge_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    db_session,
) -> dict:
    from app.services.course_knowledge_service import (
        get_user_course_knowledge_outline,
        resolve_current_course_node,
        upsert_user_course_knowledge_outline,
    )
    from app.services.learning_path_service import get_user_learning_path
    from app.models import UserProfile

    user_uid = state["user_id"]

    profile = db_session.get(UserProfile, user_uid)
    if profile is None or profile.profile_data.get("type") != "basic_profile":
        return {"error": "请先完成基础画像。"}

    stored_path = get_user_learning_path(db_session, user_uid)
    if stored_path is None:
        return {"error": "请先生成学习路径。"}

    path_data = stored_path.path_data
    course_node = resolve_current_course_node(path_data)
    course_node_id = str(course_node.get("course_node_id") or "")
    if not course_node_id:
        return {"error": "当前课程节点缺少 course_node_id。"}

    existing = get_user_course_knowledge_outline(db_session, user_uid, course_node_id)
    if existing is not None:
        return {"course_knowledge": existing.outline_data}

    input_data = {
        "course_node": course_node,
        "user_profile": profile.profile_data,
        "learning_goal": path_data.get("learning_goal", {}),
        "learner_baseline": path_data.get("learner_baseline", {}),
    }
    input_text = f"请为当前课程生成个性化章节定义。\n\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"

    chain = _build_course_knowledge_chain(llm)

    try:
        result: CourseKnowledgeOutlineResult = await chain.ainvoke({"query": input_text, "history": []})
    except Exception as exc:
        logger.warning("CourseKnowledgeAgent failed: %s", exc)
        return {"error": str(exc)}

    outline_dict = result.model_dump()

    if outline_dict.get("course_node_id") != course_node_id:
        return {"error": "生成的课程章节 node_id 不匹配。"}

    upsert_user_course_knowledge_outline(db_session, user_uid, outline_dict)
    return {"course_knowledge": outline_dict}


def _extract_last_tool_call_id(state: OrchestrationState) -> str | None:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("id")
    return None


def create_course_knowledge_agent_node(llm: BaseChatModel, db_session):
    async def course_knowledge_node(state: OrchestrationState) -> dict:
        agent_result = await run_course_knowledge_agent(state, llm, db_session)

        tool_call_id = _extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        return {
            "course_knowledge": agent_result.get("course_knowledge"),
            "messages": [tool_message],
        }

    return course_knowledge_node
