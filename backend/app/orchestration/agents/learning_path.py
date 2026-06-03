from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agent_plan import LearningPathResult, normalize_learning_path_result_payload
from app.orchestration.agents.prompts import LEARNING_PATH_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_id, parse_json_response
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)

LEARNING_PATH_PROMPT = LEARNING_PATH_AGENT_SYSTEM_PROMPT + """

## 输出格式
你必须输出一个合法的 JSON 对象，不要包含 markdown 代码块标记。输出结构必须包含：

- schema_version: 字符串 "learning_path.v2.course_node"
- learning_goal: 对象 target_course_or_skill, target_completion_time, goal_type(枚举: 考试/课程学习/项目实践/能力提升/就业准备/其他), desired_outcome
- gap_analysis: 对象 含 current_mastered_content(数组), current_weaknesses(数组), required_capabilities(数组), main_gaps(数组)
- foundation_path: 对象 含 stages(数组), 每个阶段有 stage_id, stage_name, learning_goal, learning_content(数组), learning_tasks(数组), recommended_methods(数组), completion_standard(数组)
- generated_path: 对象 含 overall_goal, stage_routes(数组 含stage_id和route_summary), schedule(数组至少8项 每项含period focus milestone), task_checklist(数组), recommended_resource_types(数组), stage_acceptance_criteria(数组 含stage_id和criteria数组), next_actions(数组)

示例输出格式:
{{"schema_version": "learning_path.v2.course_node", "learning_goal": {{"target_course_or_skill": "...", "target_completion_time": "...", "goal_type": "...", "desired_outcome": "..."}}, "gap_analysis": {{"current_mastered_content": ["..."], "current_weaknesses": ["..."], "required_capabilities": ["..."], "main_gaps": ["..."]}}, "foundation_path": {{"stages": [{{"stage_id": "stage_1", "stage_name": "...", "learning_goal": "...", "learning_content": ["..."], "learning_tasks": ["..."], "recommended_methods": ["..."], "completion_standard": ["..."]}}]}}, "generated_path": {{"overall_goal": "...", "stage_routes": [{{"stage_id": "stage_1", "route_summary": "..."}}], "schedule": [{{"period": "大一上学期", "focus": "...", "milestone": "..."}}], "task_checklist": ["..."], "recommended_resource_types": ["..."], "stage_acceptance_criteria": [{{"stage_id": "stage_1", "criteria": ["..."]}}], "next_actions": ["..."]}}}}

直接输出纯 JSON。"""


def _build_learning_path_chain(llm: BaseChatModel):
    prompt = ChatPromptTemplate.from_messages([
        ("system", LEARNING_PATH_PROMPT),
        ("human", "{query}"),
    ])
    return prompt | llm


async def run_learning_path_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
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
        response = await chain.ainvoke({"query": input_text})
        parsed = parse_json_response(response.content)
        result = LearningPathResult.model_validate(normalize_learning_path_result_payload(parsed))
    except Exception as exc:
        logger.warning("LearningPathAgent failed: %s", exc)
        return {"error": str(exc)}

    # Use model_dump() directly — no redundant second normalize call
    path_dict = result.model_dump()

    from sqlmodel import Session
    from app.database import get_engine
    from app.services.learning_path_service import upsert_user_learning_path
    with Session(get_engine()) as db_session:
        upsert_user_learning_path(db_session, state["user_id"], path_dict)

    return {"learning_path": path_dict}


def create_learning_path_agent_node(llm: BaseChatModel):
    async def learning_path_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_learning_path_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        return {
            "learning_path": agent_result.get("learning_path"),
            "messages": [tool_message],
        }

    return learning_path_agent_node
