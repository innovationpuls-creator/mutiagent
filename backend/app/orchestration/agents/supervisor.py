from __future__ import annotations

import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool

from app.orchestration.agents.course_knowledge import ALL_CURRENT_GRADE_COURSES_ID
from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.prompts import SUPERVISOR_BASE_PROMPT
from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_LEARNING_PATH_INTAKE,
    AGENT_PROFILE,
    AGENT_SECTION_MARKDOWN,
    build_blocked_agents_hint,
    has_pending_profile_update_followup,
    is_course_change_query,
    is_navigation_query,
    is_profile_refinement_query,
    is_profile_update_no_change_query,
    is_profile_update_query,
)
from app.orchestration.rule_engine import (
    evaluate as evaluate_rules,
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
        summary_text = (
            profile.get("summary_text") if isinstance(profile, dict) else None
        )
        if isinstance(summary_text, str) and summary_text.strip():
            status_lines.append(f"✅ 用户画像已完成 — 摘要：{summary_text[:120]}")
        else:
            status_lines.append("✅ 用户画像已完成")
    elif profile and isinstance(profile, dict):
        status_lines.append(
            "❌ 用户画像未完成 — 当前仍需补全基础信息后再调用 profile_agent"
        )
    else:
        status_lines.append(
            "❌ 用户画像未完成 — 需要通过对话收集信息后调用 profile_agent"
        )

    year_paths = state.get("year_learning_paths", {})
    if year_paths:
        for year, path in year_paths.items():
            grade_name = (
                _grade_name_for_path(year, path) if isinstance(path, dict) else year
            )
            course_count = _course_count_for_path(path) if isinstance(path, dict) else 0
            status_lines.append(
                f"✅ {grade_name}({year}) 学习路径已生成 — {course_count} 门课程"
            )
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
    async def learning_path_intake_agent() -> str:
        """在正式生成学习路径前，基于已完成画像生成或确认课程草案。
        前提：用户画像已完成。该工具只负责课程草案，不生成正式学习路径。
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
        注意：仅在为特定课程生成大纲结构时使用。如果是通用的问答或概念解释，绝对禁止调用此工具。

        Args:
            course_id: 课程 ID（可选，留空则生成当前课程；"__all_current_grade__" 表示当前年级全部课程）
        """
        return ""

    @tool
    async def section_markdown_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前大纲中已存在的具体章节小节生成结构化的 Markdown 教学文档。
        注意：仅在生成课程小节内容时调用。如果用户是询问通用概念（如“什么是 FastAPI”、“如何学习后端”），绝对禁止调用此工具，应直接以文本形式回复用户。

        Args:
            course_id: 课程 ID，留空时使用当前课程
            section_id: 小节或一级章节 ID
            scope: default_first_chapter/single_section/chapter_sections
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
        learning_path_intake_agent,
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
                if isinstance(course, dict)
                and course.get("course_node_id") == current_course_id
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


def _normalized_course_match_text(value: object) -> str:
    return re.sub(
        r"[\s《》“”\"'：:，,。！？!?、；;（）()【】\[\]\-_/]+",
        "",
        str(value).strip().lower(),
    )


def _course_id_from_query_course_name(state: OrchestrationState) -> str:
    query_key = _normalized_course_match_text(state.get("query", ""))
    if not query_key:
        return ""

    year_learning_paths = state.get("year_learning_paths")
    if not isinstance(year_learning_paths, dict):
        return ""

    latest_grade_year = str(state.get("latest_grade_year", "")).strip()
    for path in iter_year_learning_paths(year_learning_paths, latest_grade_year):
        if not isinstance(path, dict):
            continue
        grade_plans = path.get("grade_plans")
        if not isinstance(grade_plans, dict):
            continue
        for grade_plan in grade_plans.values():
            if not isinstance(grade_plan, dict):
                continue
            course_nodes = grade_plan.get("course_nodes")
            if not isinstance(course_nodes, list):
                continue
            for course in course_nodes:
                if not isinstance(course, dict):
                    continue
                course_name_key = _normalized_course_match_text(
                    course.get("course_or_chapter_theme", "")
                )
                if not course_name_key or course_name_key not in query_key:
                    continue
                course_id = course.get("course_node_id")
                if isinstance(course_id, str):
                    return course_id

    return ""


def _current_course_id_from_learning_path(state: OrchestrationState) -> str:
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
        course_id = current.get("course_node_id")
        if isinstance(course_id, str) and course_id.strip():
            return course_id.strip()
    return ""


def _requests_all_current_grade_course_outlines(query: str) -> bool:
    normalized = _normalized_course_match_text(query)
    return any(
        keyword in normalized
        for keyword in (
            "全年所有课程",
            "全年全部课程",
            "全部课程大纲",
            "所有课程大纲",
            "一整年所有课程",
            "当前年级全部课程",
            "当前年级所有课程",
        )
    )


def _all_tasks_completed_response() -> str:
    return (
        "当前所有任务已经完成。"
        "如果你想继续下一阶段，我可以先帮你更新个人画像，再重新生成学习路径。"
        "请直接告诉我你想调整的信息，例如年级、专业、学习方向、短期目标、每周可投入时间或当前限制；"
        "如果这些信息里还有拿不准的部分，我会继续向你确认。"
    )


def _profile_update_prompt_response() -> str:
    return (
        "可以。更新个人画像前，我需要先确认这次是否值得更新。"
        "请先告诉我你想更新哪一块：基础信息、学习目标、能力基础、学习偏好、每周时间或当前限制。"
        "同时说明它和当前画像相比发生了什么具体变化；如果只是想看看或没有明确变化，我不会改画像，只会继续向你确认。"
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
        "specific_requirements": ""
        if normalized_query in _GENERIC_PATH_REFRESH_QUERIES
        else query,
    }


_CHINESE_CHAPTER_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_CHINESE_CHAPTER_PATTERN = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*章")
_ENGLISH_CHAPTER_PATTERN = re.compile(r"\bchapter\s*(\d+)\b", re.IGNORECASE)


def _clean_text(value: object) -> str:
    return str(value).strip()


def _normalized_section_text(value: object) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _clean_text(value).lower())


def _course_outline_sections(course_knowledge: object) -> list[dict]:
    if not isinstance(course_knowledge, dict):
        return []
    sections = course_knowledge.get("sections")
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]


def _root_sections(course_knowledge: object) -> list[dict]:
    sections = _course_outline_sections(course_knowledge)
    return sorted(
        [section for section in sections if int(section.get("depth", 1)) == 1],
        key=lambda item: int(item.get("order_index", 0)),
    )


def _first_root_section_id(course_knowledge: object) -> str:
    roots = _root_sections(course_knowledge)
    if not roots:
        return ""
    return _clean_text(roots[0].get("section_id"))


def _chapter_index_from_query(query: str) -> int | None:
    chinese_match = _CHINESE_CHAPTER_PATTERN.search(query)
    if chinese_match:
        raw = chinese_match.group(1).strip()
        if raw.isdigit():
            return int(raw)
        return _CHINESE_CHAPTER_NUMBERS.get(raw)

    english_match = _ENGLISH_CHAPTER_PATTERN.search(query)
    if english_match:
        return int(english_match.group(1))

    return None


def _resolve_root_section_id_from_query(course_knowledge: object, query: str) -> str:
    roots = _root_sections(course_knowledge)
    if not roots:
        return ""

    chapter_index = _chapter_index_from_query(query)
    if chapter_index is not None and 1 <= chapter_index <= len(roots):
        return _clean_text(roots[chapter_index - 1].get("section_id"))

    normalized_query = _normalized_section_text(query)
    if not normalized_query:
        return ""

    for root in roots:
        root_id = _clean_text(root.get("section_id"))
        root_title = _clean_text(root.get("title"))
        title_key = _normalized_section_text(root_title)
        labeled_key = _normalized_section_text(f"{root_id} {root_title}")
        if title_key and title_key in normalized_query:
            return root_id
        if labeled_key and labeled_key in normalized_query:
            return root_id

    return ""


def _section_markdown_force_args(state: OrchestrationState) -> dict[str, str]:
    query = str(state.get("query", "")).strip()
    course_knowledge = state.get("course_knowledge")
    course_id = (
        course_knowledge.get("course_id", "")
        if isinstance(course_knowledge, dict)
        else ""
    )
    first_root_id = _first_root_section_id(course_knowledge) or "1"
    if "当前课程" in query or "整门课" in query:
        return {
            "course_id": course_id,
            "section_id": first_root_id,
            "scope": "chapter_sections",
        }

    resolved_root_id = _resolve_root_section_id_from_query(course_knowledge, query)
    if resolved_root_id:
        return {
            "course_id": course_id,
            "section_id": resolved_root_id,
            "scope": "chapter_sections",
        }

    chapter_index = _chapter_index_from_query(query)
    if chapter_index is not None:
        return {
            "course_id": course_id,
            "section_id": str(chapter_index),
            "scope": "chapter_sections",
        }

    return {"course_id": course_id, "section_id": "", "scope": "default_first_chapter"}


def _force_call_response(agent_key: str, state: OrchestrationState) -> dict:
    """When the rule engine mandates a forced agent call."""
    if agent_key == AGENT_PROFILE:
        query = state.get("query", "")
        normalized_query = _normalize_followup_query(query)
        if has_pending_profile_update_followup(state) and (
            normalized_query in _FOLLOWUP_PAUSE_QUERIES
            or is_profile_update_no_change_query(query)
        ):
            response = _followup_pause_response()
            return {
                "messages": [AIMessage(content=response)],
                "response": response,
            }
        if (
            normalized_query in _GENERIC_PROFILE_UPDATE_QUERIES
            or is_profile_update_query(query)
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
            history = [
                m.content if hasattr(m, "content") else str(m) for m in messages[-6:]
            ]
            conversation_summary = "\n".join(history)

        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": AGENT_PROFILE,
                            "args": {"conversation_summary": conversation_summary},
                            "id": f"force_{AGENT_PROFILE}",
                        }
                    ],
                )
            ],
        }

    elif agent_key == AGENT_LEARNING_PATH_INTAKE:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": AGENT_LEARNING_PATH_INTAKE,
                            "args": {},
                            "id": f"force_{AGENT_LEARNING_PATH_INTAKE}",
                        }
                    ],
                )
            ],
        }

    elif agent_key == AGENT_LEARNING_PATH:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": AGENT_LEARNING_PATH,
                            "args": _learning_path_force_args(state),
                            "id": f"force_{AGENT_LEARNING_PATH}",
                        }
                    ],
                )
            ],
        }

    elif agent_key == AGENT_COURSE_KNOWLEDGE:
        query = str(state.get("query", "")).strip()
        is_course_change = is_course_change_query(query)
        if is_course_change:
            course_id = _next_course_id_for_course_change(state)
        elif _requests_all_current_grade_course_outlines(query):
            course_id = ALL_CURRENT_GRADE_COURSES_ID
        else:
            course_id = _course_id_from_query_course_name(
                state
            ) or _current_course_id_from_learning_path(state)
        if is_course_change and not course_id:
            response = _all_tasks_completed_response()
            return {
                "messages": [AIMessage(content=response)],
                "response": response,
            }
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": AGENT_COURSE_KNOWLEDGE,
                            "args": {"course_id": course_id},
                            "id": f"force_{AGENT_COURSE_KNOWLEDGE}",
                        }
                    ],
                )
            ],
        }

    elif agent_key == AGENT_SECTION_MARKDOWN:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": AGENT_SECTION_MARKDOWN,
                            "args": _section_markdown_force_args(state),
                            "id": f"force_{AGENT_SECTION_MARKDOWN}",
                        }
                    ],
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
                "messages": [
                    AIMessage(content="抱歉，暂时无法处理你的请求，请稍后再试。")
                ],
                "response": "抱歉，暂时无法处理你的请求，请稍后再试。",
            }

        # Guard: block LLM from calling blocked agents
        if rule_result and rule_result.blocked_agents and response.tool_calls:
            filtered_calls = [
                tc
                for tc in response.tool_calls
                if tc.get("name") not in rule_result.blocked_agents
            ]
            if len(filtered_calls) != len(response.tool_calls):
                blocked_names = [
                    tc["name"]
                    for tc in response.tool_calls
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
