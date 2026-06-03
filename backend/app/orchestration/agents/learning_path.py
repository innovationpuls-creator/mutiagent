from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.orchestration.agent_plan import LearningPathResult, normalize_learning_path_result_payload
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _build_learning_path_chain(llm: BaseChatModel) -> Runnable:
    prompt = ChatPromptTemplate.from_messages([
        ("system", LEARNING_PATH_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{query}"),
    ])
    return prompt | llm.with_structured_output(LearningPathResult)


async def run_learning_path_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    db_session,
) -> dict:
    profile_data = state.get("profile", {})
    if not profile_data or profile_data.get("type") != "basic_profile":
        return {"error": "请先完成基础画像，再生成学习路径。"}

    query_str = state["query"]
    input_text = json.dumps(
        {
            "user_profile": profile_data.get("confirmed_info", profile_data),
            "learning_path_request": {
                "learning_topic": query_str,
                "goal": "",
                "preference": "",
                "target_time": "",
                "desired_outcome": "",
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    input_text = f"请根据以下信息生成学习路径：\n\n{input_text}"

    chain = _build_learning_path_chain(llm)

    try:
        result: LearningPathResult = await chain.ainvoke({"query": input_text, "history": []})
    except Exception as exc:
        logger.warning("LearningPathAgent failed: %s", exc)
        return {"error": str(exc)}

    path_dict = normalize_learning_path_result_payload(result.model_dump())

    from app.services.learning_path_service import upsert_user_learning_path
    upsert_user_learning_path(db_session, state["user_id"], path_dict)

    return {"learning_path": path_dict}


def _extract_last_tool_call_id(state: OrchestrationState) -> str | None:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("id")
    return None


def create_learning_path_agent_node(llm: BaseChatModel, db_session):
    async def learning_path_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_learning_path_agent(state, llm, db_session)

        tool_call_id = _extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        return {
            "learning_path": agent_result.get("learning_path"),
            "messages": [tool_message],
        }

    return learning_path_agent_node
