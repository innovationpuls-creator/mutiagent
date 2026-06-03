from __future__ import annotations

import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.orchestration.agents.models import ProfileAgentOutput
from app.orchestration.agents.prompts import PROFILE_AGENT_SYSTEM_PROMPT
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

PROFILE_AGENT_PROMPT = PROFILE_AGENT_SYSTEM_PROMPT + """

## 输出 JSON Schema（必须严格遵循此格式）
最终回复必须是合法 JSON，不要包含 markdown 代码块标记，直接输出纯 JSON。输出结构示例：

```
类型字段 type: "collecting" 或 "basic_profile"
阶段字段 stage: "basic_info"、"learning_preference"、"ability_basis"、"goal_constraint" 或 "generated"
问题模式 question_mode: "question_md"、"question_box" 或 "none"
已确认信息 confirmed_info: 对象，包含 current_grade、major、learning_stage、has_clear_goal、learning_method_preference、learning_pace_preference、content_preference(数组)、need_guidance、knowledge_foundation、strengths、weaknesses、experience、short_term_goal、long_term_goal、weekly_available_time、constraints 字段
系统补全 defaulted_fields: 字符串数组
问题文本 question_md: 字符串
选项框 question_box: 对象，包含 question(字符串) 和 options(数组，每项含 label、value、description、target_fields、fills 字段)
对话文本 text: 字符串
```

示例输出：
```
{{"type": "collecting", "stage": "basic_info", "question_mode": "question_box", "confirmed_info": {{"current_grade": "", "major": "", ...}}, "defaulted_fields": [], "question_md": "", "question_box": {{"question": "你是大几的？", "options": [{{"label": "大一", "value": "大一", "description": "", "target_fields": ["current_grade"], "fills": {{"current_grade": "大一"}}}}]}}, "text": "请告诉我你的基本信息。"}}
```"""


def _build_profile_chain(llm: BaseChatModel):
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROFILE_AGENT_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{query}"),
    ])
    return prompt | llm


def _parse_json_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON，支持代码块和纯文本格式。"""
    text = text.strip()

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)

    raise ValueError(f"Response does not contain valid JSON: {text[:200]}")


async def run_profile_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    db_session,
) -> dict:
    chain = _build_profile_chain(llm)
    messages = [
        m for m in state.get("messages", [])
        if not (hasattr(m, "content") and m.content == "" and hasattr(m, "tool_calls") and m.tool_calls)
    ]
    chain_input = {"query": state["query"], "history": messages}

    try:
        response = await chain.ainvoke(chain_input)
        parsed = _parse_json_response(response.content)
        result = ProfileAgentOutput.model_validate(parsed)
    except Exception as exc:
        logger.warning("ProfileAgent failed: %s", exc)
        return {"error": str(exc)}

    profile_dict = result.model_dump()
    is_completed = result.type == "basic_profile" and result.stage == "generated"

    if is_completed:
        from app.services.profile_service import upsert_user_profile
        upsert_user_profile(db_session, state["user_id"], profile_dict)

    user_answer = {
        "user_message": result.question_md or result.text or "",
        "question_box": {
            "question": result.question_box.question,
            "options": [opt.model_dump() for opt in result.question_box.options],
        } if result.question_box.question else None,
    }

    return {"profile": profile_dict, "answer": user_answer, "profile_completed": is_completed}


def _extract_last_tool_call_id(state: OrchestrationState) -> str | None:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return msg.tool_calls[0].get("id")
    return None


def create_profile_agent_node(llm: BaseChatModel, db_session):
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
