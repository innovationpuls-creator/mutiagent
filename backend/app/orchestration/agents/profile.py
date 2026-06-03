from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agents.models import ProfileOutput
from app.orchestration.agents.prompts import PROFILE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


async def run_profile_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """One-shot profile generation: receives conversation summary, outputs structured profile."""
    tool_args = extract_last_tool_call_args(state)
    conversation_summary = tool_args.get("conversation_summary", state["query"])

    structured_llm = llm.with_structured_output(ProfileOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROFILE_AGENT_SYSTEM_PROMPT),
        ("human", "{summary}"),
    ])
    chain = prompt | structured_llm

    try:
        result: ProfileOutput = await chain.ainvoke({"summary": conversation_summary})
    except Exception as exc:
        logger.warning("ProfileAgent structured output failed: %s", exc)
        return {"error": f"画像生成失败：{str(exc)[:200]}"}

    profile_dict = result.model_dump()

    from sqlmodel import Session
    from app.database import get_engine
    from app.services.profile_service import upsert_user_profile
    try:
        with Session(get_engine()) as db_session:
            upsert_user_profile(db_session, state["user_id"], profile_dict)
        logger.info("Profile persisted for user %s", state["user_id"])
    except Exception as exc:
        logger.error("Failed to persist profile for user %s: %s", state["user_id"], exc)

    return {"profile": profile_dict}


def create_profile_agent_node(llm: BaseChatModel):
    async def profile_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_profile_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("profile") is not None:
            result["profile"] = agent_result["profile"]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return profile_agent_node
