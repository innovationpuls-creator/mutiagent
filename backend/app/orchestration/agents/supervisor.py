from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool

from app.orchestration.agents.prompts import SUPERVISOR_BASE_PROMPT
from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_PROFILE,
    build_blocked_agents_hint,
    evaluate as evaluate_rules,
)
from app.orchestration.state import OrchestrationState

logger = logging.getLogger(__name__)


# ── Dynamic system prompt builder ────────────────────────────────────────

def build_system_prompt(state: OrchestrationState) -> str:
    """Build a system prompt that tells the LLM what stage the conversation is in."""
    base = SUPERVISOR_BASE_PROMPT
    status_lines = []

    profile = state.get("profile")
    if profile and isinstance(profile, dict) and profile.get("summary_text"):
        status_lines.append(f"✅ 用户画像已完成 — 摘要：{profile['summary_text'][:120]}")
    elif profile and isinstance(profile, dict):
        status_lines.append("✅ 用户画像已完成")
    else:
        status_lines.append("❌ 用户画像未完成 — 需要通过对话收集信息后调用 profile_agent")

    year_paths = state.get("year_learning_paths", {})
    if year_paths:
        for year, path in year_paths.items():
            grade_name = path.get("grade_name", year)
            course_count = len(path.get("courses", []))
            status_lines.append(f"✅ {grade_name}({year}) 学习路径已生成 — {course_count} 门课程")
    else:
        status_lines.append("❌ 尚无学习路径")

    course_knowledge = state.get("course_knowledge")
    if course_knowledge and isinstance(course_knowledge, dict):
        status_lines.append(
            f"✅ 最近课程大纲：{course_knowledge.get('course_name', '')} "
            f"({len(course_knowledge.get('sections', []))} 个章节)"
        )

    status_blob = "\n".join(status_lines)
    return f"{base}\n\n## 当前状态\n{status_blob}"


# ── Tool definitions (matching new tool signatures) ──────────────────────

def create_tools_for_llm() -> list:

    @tool
    async def profile_agent(conversation_summary: str) -> str:
        """根据与用户的对话，生成结构化的基础学习画像。
        当你已经收集到足够的用户信息（年级、专业、偏好、目标等）时调用。

        Args:
            conversation_summary: 对用户已提供信息的总结，包含年级、专业、学习偏好、目标等
        """
        return ""

    @tool
    async def learning_path_agent(
        grade_year: str,
        learning_topic: str,
        specific_requirements: str = "",
    ) -> str:
        """为指定年级生成学习路径（推荐课程 + 顺序）。
        前提：用户画像已完成。

        Args:
            grade_year: 年级 ID (year_1/year_2/year_3/year_4)
            learning_topic: 学习主题/方向
            specific_requirements: 用户的具体要求
        """
        return ""

    @tool
    async def course_knowledge_agent(course_id: str = "") -> str:
        """为学习路径中的课程生成详细的章节大纲。
        前提：该年级的学习路径已生成。
        如果不指定 course_id，自动选取下一门待学课程。

        Args:
            course_id: 课程 ID（可选，留空则自动选取）
        """
        return ""

    return [profile_agent, learning_path_agent, course_knowledge_agent]


# ── Force call helper ────────────────────────────────────────────────────

def _force_call_response(agent_key: str, state: OrchestrationState) -> dict:
    """When the rule engine mandates a forced agent call."""
    if agent_key == AGENT_PROFILE:
        query = state.get("query", "")
        conversation_summary = f"用户说：{query}"
        # Build summary from existing conversation messages
        messages = state.get("messages", [])
        if messages:
            history = [m.content if hasattr(m, 'content') else str(m) for m in messages[-6:]]
            conversation_summary = "\n".join(history)

        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_PROFILE,
                        "args": {"conversation_summary": conversation_summary},
                        "id": f"force_{AGENT_PROFILE}",
                    }],
                )
            ],
        }

    elif agent_key == AGENT_LEARNING_PATH:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_LEARNING_PATH,
                        "args": {
                            "grade_year": "",
                            "learning_topic": state.get("query", ""),
                            "specific_requirements": "",
                        },
                        "id": f"force_{AGENT_LEARNING_PATH}",
                    }],
                )
            ],
        }

    elif agent_key == AGENT_COURSE_KNOWLEDGE:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_COURSE_KNOWLEDGE,
                        "args": {"course_id": ""},
                        "id": f"force_{AGENT_COURSE_KNOWLEDGE}",
                    }],
                )
            ],
        }

    return {}


# ── Supervisor node factory ──────────────────────────────────────────────

def create_supervisor_node(llm: BaseChatModel):
    """Create the Supervisor LangGraph node.

    Uses rule_engine.evaluate() for hard agent gating,
    then delegates all remaining decisions to the LLM.
    """

    tools = create_tools_for_llm()
    llm_with_tools = llm.bind_tools(tools)

    async def supervisor_node(state: OrchestrationState) -> dict:
        rule_result = evaluate_rules(state)

        # Force call: bypass LLM entirely
        if rule_result and rule_result.force_call:
            logger.debug("Rule engine force_call: %s", rule_result.force_call)
            return _force_call_response(rule_result.force_call, state)

        # Build messages: dynamic system prompt + conversation history
        messages = list(state.get("messages", []))
        system_prompt = build_system_prompt(state)
        system_messages = [SystemMessage(content=system_prompt)]

        # Inject rule hints
        if rule_result:
            if rule_result.blocked_agents:
                blocked_hint = build_blocked_agents_hint(rule_result.blocked_agents)
                if blocked_hint:
                    system_messages.append(SystemMessage(content=blocked_hint))
            for hint in rule_result.system_hints:
                system_messages.append(SystemMessage(content=hint))

        full_messages = system_messages + messages

        # Call LLM
        try:
            response: AIMessage = await llm_with_tools.ainvoke(full_messages)
        except Exception as exc:
            logger.warning("Supervisor LLM call failed: %s", exc)
            return {
                "messages": [AIMessage(content="抱歉，暂时无法处理你的请求，请稍后再试。")],
                "response": "抱歉，暂时无法处理你的请求，请稍后再试。",
            }

        # Guard: block LLM from calling blocked agents
        if rule_result and rule_result.blocked_agents and response.tool_calls:
            filtered_calls = [
                tc for tc in response.tool_calls
                if tc.get("name") not in rule_result.blocked_agents
            ]
            if len(filtered_calls) != len(response.tool_calls):
                blocked_names = [
                    tc["name"] for tc in response.tool_calls
                    if tc["name"] in rule_result.blocked_agents
                ]
                logger.warning("Blocked LLM tool calls: %s", blocked_names)
                if not filtered_calls:
                    response = AIMessage(
                        content="抱歉，当前阶段还不能使用这个功能。请先完成前面的步骤。"
                    )
                else:
                    response.tool_calls = filtered_calls

        result = {"messages": [response]}
        if not response.tool_calls:
            result["response"] = response.content
        return result

    return supervisor_node
