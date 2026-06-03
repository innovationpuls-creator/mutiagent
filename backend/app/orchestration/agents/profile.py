from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.orchestration.agents.models import ProfileAgentOutput
from app.orchestration.agents.prompts import PROFILE_AGENT_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _build_profile_chain(llm: BaseChatModel) -> Runnable:
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROFILE_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{query}"),
    ])
    return prompt | llm.with_structured_output(ProfileAgentOutput)


def _build_profile_input(state: OrchestrationState) -> dict:
    messages = state.get("messages", [])
    return {
        "query": state["query"],
        "history": list(messages),
    }


def _profile_result_to_user_answer(result: ProfileAgentOutput) -> dict:
    return {
        "user_message": result.question_md or result.text or "",
        "question_box": {
            "question": result.question_box.question,
            "options": [opt.model_dump() for opt in result.question_box.options],
        } if result.question_box.question else None,
    }


async def run_profile_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    db_session,
) -> dict:
    chain = _build_profile_chain(llm)
    chain_input = _build_profile_input(state)

    try:
        result: ProfileAgentOutput = await chain.ainvoke(chain_input)
    except Exception as exc:
        logger.warning("ProfileAgent failed: %s", exc)
        return {"error": str(exc)}

    profile_dict = result.model_dump()
    user_answer = _profile_result_to_user_answer(result)
    is_completed = result.type == "basic_profile" and result.stage == "generated"

    if is_completed:
        from app.services.profile_service import upsert_user_profile
        upsert_user_profile(db_session, state["user_id"], profile_dict)

    return {"profile": profile_dict, "answer": user_answer, "profile_completed": is_completed}


def _extract_last_tool_call_id(state: OrchestrationState) -> str | None:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("id")
    return None


def create_profile_agent_node(llm: BaseChatModel, db_session):
    """Create ProfileAgent as a LangGraph node. Executes agent then writes state fields and ToolMessage."""

    async def profile_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_profile_agent(state, llm, db_session)

        tool_call_id = _extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        return {
            "profile": agent_result.get("profile"),
            "answer": agent_result.get("answer"),
            "profile_completed": agent_result.get("profile_completed", False),
            "messages": [tool_message],
        }

    return profile_agent_node
