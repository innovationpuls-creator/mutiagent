from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool

from app.orchestration.agents.prompts import SUPERVISOR_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def create_tools_for_llm() -> list:
    """Create LangChain tool definitions. These only provide the schema for the LLM to produce tool_calls.
    Actual execution happens in dedicated graph nodes."""

    @tool
    async def profile_agent(query: str) -> str:
        """Collect or view the user's basic learning profile (grade, major, learning preferences, goals, etc.).
        Call when the user is new or their profile is incomplete.

        Args:
            query: The user's current input
        """
        return ""

    @tool
    async def learning_path_agent(
        learning_topic: str,
        goal: str = "",
        preference: str = "",
        target_time: str = "",
        desired_outcome: str = "",
    ) -> str:
        """Generate a structured learning path based on the user's completed profile.
        Call when the user has a complete profile and wants to learn a specific topic.

        Args:
            learning_topic: The course/technology/skill the user wants to learn
            goal: The learning goal
            preference: The learning preference
            target_time: The target completion time
            desired_outcome: The desired outcome
        """
        return ""

    @tool
    async def course_knowledge_agent() -> str:
        """Generate a chapter outline for the current course node based on the learning path.
        Call when the user has a learning path and wants to start a course.
        No parameters needed — the backend automatically resolves the current course node."""
        return ""

    return [profile_agent, learning_path_agent, course_knowledge_agent]


def create_supervisor_node(llm: BaseChatModel):
    """Create Supervisor LangGraph node.

    Each invocation: LLM + bind_tools decides the next step, producing an AIMessage (possibly with tool_calls).
    If tool_calls exist → route to corresponding worker node.
    If no tool_calls → graph ends, content becomes the final response.
    """

    tools = create_tools_for_llm()
    llm_with_tools = llm.bind_tools(tools)

    async def supervisor_node(state: OrchestrationState) -> dict:
        messages = list(state.get("messages", []))

        system_message = SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)
        full_messages = [system_message] + messages

        try:
            response: AIMessage = await llm_with_tools.ainvoke(full_messages)
        except Exception as exc:
            logger.warning("Supervisor LLM call failed: %s", exc)
            return {
                "messages": [AIMessage(content="抱歉，暂时无法处理你的请求，请稍后再试。")],
                "response": "抱歉，暂时无法处理你的请求，请稍后再试。",
            }

        result = {"messages": [response]}
        if not response.tool_calls:
            result["response"] = response.content
        return result

    return supervisor_node
