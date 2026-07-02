from __future__ import annotations

import asyncio
import copy
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlmodel import Session

from app.database import get_engine
from app.orchestration.agents.models import (
    LearningPathIntakeDraftOutput,
    LearningPathIntakeOutput,
)
from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.prompts import LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_id
from app.orchestration.grade_contract import grade_year_from_current_grade
from app.orchestration.guards import require_profile_for_intake
from app.orchestration.prompt_budget import apply_prompt_budget
from app.orchestration.state import OrchestrationState
from app.services.conversation_session_service import (
    load_or_create_session,
    replace_latest_learning_path_intake,
)
from app.services.knowledge_base_service import get_published_textbook_context_for_topic
from app.services.learning_path_service import (
    get_grade_courses,
    iter_year_learning_paths,
)

logger = logging.getLogger(__name__)

LEARNING_PATH_INTAKE_STRUCTURED_TIMEOUT_SECONDS = 90.0
LEARNING_PATH_INTAKE_RETRY_ERROR = "课程草案生成失败，请重试生成学习路径草案。"

CONFIRMATION_MARKERS = (
    "可以",
    "确认",
    "没问题",
    "就按这个",
    "按这个来",
    "听你的",
    "可以开始",
    "开始吧",
    "好的",
    "行",
    "继续",
)
CANCELLATION_MARKERS = (
    "不要了",
    "算了",
    "先不改",
)
MODIFICATION_MARKERS = (
    "换成",
    "改成",
    "调整",
    "修改",
    "不想学",
    "不学",
    "我想学",
    "想学",
    "换一门",
    "换个",
)
TOPIC_MARKERS = (
    ("数据结构", "数据结构"),
    ("算法", "算法"),
    ("前端", "前端开发"),
    ("后端", "后端开发"),
)


def is_intake_modification_query(text: str) -> bool:
    normalized = text.strip()
    if "确认修改" in normalized or "确认调整" in normalized:
        return False
    return bool(normalized) and any(
        marker in normalized for marker in MODIFICATION_MARKERS
    )


def is_intake_confirmation_query(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if "确认修改" in normalized or "确认调整" in normalized:
        return True
    if is_intake_modification_query(normalized):
        return False
    return any(marker in normalized for marker in CONFIRMATION_MARKERS)


def is_intake_cancellation_query(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and any(
        marker in normalized for marker in CANCELLATION_MARKERS
    )


def latest_intake_from_state(state: OrchestrationState | dict) -> dict | None:
    intake = state.get("learning_path_intake")
    if isinstance(intake, dict) and intake.get("type") == "learning_path_intake":
        return intake

    messages = state.get("messages", [])
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        parsed = _intake_from_message(message)
        if parsed is not None:
            return parsed
    return None


async def run_learning_path_intake_agent(
    state: OrchestrationState, llm: BaseChatModel
) -> dict:
    query = str(state.get("query", "")).strip()
    existing_intake = latest_intake_from_state(state)

    if (
        existing_intake is not None
        and existing_intake.get("status") == "risk_pending"
        and is_intake_cancellation_query(query)
    ):
        rolled_back = copy.deepcopy(existing_intake)
        rolled_back["status"] = "draft"
        rolled_back["requires_second_confirmation"] = False
        rolled_back["risk_warnings"] = []
        _persist_learning_path_intake(state, rolled_back)
        return {
            "learning_path_intake": rolled_back,
            "response": _risk_cancelled_response_text(rolled_back),
        }

    if existing_intake is not None and is_intake_confirmation_query(query):
        confirmed = copy.deepcopy(existing_intake)
        confirmed["status"] = "confirmed"
        confirmed["requires_second_confirmation"] = False
        confirmed["risk_warnings"] = []
        _persist_learning_path_intake(state, confirmed)
        return {
            "learning_path_intake": confirmed,
            "response": _confirmed_response_text(confirmed),
        }

    profile = state.get("profile")
    if not is_complete_profile_data(profile):
        return {"error": "请先完成基础画像再生成学习路径。", "hard_error": True}

    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    learning_topic = _learning_topic_from_texts(query, profile, confirmed)
    knowledge_context = _published_textbook_context_for_intake(
        learning_topic,
        query,
        profile,
    )
    if not knowledge_context["textbooks"]:
        gap_id = knowledge_context.get("gap_id")
        error = f"知识库暂无覆盖「{learning_topic}」的已发布教材，已加入管理员待办。"
        return {
            "error": error,
            "gap_id": gap_id,
        }

    try:
        intake = await _invoke_intake_draft(
            state,
            llm,
            query=query,
            profile=profile,
            existing_intake=existing_intake,
            knowledge_context=knowledge_context,
        )
    except Exception as exc:
        logger.warning(
            "LearningPathIntakeAgent structured output failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        error_detail = f"{type(exc).__name__}: {exc}"
        return {
            "error": f"{LEARNING_PATH_INTAKE_RETRY_ERROR} ({error_detail})",
            "hard_error": True,
        }

    _check_risk_pending(state, intake)
    _persist_learning_path_intake(state, intake)
    return {
        "learning_path_intake": intake,
        "response": _draft_response_text(intake),
    }


def create_learning_path_intake_agent_node(llm: BaseChatModel):
    async def learning_path_intake_agent_node(state: OrchestrationState) -> dict:
        agent_result = await run_learning_path_intake_agent(state, llm)

        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )

        result = {"messages": [tool_message]}
        if agent_result.get("learning_path_intake") is not None:
            result["learning_path_intake"] = agent_result["learning_path_intake"]
            result["response"] = agent_result.get("response", "")
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return learning_path_intake_agent_node


def _intake_from_message(message: object) -> dict | None:
    if isinstance(message, dict) and message.get("type") == "learning_path_intake":
        return message
    if not isinstance(message, BaseMessage):
        return None
    content = message.content
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        intake = parsed.get("learning_path_intake", parsed)
        if isinstance(intake, dict) and intake.get("type") == "learning_path_intake":
            return intake
    return None


async def _invoke_intake_draft(
    state: OrchestrationState | dict,
    llm: BaseChatModel,
    *,
    query: str,
    profile: dict,
    existing_intake: dict | None,
    knowledge_context: dict,
) -> dict:
    if not hasattr(llm, "with_structured_output"):
        logger.warning(
            "LearningPathIntakeAgent LLM lacks structured output; "
            "using local draft fallback."
        )
        return _build_intake_draft(
            state,
            profile,
            query=query,
            user_modification_summary=query
            if is_intake_modification_query(query)
            else "",
            knowledge_context=knowledge_context,
        )

    structured_llm = llm.with_structured_output(LearningPathIntakeDraftOutput)
    messages = [
        SystemMessage(content=LEARNING_PATH_INTAKE_AGENT_SYSTEM_PROMPT),
        HumanMessage(
            content=_build_intake_generation_input(
                state, query, profile, existing_intake, knowledge_context
            )
        ),
    ]
    if hasattr(structured_llm, "ainvoke"):
        invoke_result = structured_llm.ainvoke(messages)
    elif callable(structured_llm):
        invoke_result = structured_llm(messages)
    else:
        logger.warning(
            "LearningPathIntakeAgent structured output is not invokable; "
            "using local draft fallback."
        )
        return _build_intake_draft(
            state,
            profile,
            query=query,
            user_modification_summary=query
            if is_intake_modification_query(query)
            else "",
            knowledge_context=knowledge_context,
        )

    result = await asyncio.wait_for(
        invoke_result,
        timeout=LEARNING_PATH_INTAKE_STRUCTURED_TIMEOUT_SECONDS,
    )
    intake = _normalize_intake_draft(
        _raw_intake_to_dict(result),
        profile=profile,
        query=query,
        knowledge_context=knowledge_context,
    )
    return LearningPathIntakeOutput.model_validate(intake).model_dump()


def _raw_intake_to_dict(result: object) -> dict:
    if isinstance(result, LearningPathIntakeOutput | LearningPathIntakeDraftOutput):
        return result.model_dump()
    if hasattr(result, "model_dump"):
        dumped = result.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if isinstance(result, dict):
        return copy.deepcopy(result)
    return LearningPathIntakeOutput.model_validate(result).model_dump()


def _build_intake_generation_input(
    state: OrchestrationState | dict,
    query: str,
    profile: dict,
    existing_intake: dict | None,
    knowledge_context: dict,
) -> str:
    require_profile_for_intake({"profile": profile})
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    query = "\n".join(
        [
            "请根据以下上下文生成课程草案 JSON。",
            f"用户最新输入：{query}",
            f"已完成画像：{json.dumps(confirmed, ensure_ascii=False)}",
            f"画像摘要：{profile.get('summary_text') or profile.get('text') or ''}",
            f"已有课程草案：{json.dumps(existing_intake or {}, ensure_ascii=False)}",
            "已有学习路径："
            f"{json.dumps(state.get('year_learning_paths') or {}, ensure_ascii=False)}",
            "已发布知识库教材上下文："
            f"{json.dumps(knowledge_context, ensure_ascii=False)}",
            "生成规则：",
            "- 课程数量必须由你根据画像和目标判断，但只能在 4-8 门之间。",
            "- 课程只能从已发布知识库教材上下文中推荐。",
            "- 每门课程的 source_textbook_id、source_textbook_title、"
            "source_outline_section_ids 必须来自已发布知识库教材上下文。",
            "- 已发布知识库教材上下文不包含教材正文，不要编造教材正文。",
            "- 课程顺序会被正式学习路径智能体严格继承；"
            "请把 courses 按用户真正应该学习的先后顺序输出。",
            "- source_outline_section_ids 会继续传递给大纲、Markdown、"
            "视频和动画智能体，不能绑定到与课程目的无关的教材小节。",
            "- 每门课程的 purpose 必须说明教材小节覆盖的具体学习边界，"
            "便于后续大纲与 Markdown 资源生成。",
            "- 课程必须与用户目标、年级、基础、偏好和每周时间匹配。",
            "- 如果用户自然表达了修改方向，要吸收修改并输出新的 draft。",
            "- 不要输出 confirmed；用户确认由系统单独处理。",
            "- 不要输出自然语言解释，只输出结构化对象。",
        ]
    )
    budget = apply_prompt_budget(query, phase="intake")
    return (
        f"{budget.text}\n\n"
        f"prompt_budget_applied={str(budget.prompt_budget_applied).lower()}"
    )


def _normalize_intake_draft(
    intake: dict,
    *,
    profile: dict,
    query: str,
    knowledge_context: dict,
) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    grade_name = str(confirmed.get("current_grade", "")).strip()
    grade_year = grade_year_from_current_grade(grade_name)
    intake["type"] = "learning_path_intake"
    intake["status"] = "draft"
    if grade_name:
        intake["grade_name"] = grade_name
    if grade_year:
        intake["grade_year"] = grade_year
    if (
        is_intake_modification_query(query)
        and not str(intake.get("user_modification_summary", "")).strip()
    ):
        intake["user_modification_summary"] = query
    intake["requires_second_confirmation"] = False
    intake["risk_warnings"] = []
    _require_intake_courses_from_knowledge_context(intake, knowledge_context)
    return intake


def _build_intake_draft(
    state: OrchestrationState | dict,
    profile: dict,
    *,
    query: str,
    user_modification_summary: str,
    knowledge_context: dict,
) -> dict:
    confirmed = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    current_grade = (
        confirmed.get("current_grade", "") if isinstance(confirmed, dict) else ""
    )
    grade_name = str(current_grade).strip()
    grade_year = grade_year_from_current_grade(grade_name)
    learning_topic = _learning_topic_from_texts(query, profile, confirmed)
    courses = _bind_fallback_course_sources(
        _courses_for_topic(learning_topic), state, grade_year, knowledge_context
    )
    draft = {
        "type": "learning_path_intake",
        "status": "draft",
        "grade_year": grade_year,
        "grade_name": grade_name,
        "learning_topic": learning_topic,
        "courses": courses,
        "recommendation_reasons": _recommendation_reasons(confirmed, learning_topic),
        "user_modification_summary": user_modification_summary,
        "risk_warnings": [],
        "requires_second_confirmation": False,
    }
    return LearningPathIntakeOutput.model_validate(draft).model_dump()


def _bind_fallback_course_sources(
    courses: list[dict[str, str]],
    state: OrchestrationState | dict,
    grade_year: str,
    knowledge_context: dict,
) -> list[dict[str, object]]:
    source_bindings = _source_bindings_from_knowledge_context(knowledge_context)
    if not source_bindings:
        source_bindings = _source_bindings_from_existing_paths(state, grade_year)
    if not source_bindings:
        raise ValueError("本地课程草案无法找到已有课程来源绑定。")

    bound_courses: list[dict[str, object]] = []
    for index, course in enumerate(courses):
        source = _source_binding_for_course(course, source_bindings, index)
        bound_courses.append({**course, **source})
    return bound_courses


def _published_textbook_context_for_intake(
    learning_topic: str,
    query: str,
    profile: dict,
) -> dict:
    summary = profile.get("summary_text") or profile.get("text") or ""
    student_goal_summary = "\n".join(
        text for text in (query, str(summary)) if text.strip()
    )
    with Session(get_engine()) as db_session:
        return get_published_textbook_context_for_topic(
            db_session,
            learning_topic,
            student_goal_summary=student_goal_summary,
        )


def _source_bindings_from_knowledge_context(
    knowledge_context: dict,
) -> list[dict[str, object]]:
    textbooks = knowledge_context.get("textbooks")
    if not isinstance(textbooks, list):
        return []

    bindings: list[dict[str, object]] = []
    for textbook in textbooks:
        if not isinstance(textbook, dict):
            continue
        textbook_id = str(textbook.get("textbook_id", "")).strip()
        title = str(textbook.get("title", "")).strip()
        outline_summary = textbook.get("outline_summary")
        if not textbook_id or not title or not isinstance(outline_summary, list):
            continue
        sections = _outline_sections_from_textbook(textbook)
        if not sections:
            continue
        bindings.append(
            {
                "source_textbook_id": textbook_id,
                "source_textbook_title": title,
                "source_outline_sections": sections,
                "source_outline_section_ids": [sections[0]["section_id"]],
            }
        )
    return bindings


def _outline_sections_from_textbook(textbook: dict) -> list[dict[str, str]]:
    outline_summary = textbook.get("outline_summary")
    if not isinstance(outline_summary, list):
        return []
    sections: list[dict[str, str]] = []
    for section in outline_summary:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id", "")).strip()
        title = str(section.get("title", "")).strip()
        if section_id and title:
            sections.append({"section_id": section_id, "title": title})
    return sections


def _source_binding_for_course(
    course: dict[str, str],
    source_bindings: list[dict[str, object]],
    course_index: int,
) -> dict[str, object]:
    course_text = " ".join(
        str(course.get(key, "")).strip() for key in ("title", "purpose")
    )
    best_source, best_section_id = _best_source_section_for_course(
        course_text, source_bindings
    )
    if best_source is None:
        best_source = source_bindings[course_index % len(source_bindings)]
        best_section_id = _first_source_section_id(best_source)

    selected_section_id = best_section_id or _first_source_section_id(best_source)

    return {
        "source_textbook_id": best_source["source_textbook_id"],
        "source_textbook_title": best_source["source_textbook_title"],
        "source_outline_section_ids": [selected_section_id],
    }


def _best_source_section_for_course(
    course_text: str,
    source_bindings: list[dict[str, object]],
) -> tuple[dict[str, object] | None, str]:
    best_source: dict[str, object] | None = None
    best_section_id = ""
    best_score = -1
    for source in source_bindings:
        for section in _outline_sections_from_source_binding(source):
            score = _section_match_score(course_text, section["title"])
            if score > best_score:
                best_source = source
                best_section_id = section["section_id"]
                best_score = score
    return best_source, best_section_id


def _outline_sections_from_source_binding(
    source: dict[str, object],
) -> list[dict[str, str]]:
    sections = source.get("source_outline_sections")
    if isinstance(sections, list) and sections:
        return [
            {"section_id": str(section["section_id"]), "title": str(section["title"])}
            for section in sections
            if isinstance(section, dict)
            and str(section.get("section_id", "")).strip()
            and str(section.get("title", "")).strip()
        ]
    first_section_id = _first_source_section_id(source)
    return [{"section_id": first_section_id, "title": ""}] if first_section_id else []


def _first_source_section_id(source: dict[str, object]) -> str:
    section_ids = source.get("source_outline_section_ids")
    if isinstance(section_ids, list) and section_ids:
        return str(section_ids[0]).strip()
    return ""


def _section_match_score(course_text: str, section_title: str) -> int:
    course_key = _match_key(course_text)
    section_key = _match_key(section_title)
    if not course_key or not section_key:
        return 0
    score = 0
    if section_key in course_key:
        score += 100
    if course_key in section_key:
        score += 80
    section_terms = _match_terms(section_key)
    for term in section_terms:
        if term in course_key:
            score += len(term) * 5
    course_terms = _match_terms(course_key)
    score += len(set(course_terms) & set(section_terms)) * 3
    return score


def _match_key(value: object) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _match_terms(value: str) -> list[str]:
    if len(value) <= 2:
        return [value] if value else []
    terms = [value[index : index + 2] for index in range(len(value) - 1)]
    terms.extend(value[index : index + 3] for index in range(len(value) - 2))
    return terms


def _require_intake_courses_from_knowledge_context(
    intake: dict,
    knowledge_context: dict,
) -> None:
    allowed_sections_by_textbook_id = _allowed_sections_by_textbook_id(
        knowledge_context
    )
    if not allowed_sections_by_textbook_id:
        raise ValueError("课程草案缺少已发布教材上下文。")
    for course in intake.get("courses", []):
        if not isinstance(course, dict):
            raise ValueError("课程草案课程格式无效。")
        source_textbook_id = str(course.get("source_textbook_id", "")).strip()
        if source_textbook_id not in allowed_sections_by_textbook_id:
            raise ValueError("课程草案教材来源不在已发布知识库上下文中。")
        source_section_ids = _source_section_ids_from_course(course)
        if not source_section_ids:
            raise ValueError("课程草案缺少教材小节绑定。")
        allowed_section_ids = allowed_sections_by_textbook_id[source_textbook_id]
        has_unknown_section = any(
            section_id not in allowed_section_ids for section_id in source_section_ids
        )
        if has_unknown_section:
            raise ValueError("课程草案教材小节不在已发布知识库上下文中。")


def _allowed_sections_by_textbook_id(knowledge_context: dict) -> dict[str, set[str]]:
    textbooks = knowledge_context.get("textbooks", [])
    if not isinstance(textbooks, list):
        return {}
    allowed_sections: dict[str, set[str]] = {}
    for textbook in textbooks:
        if not isinstance(textbook, dict):
            continue
        textbook_id = str(textbook.get("textbook_id", "")).strip()
        if textbook_id:
            allowed_sections[textbook_id] = {
                section["section_id"]
                for section in _outline_sections_from_textbook(textbook)
            }
    return allowed_sections


def _source_section_ids_from_course(course: dict) -> list[str]:
    return [
        str(section_id).strip()
        for section_id in course.get("source_outline_section_ids", [])
        if str(section_id).strip()
    ]


def _source_bindings_from_existing_paths(
    state: OrchestrationState | dict, grade_year: str
) -> list[dict[str, object]]:
    year_learning_paths = state.get("year_learning_paths")
    bindings: list[dict[str, object]] = []
    for path in iter_year_learning_paths(year_learning_paths, grade_year):
        path_grade_plans = path.get("grade_plans", {})
        if not isinstance(path_grade_plans, dict):
            continue
        ordered_grade_years = [grade_year]
        ordered_grade_years.extend(
            available_grade_year
            for available_grade_year in path_grade_plans
            if available_grade_year != grade_year
        )
        for path_grade_year in ordered_grade_years:
            for course in get_grade_courses(path, path_grade_year):
                source = _source_binding_from_course(course)
                if source is not None:
                    bindings.append(source)
    return bindings


def _source_binding_from_course(course: dict) -> dict[str, object] | None:
    source_textbook_id = str(course.get("source_textbook_id", "")).strip()
    source_textbook_title = str(course.get("source_textbook_title", "")).strip()
    source_outline_section_ids = [
        str(section_id).strip()
        for section_id in course.get("source_outline_section_ids", [])
        if str(section_id).strip()
    ]
    if (
        not source_textbook_id
        or not source_textbook_title
        or not source_outline_section_ids
    ):
        return None
    return {
        "source_textbook_id": source_textbook_id,
        "source_textbook_title": source_textbook_title,
        "source_outline_section_ids": source_outline_section_ids,
    }


def _learning_topic_from_texts(query: str, profile: dict, confirmed: dict) -> str:
    texts = [
        query,
        str(confirmed.get("short_term_goal", "")),
        str(confirmed.get("long_term_goal", "")),
        str(profile.get("summary_text", "")) if isinstance(profile, dict) else "",
        str(profile.get("text", "")) if isinstance(profile, dict) else "",
    ]
    combined = "\n".join(text for text in texts if text)
    for marker, topic in TOPIC_MARKERS:
        if marker in combined:
            return topic
    return (
        str(confirmed.get("short_term_goal", "")).replace("学习", "", 1).strip()
        or "学习路径"
    )


def _courses_for_topic(learning_topic: str) -> list[dict[str, str]]:
    if learning_topic == "数据结构":
        return [
            {
                "title": "数据结构入门与复杂度基础",
                "purpose": "建立抽象数据类型、复杂度和基本分析能力",
            },
            {
                "title": "线性结构实践",
                "purpose": "掌握数组、链表、栈、队列的实现与使用场景",
            },
            {
                "title": "树与递归基础",
                "purpose": "理解树结构、递归遍历和层次化问题拆解",
            },
            {
                "title": "查找、排序与哈希",
                "purpose": "建立常见查找排序策略和哈希表应用能力",
            },
            {
                "title": "图结构与综合项目",
                "purpose": "完成图遍历、路径问题和综合数据结构应用",
            },
        ]
    if learning_topic == "算法":
        return [
            {"title": "算法复杂度与问题建模", "purpose": "建立算法分析和输入规模意识"},
            {"title": "基础排序与查找算法", "purpose": "掌握常见排序、二分和哈希查找"},
            {"title": "递归、分治与回溯", "purpose": "训练结构化拆解复杂问题"},
            {"title": "动态规划入门", "purpose": "掌握状态定义、转移和边界处理"},
        ]
    return [
        {"title": f"{learning_topic}入门基础", "purpose": "建立方向认知和基础概念"},
        {
            "title": f"{learning_topic}核心能力训练",
            "purpose": "围绕核心技能进行系统练习",
        },
        {"title": f"{learning_topic}实践任务", "purpose": "通过小项目形成可验证产出"},
        {"title": f"{learning_topic}综合复盘", "purpose": "总结学习成果并明确下一步"},
    ]


def _recommendation_reasons(confirmed: dict, learning_topic: str) -> list[str]:
    reasons = [f"近期目标指向{learning_topic}"]
    current_grade = str(confirmed.get("current_grade", "")).strip()
    if current_grade:
        reasons.append(f"当前年级是{current_grade}，适合先形成可持续的课程顺序")
    learning_stage = str(confirmed.get("learning_stage", "")).strip()
    if learning_stage:
        reasons.append(f"当前阶段是{learning_stage}，先从基础和实践闭环开始")
    pace = str(confirmed.get("learning_pace_preference", "")).strip()
    if pace:
        reasons.append(f"学习节奏偏好为{pace}，课程数量保持适中")
    return reasons[:4]


def _draft_response_text(intake: dict) -> str:
    courses = intake.get("courses", [])
    course_lines = [
        f"{index}. {course.get('title')}：{course.get('purpose')}"
        for index, course in enumerate(courses, start=1)
        if isinstance(course, dict)
    ]
    reasons = intake.get("recommendation_reasons", [])
    reason_text = "；".join(str(reason) for reason in reasons if str(reason).strip())

    lines = [
        "基础画像已经完成，我先把正式学习路径生成前的课程草稿整理出来。",
        f"推荐理由：{reason_text}。",
        f"年级：{intake.get('grade_name')}；主题：{intake.get('learning_topic')}。",
        "课程草稿：",
        *course_lines,
    ]

    if intake.get("status") == "risk_pending":
        lines.append("\n⚠️【风险提示】检测到本次修改包含以下敏感操作：")
        lines.extend(f"- {w}" for w in intake.get("risk_warnings", []))
        lines.append(
            "这会导致相关课程的已生成内容或进度丢失。下一步是确认是否继续替换或删除这些课程。确认继续修改可直接回复“确认”“可以”“好的”“行”“继续”，也可以说“先不改”保留原路径。"
        )
    else:
        lines.append(
            "下一步是生成正式学习路径，系统会把这份草稿变成具体课程顺序、学习目标、时间安排和下一步行动。可以开始下一步吗？如果同意，可以直接回复“确认”“可以”“继续”，也可以点击“确认并生成学习路径”。如果想改，直接说“把第2门换成算法实战”“删掉第3门”或“主题改成前端”。"
        )

    return "\n".join(lines)


def _check_risk_pending(state: OrchestrationState | dict, intake: dict) -> None:  # noqa: C901
    user_id = state.get("user_id", "")
    if not user_id:
        return

    protected = {}
    from sqlmodel import Session, select

    from app.database import get_engine
    from app.models import UserCourseKnowledgeOutline

    try:
        with Session(get_engine()) as db_session:
            outlines = db_session.exec(
                select(UserCourseKnowledgeOutline).where(
                    UserCourseKnowledgeOutline.user_uid == user_id
                )
            ).all()
            for o in outlines:
                if o.course_name:
                    protected[o.course_name.strip()] = "已有课程大纲"
    except Exception as exc:
        logger.warning("Failed to query course outlines for user %s: %s", user_id, exc)

    year_paths = state.get("year_learning_paths")
    if (not year_paths or not isinstance(year_paths, dict)) and user_id:
        try:
            with Session(get_engine()) as db_session:
                from app.services.learning_path_service import (
                    get_all_year_learning_paths,
                )

                year_paths = get_all_year_learning_paths(db_session, user_id)
        except Exception as exc:
            logger.warning(
                "Failed to query year learning paths for user %s: %s", user_id, exc
            )

    if isinstance(year_paths, dict):
        for grade_year, path in year_paths.items():
            if not isinstance(path, dict):
                continue
            current = path.get("current_learning_course")
            if isinstance(current, dict):
                curr_title = current.get("course_or_chapter_theme")
                curr_state = current.get("progress_state")
                if curr_title and curr_state in {"in_progress", "completed"}:
                    protected[curr_title.strip()] = "已开始学习"
            grade_plans = path.get("grade_plans", {})
            if isinstance(grade_plans, dict):
                for gp in grade_plans.values():
                    if not isinstance(gp, dict):
                        continue
                    course_nodes = gp.get("course_nodes", [])
                    if isinstance(course_nodes, list):
                        for c in course_nodes:
                            if isinstance(c, dict):
                                c_title = c.get("course_or_chapter_theme")
                                c_state = c.get("progress_state")
                                if c_title and c_state in {"in_progress", "completed"}:
                                    protected[c_title.strip()] = "已开始学习"

    new_course_titles = {
        c.get("title", "").strip()
        for c in intake.get("courses", [])
        if isinstance(c, dict)
    }
    warnings = []
    for title, reason in protected.items():
        if title not in new_course_titles:
            warnings.append(f"替换/删除{reason}的课程《{title}》")

    if warnings:
        intake["status"] = "risk_pending"
        intake["requires_second_confirmation"] = True
        intake["risk_warnings"] = warnings


def _confirmed_response_text(intake: dict) -> str:
    topic = intake.get("learning_topic", "")
    return (
        f"好的，已确认这份{topic}学习路径草稿。下一步会生成正式学习路径，"
        "包括课程顺序、学习目标、时间安排和下一步行动。"
    )


def _risk_cancelled_response_text(intake: dict) -> str:
    topic = intake.get("learning_topic", "")
    topic_text = f"{topic}的" if topic else ""
    return (
        f"好的，已保留原学习路径，不做本次修改。{topic_text}"
        "课程草稿已回到普通草稿状态，你也可以继续告诉我哪里需要修改。"
    )


def _persist_learning_path_intake(
    state: OrchestrationState | dict, intake: dict
) -> None:
    session_id = str(state.get("session_id", "")).strip()
    user_id = str(state.get("user_id", "")).strip()
    if not session_id or not user_id:
        return

    from sqlmodel import Session

    try:
        with Session(get_engine()) as db_session:
            load_or_create_session(db_session, session_id, user_id)
            replace_latest_learning_path_intake(db_session, session_id, intake)
    except Exception as exc:
        logger.warning(
            "Failed to persist learning_path_intake for session %s: %s", session_id, exc
        )
