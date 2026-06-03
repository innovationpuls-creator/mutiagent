from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agents.models import YearLearningPathOutput
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


async def run_learning_path_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """Generate a simplified learning path for a single grade year."""
    tool_args = extract_last_tool_call_args(state)
    grade_year = tool_args.get("grade_year", "")
    learning_topic = tool_args.get("learning_topic", "")

    # Guard: profile must exist
    profile = state.get("profile")
    if not profile or profile.get("type") != "basic_profile":
        return {"error": "请先完成基础画像再生成学习路径。"}

    input_data = {
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
        "grade_year": grade_year,
        "learning_topic": learning_topic,
        "requirements": tool_args.get("specific_requirements", ""),
    }

    input_text = (
        f"请为 {grade_year} 生成「{learning_topic}」的学习路径。\n\n"
        f"用户画像：{input_data['profile']}\n"
        f"具体要求：{input_data['requirements'] or '无'}"
    )

    structured_llm = llm.with_structured_output(YearLearningPathOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", LEARNING_PATH_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    try:
        result: YearLearningPathOutput = await chain.ainvoke({"query": input_text})
    except Exception as exc:
        logger.warning("LearningPathAgent structured output failed: %s", exc)
        return {"error": f"路径生成失败：{str(exc)[:200]}"}

    path_dict = result.model_dump()

    from sqlmodel import Session
    from app.database import get_engine
    from app.services.learning_path_service import upsert_year_learning_path
    try:
        with Session(get_engine()) as db_session:
            upsert_year_learning_path(db_session, state["user_id"], grade_year, learning_topic, path_dict)
        logger.info("LearningPath persisted for user %s, year %s", state["user_id"], grade_year)
    except Exception as exc:
        logger.error("Failed to persist learning_path for user %s: %s", state["user_id"], exc)

    return {"year_learning_path": path_dict, "grade_year": grade_year}


def create_learning_path_agent_node(llm: BaseChatModel):
    async def learning_path_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_learning_path_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("year_learning_path") is not None:
            result["year_learning_path"] = agent_result["year_learning_path"]
            result["grade_year"] = agent_result.get("grade_year", "")
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return learning_path_agent_node
