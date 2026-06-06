from __future__ import annotations

import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool

from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.prompts import SUPERVISOR_BASE_PROMPT
from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_PROFILE,
    AGENT_SECTION_HTML_ANIMATION,
    AGENT_SECTION_MARKDOWN,
    AGENT_SECTION_VIDEO_SEARCH,
    build_blocked_agents_hint,
    evaluate as evaluate_rules,
    has_pending_profile_update_followup,
    is_course_change_query,
    is_navigation_query,
    is_profile_refinement_query,
)
from app.orchestration.state import OrchestrationState
from app.services.learning_path_service import iter_year_learning_paths

logger = logging.getLogger(__name__)

_GENERIC_PROFILE_UPDATE_QUERIES = {"更新个人画像", "修改画像方向"}
_GENERIC_PATH_REFRESH_QUERIES = {"继续生成学习路径", "更新学习路径"}
_FOLLOWUP_PAUSE_QUERIES = {
    "谢谢",
    "谢谢你",
    "先不用",
    "先不用了",
    "不用了",
    "暂时不用",
    "不需要",
    "先这样",
}


# ── Dynamic system prompt builder ────────────────────────────────────────

def _grade_name_for_path(year: str, path: dict) -> str:
    grade_plans = path.get("grade_plans")
    if isinstance(grade_plans, dict):
        grade_plan = grade_plans.get(year)
        if isinstance(grade_plan, dict):
            grade_name = grade_plan.get("grade_name")
            if isinstance(grade_name, str) and grade_name.strip():
                return grade_name.strip()
        for value in grade_plans.values():
            if not isinstance(value, dict):
                continue
            grade_name = value.get("grade_name")
            if isinstance(grade_name, str) and grade_name.strip():
                return grade_name.strip()

    grade_name = path.get("grade_name")
    if isinstance(grade_name, str) and grade_name.strip():
        return grade_name.strip()
    return year


def _course_count_for_path(path: dict) -> int:
    grade_plans = path.get("grade_plans")
    if isinstance(grade_plans, dict):
        count = 0
        for grade_plan in grade_plans.values():
            if not isinstance(grade_plan, dict):
                continue
            course_nodes = grade_plan.get("course_nodes")
            if isinstance(course_nodes, list):
                count += len(course_nodes)
        return count

    courses = path.get("courses")
    if isinstance(courses, list):
        return len(courses)
    return 0

def build_system_prompt(state: OrchestrationState) -> str:
    """Build a system prompt that tells the LLM what stage the conversation is in."""
    base = SUPERVISOR_BASE_PROMPT
    status_lines = []

    profile = state.get("profile")
    if is_complete_profile_data(profile):
        summary_text = profile.get("summary_text") if isinstance(profile, dict) else None
        if isinstance(summary_text, str) and summary_text.strip():
            status_lines.append(f"✅ 用户画像已完成 — 摘要：{summary_text[:120]}")
        else:
            status_lines.append("✅ 用户画像已完成")
    elif profile and isinstance(profile, dict):
        status_lines.append("❌ 用户画像未完成 — 当前仍需补全基础信息后再调用 profile_agent")
    else:
        status_lines.append("❌ 用户画像未完成 — 需要通过对话收集信息后调用 profile_agent")

    year_paths = state.get("year_learning_paths", {})
    if year_paths:
        for year, path in year_paths.items():
            grade_name = _grade_name_for_path(year, path) if isinstance(path, dict) else year
            course_count = _course_count_for_path(path) if isinstance(path, dict) else 0
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

    @tool
    async def section_markdown_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前课程的小节生成 Markdown 教学文档。

        Args:
            course_id: 课程 ID，留空时使用当前课程
            section_id: 小节或一级章节 ID
            scope: default_first_chapter/single_section/chapter_sections/course_sections
        """
        return ""

    @tool
    async def section_video_search_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前课程小节联网搜索教学视频链接和封面。"""
        return ""

    @tool
    async def section_html_animation_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前课程小节生成 HTML 动画资源。"""
        return ""

    return [
        profile_agent,
        learning_path_agent,
        course_knowledge_agent,
        section_markdown_agent,
        section_video_search_agent,
        section_html_animation_agent,
    ]


# ── Force call helper ────────────────────────────────────────────────────

def _next_course_id_for_course_change(state: OrchestrationState) -> str:
    query = str(state.get("query", "")).strip()
    if not is_course_change_query(query):
        return ""

    year_learning_paths = state.get("year_learning_paths")
    if not isinstance(year_learning_paths, dict):
        return ""

    latest_grade_year = str(state.get("latest_grade_year", "")).strip()

    for path in iter_year_learning_paths(year_learning_paths, latest_grade_year):
        if not isinstance(path, dict):
            continue
        current = path.get("current_learning_course")
        if not isinstance(current, dict):
            continue
        grade_id = current.get("grade_id")
        current_course_id = current.get("course_node_id")
        grade_plans = path.get("grade_plans")
        if not isinstance(grade_plans, dict):
            continue
        grade_plan = grade_plans.get(grade_id)
        if not isinstance(grade_plan, dict):
            continue
        course_nodes = grade_plan.get("course_nodes")
        if not isinstance(course_nodes, list):
            continue

        current_index = next(
            (
                index
                for index, course in enumerate(course_nodes)
                if isinstance(course, dict) and course.get("course_node_id") == current_course_id
            ),
            -1,
        )
        if current_index >= 0 and current_index + 1 < len(course_nodes):
            next_course = course_nodes[current_index + 1]
            if isinstance(next_course, dict):
                next_course_id = next_course.get("course_node_id")
                if isinstance(next_course_id, str):
                    return next_course_id

    return ""


def _all_tasks_completed_response() -> str:
    return (
        "当前所有任务已经完成。"
        "如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"
        "请直接告诉我你想调整的信息，例如年级、专业、学习方向、短期目标、每周可投入时间或当前限制；"
        "如果这些信息里还有拿不准的部分，我会继续向你确认。"
    )


def _profile_update_prompt_response() -> str:
    return (
        "可以。更新个人画像前，请先直接告诉我你想调整的具体信息。"
        "你可以提供年级、专业、学习方向、短期目标、长期目标、每周可投入时间、学习节奏或当前限制。"
        "如果你暂时只确定了一部分，也可以先发我已确定的内容，我会继续向你确认剩余信息。"
    )


def _followup_pause_response() -> str:
    return (
        "好的，当前先不调整。"
        "如果你之后想继续更新个人画像或重新生成学习路径，直接告诉我你想调整的具体信息就可以。"
    )


def _normalize_followup_query(query: str) -> str:
    return re.sub(r"[。！？!?,，、；：\s]+", "", query.strip())


def _learning_path_force_args(state: OrchestrationState) -> dict[str, str]:
    query = str(state.get("query", "")).strip()
    normalized_query = _normalize_followup_query(query)
    return {
        "grade_year": "",
        "learning_topic": "",
        "specific_requirements": "" if normalized_query in _GENERIC_PATH_REFRESH_QUERIES else query,
    }


def _section_markdown_force_args(state: OrchestrationState) -> dict[str, str]:
    query = str(state.get("query", "")).strip()
    course_knowledge = state.get("course_knowledge")
    course_id = course_knowledge.get("course_id", "") if isinstance(course_knowledge, dict) else ""
    if "当前课程" in query or "整门课" in query:
        return {"course_id": course_id, "section_id": "", "scope": "course_sections"}
    if "第一章" in query:
        return {"course_id": course_id, "section_id": "1", "scope": "chapter_sections"}
    return {"course_id": course_id, "section_id": "", "scope": "default_first_chapter"}


def _force_call_response(agent_key: str, state: OrchestrationState) -> dict:
    """When the rule engine mandates a forced agent call."""
    if agent_key == AGENT_PROFILE:
        query = state.get("query", "")
        normalized_query = _normalize_followup_query(query)
        if has_pending_profile_update_followup(state) and normalized_query in _FOLLOWUP_PAUSE_QUERIES:
            response = _followup_pause_response()
            return {
                "messages": [AIMessage(content=response)],
                "response": response,
            }
        if (
            normalized_query in _GENERIC_PROFILE_UPDATE_QUERIES
            or (
                has_pending_profile_update_followup(state)
                and normalized_query in _GENERIC_PATH_REFRESH_QUERIES
            )
            or (
                has_pending_profile_update_followup(state)
                and is_navigation_query(query)
                and not is_profile_refinement_query(query)
            )
        ):
            response = _profile_update_prompt_response()
            return {
                "messages": [AIMessage(content=response)],
                "response": response,
            }
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
                        "args": _learning_path_force_args(state),
                        "id": f"force_{AGENT_LEARNING_PATH}",
                    }],
                )
            ],
        }

    elif agent_key == AGENT_COURSE_KNOWLEDGE:
        course_id = _next_course_id_for_course_change(state)
        if is_course_change_query(str(state.get("query", "")).strip()) and not course_id:
            response = _all_tasks_completed_response()
            return {
                "messages": [AIMessage(content=response)],
                "response": response,
            }
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_COURSE_KNOWLEDGE,
                        "args": {"course_id": course_id},
                        "id": f"force_{AGENT_COURSE_KNOWLEDGE}",
                    }],
                )
            ],
        }

    elif agent_key == AGENT_SECTION_MARKDOWN:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_SECTION_MARKDOWN,
                        "args": _section_markdown_force_args(state),
                        "id": f"force_{AGENT_SECTION_MARKDOWN}",
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
