from __future__ import annotations

import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.orchestration.agent_plan import CourseKnowledgeOutlineResult
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

COURSE_KNOWLEDGE_PROMPT = COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT + """

## 输出格式
你必须输出一个合法的 JSON 对象，不要包含 markdown 代码块标记。输出结构必须包含：

- schema_version: 字符串 "course_knowledge_outline.v1"
- course_node_id: 字符串
- course_name: 字符串
- grade_id: 字符串 "year_1"到"year_4"
- personalization_summary: 字符串
- sections: 数组 每项含 section_id(格式如 "1"/"1.1"/"1.1.1" 数字点分), parent_section_id(字符串或null), depth(整数1-4), title(字符串), order_index(整数)
- learning_sequence: 字符串数组 section_id 的顺序列表
- markmap_source: 字符串 思维导图文本

示例输出格式:
{{"schema_version": "course_knowledge_outline.v1", "course_node_id": "year_1_course_1", "course_name": "程序设计基础", "grade_id": "year_1", "personalization_summary": "...", "sections": [{{"section_id": "1", "parent_section_id": null, "depth": 1, "title": "第1章 ...", "order_index": 1}}], "learning_sequence": ["1", "1.1", "1.2"], "markmap_source": "# 课程名\\n## 第1章 ..."}}

直接输出纯 JSON。"""


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    raise ValueError(f"Response does not contain valid JSON: {text[:200]}")


def _build_course_knowledge_chain(llm: BaseChatModel):
    prompt = ChatPromptTemplate.from_messages([
        ("system", COURSE_KNOWLEDGE_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{query}"),
    ])
    return prompt | llm


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
        response = await chain.ainvoke({"query": input_text, "history": []})
        parsed = _parse_json_response(response.content)
        result = CourseKnowledgeOutlineResult.model_validate(parsed)
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
