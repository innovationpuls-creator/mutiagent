from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agents.models import CourseKnowledgeOutput
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


def _resolve_next_course(year_learning_paths: dict, course_knowledge: dict | None) -> tuple[str | None, dict | None]:
    """Find the next course without an outline across all years."""
    if not year_learning_paths:
        return None, None

    from sqlmodel import Session
    from app.database import get_engine
    from app.services.course_knowledge_service import list_user_course_outlines

    # Gather all course_ids that already have outlines
    existing_outlines: set[str] = set()
    if course_knowledge:
        existing_outlines.add(course_knowledge.get("course_id", ""))

    for grade_year in sorted(year_learning_paths.keys()):
        path = year_learning_paths[grade_year]
        courses = path.get("courses", [])
        sequence = path.get("recommended_sequence", [])
        for course_id in sequence:
            course = next((c for c in courses if c.get("course_id") == course_id), None)
            if course and course_id not in existing_outlines:
                return course_id, course

    return None, None


async def run_course_knowledge_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """Generate detailed course outline, auto-resolving next course if not specified."""
    tool_args = extract_last_tool_call_args(state)
    course_id = tool_args.get("course_id", "")

    profile = state.get("profile", {})
    year_learning_paths = state.get("year_learning_paths", {})
    course_knowledge = state.get("course_knowledge")

    # Guard: profile must exist
    if not profile or profile.get("type") != "basic_profile":
        return {"error": "请先完成基础画像。"}

    # Guard: need at least one year path
    if not year_learning_paths:
        return {"error": "请先生成学习路径。"}

    # Auto-resolve next course
    course_info = None
    if not course_id:
        course_id, course_info = _resolve_next_course(year_learning_paths, course_knowledge)
        if not course_id:
            return {"error": "当前路径中没有待学习的课程，所有课程已生成大纲。"}
    else:
        for path in year_learning_paths.values():
            for c in path.get("courses", []):
                if c.get("course_id") == course_id:
                    course_info = c
                    break
            if course_info:
                break
        if not course_info:
            return {"error": f"未找到课程 {course_id}。"}

    input_data = {
        "course": json.dumps(course_info, ensure_ascii=False, indent=2),
        "profile": json.dumps(profile, ensure_ascii=False, indent=2),
    }

    input_text = (
        f"请为以下课程生成详细的章节大纲：\n\n"
        f"课程信息：{input_data['course']}\n"
        f"用户画像：{input_data['profile']}"
    )

    structured_llm = llm.with_structured_output(CourseKnowledgeOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    try:
        result: CourseKnowledgeOutput = await chain.ainvoke({"query": input_text})
    except Exception as exc:
        logger.warning("CourseKnowledgeAgent structured output failed: %s", exc)
        return {"error": f"大纲生成失败：{str(exc)[:200]}"}

    outline_dict = result.model_dump()

    from sqlmodel import Session
    from app.database import get_engine
    from app.services.course_knowledge_service import upsert_user_course_knowledge_outline
    try:
        with Session(get_engine()) as db_session:
            upsert_user_course_knowledge_outline(db_session, state["user_id"], outline_dict)
        logger.info("CourseKnowledgeOutline persisted for user %s, course %s", state["user_id"], course_id)
    except Exception as exc:
        logger.error("Failed to persist course_knowledge for user %s: %s", state["user_id"], exc)

    return {"course_knowledge": outline_dict}


def create_course_knowledge_agent_node(llm: BaseChatModel):
    async def course_knowledge_node(state: OrchestrationState) -> dict:
        agent_result = await run_course_knowledge_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("course_knowledge") is not None:
            result["course_knowledge"] = agent_result["course_knowledge"]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return course_knowledge_node
