from __future__ import annotations

import asyncio
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.models import CourseKnowledgeDraftOutput, CourseKnowledgeOutput
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState
from app.services.learning_path_service import iter_year_learning_paths

logger = logging.getLogger(__name__)

_STRUCTURED_OUTLINE_TIMEOUT_SECONDS = 45.0


def _select_course_for_outline(
    year_learning_paths: dict | None,
    course_id: str,
    latest_grade_year: str = "",
) -> dict:
    if not year_learning_paths:
        raise ValueError("学习路径不存在，无法生成课程章节。")
    explicit_course_requested = isinstance(course_id, str) and bool(course_id.strip())
    for path in iter_year_learning_paths(year_learning_paths, latest_grade_year):
        if not isinstance(path, dict):
            continue
        grade_plans = path.get("grade_plans")
        if course_id and isinstance(grade_plans, dict):
            for grade_plan in grade_plans.values():
                if not isinstance(grade_plan, dict):
                    continue
                course_nodes = grade_plan.get("course_nodes")
                if not isinstance(course_nodes, list):
                    continue
                for course in course_nodes:
                    if isinstance(course, dict) and course.get("course_node_id") == course_id:
                        return course
        if explicit_course_requested:
            continue
        current = path.get("current_learning_course")
        if not isinstance(current, dict):
            continue
        grade_id = current.get("grade_id")
        current_course_id = current.get("course_node_id")
        if not isinstance(grade_plans, dict):
            continue
        grade_plan = grade_plans.get(grade_id)
        if not isinstance(grade_plan, dict):
            continue
        course_nodes = grade_plan.get("course_nodes")
        if not isinstance(course_nodes, list):
            continue
        for course in course_nodes:
            if isinstance(course, dict) and course.get("course_node_id") == current_course_id:
                return course
    if explicit_course_requested:
        raise ValueError("指定课程无法定位。")
    raise ValueError("学习路径中的当前课程无法定位。")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text.lower() in {"none", "null"}:
        return ""
    return text


def _strip_top_level_title_prefix(title: str) -> str:
    if not title:
        return ""
    prefixes = ("第一章：", "第二章：", "第三章：", "第四章：", "第五章：", "第六章：", "第七章：", "第八章：", "第九章：", "第十章：")
    for prefix in prefixes:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title


def _chapter_label(section_id: str) -> str:
    return f"第{section_id}章" if "." not in section_id else section_id


def _to_chinese_chapter_number(section_id: str) -> str:
    digits = {
        "0": "零",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
        "7": "七",
        "8": "八",
        "9": "九",
    }
    value = int(section_id)
    if value < 10:
        return digits[str(value)]
    if value == 10:
        return "十"
    if value < 20:
        return f"十{digits[str(value % 10)]}"
    tens = value // 10
    ones = value % 10
    if ones == 0:
        return f"{digits[str(tens)]}十"
    return f"{digits[str(tens)]}十{digits[str(ones)]}"


def _chapter_sequence_label(section_id: str) -> str:
    if "." in section_id:
        return section_id
    return f"第{_to_chinese_chapter_number(section_id)}章"


def _learning_sequence_texts(
    sections: list[dict],
    preferred_ids: list[str] | None = None,
) -> list[str]:
    section_map = {
        section["section_id"]: section
        for section in sections
        if isinstance(section, dict) and isinstance(section.get("section_id"), str)
    }
    sequence_ids = preferred_ids or list(section_map.keys())
    sequence_texts: list[str] = []
    for section_id in sequence_ids:
        section = section_map.get(section_id)
        if not section:
            continue
        title = _clean_text(section.get("title"))
        if not title:
            continue
        sequence_texts.append(f"{_chapter_sequence_label(section_id)}：{title}")
    return sequence_texts


def _build_local_sections(selected_course: dict) -> list[dict]:
    learning_sequence = _string_list(selected_course.get("learning_sequence"))
    key_points = _string_list(selected_course.get("key_points"))
    difficult_points = _string_list(selected_course.get("difficult_points"))
    acceptance_criteria = _string_list(selected_course.get("acceptance_criteria"))

    sections: list[dict] = []
    order_index = 1

    for index, step in enumerate(learning_sequence, start=1):
        section_id = str(index)
        chapter_key_points: list[str] = []
        if index - 1 < len(key_points):
            chapter_key_points.append(key_points[index - 1])
        if not chapter_key_points:
            chapter_key_points.append(step)
        sections.append(
            {
                "section_id": section_id,
                "parent_section_id": None,
                "depth": 1,
                "title": step,
                "order_index": order_index,
                "description": f"围绕「{step}」推进当前课程的主线阶段任务。",
                "key_knowledge_points": chapter_key_points,
            }
        )
        order_index += 1

        objective_points = [step]
        if index - 1 < len(key_points):
            objective_points.append(key_points[index - 1])
        sections.append(
            {
                "section_id": f"{section_id}.1",
                "parent_section_id": section_id,
                "depth": 2,
                "title": "学习目标",
                "order_index": order_index,
                "description": f"明确「{step}」这一章学完以后必须达到的理解深度与产出目标。",
                "key_knowledge_points": objective_points,
            }
        )
        order_index += 1

        task_points: list[str] = [step]
        if index - 1 < len(key_points):
            task_points.append(key_points[index - 1])
        sections.append(
            {
                "section_id": f"{section_id}.2",
                "parent_section_id": section_id,
                "depth": 2,
                "title": "任务拆解",
                "order_index": order_index,
                "description": f"把「{step}」拆成按顺序可执行的练习、实现与交付任务。",
                "key_knowledge_points": task_points,
            }
        )
        order_index += 1

        checkpoint_points: list[str] = []
        if index - 1 < len(difficult_points):
            checkpoint_points.append(difficult_points[index - 1])
        if index - 1 < len(acceptance_criteria):
            checkpoint_points.append(acceptance_criteria[index - 1])
        if index == len(learning_sequence) and difficult_points:
            checkpoint_points.extend(
                item for item in difficult_points
                if item not in checkpoint_points
            )
        if index == len(learning_sequence) and acceptance_criteria:
            checkpoint_points.extend(
                item for item in acceptance_criteria
                if item not in checkpoint_points
            )
        if not checkpoint_points and index - 1 < len(key_points):
            checkpoint_points.append(key_points[index - 1])
        sections.append(
            {
                "section_id": f"{section_id}.3",
                "parent_section_id": section_id,
                "depth": 2,
                "title": "检查点",
                "order_index": order_index,
                "description": f"确认「{step}」这一章是否真正学会，并核对进入下一章前必须满足的检查标准。",
                "key_knowledge_points": checkpoint_points,
            }
        )
        order_index += 1

    if sections:
        return sections

    return [
        {
            "section_id": "1",
            "parent_section_id": None,
            "depth": 1,
            "title": "课程导入",
            "order_index": 1,
            "description": "梳理课程目标、任务边界与学习方式。",
            "key_knowledge_points": ["课程目标", "任务边界"],
        },
        {
            "section_id": "1.1",
            "parent_section_id": "1",
            "depth": 2,
            "title": "学习目标",
            "order_index": 2,
            "description": "确认当前课程最先要完成的核心任务与验收标准。",
            "key_knowledge_points": ["核心任务", "验收标准"],
        },
        {
            "section_id": "1.2",
            "parent_section_id": "1",
            "depth": 2,
            "title": "任务拆解",
            "order_index": 3,
            "description": "把首章拆成可执行的学习任务与实现步骤。",
            "key_knowledge_points": ["学习步骤", "实现任务"],
        },
        {
            "section_id": "1.3",
            "parent_section_id": "1",
            "depth": 2,
            "title": "检查点",
            "order_index": 4,
            "description": "确认是否具备继续推进下一章的条件。",
            "key_knowledge_points": ["完成确认", "推进条件"],
        },
    ]


def _build_local_course_outline(selected_course: dict, profile: dict) -> dict:
    course_id = _clean_text(selected_course.get("course_node_id"))
    course_name = _clean_text(selected_course.get("course_or_chapter_theme"))
    grade_year = _clean_text(selected_course.get("grade_id"))
    course_goal = _clean_text(selected_course.get("course_goal"))
    learning_sequence = _string_list(selected_course.get("learning_sequence"))
    key_points = _string_list(selected_course.get("key_points"))
    difficult_points = _string_list(selected_course.get("difficult_points"))
    acceptance_criteria = _string_list(selected_course.get("acceptance_criteria"))
    confirmed_info = profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    current_grade = _clean_text(confirmed_info.get("current_grade"))
    weekly_available_time = _clean_text(confirmed_info.get("weekly_available_time"))
    constraints = _clean_text(confirmed_info.get("constraints"))
    sections = _build_local_sections(selected_course)
    section_ids = [section["section_id"] for section in sections if isinstance(section, dict)]
    preferred_sequence_ids = [
        section_id
        for section_id in section_ids
        if "." not in section_id
    ]

    summary_parts = [
        f"当前课程面向{current_grade or grade_year}阶段学习安排。",
        f"课程目标：{course_goal or '完成当前课程核心任务。'}",
    ]
    if weekly_available_time:
        summary_parts.append(f"建议投入：{weekly_available_time}。")
    if constraints:
        summary_parts.append(f"节奏约束：{constraints}。")
    if key_points:
        summary_parts.append(f"优先掌握：{'、'.join(key_points)}。")
    if difficult_points:
        summary_parts.append(f"重点突破：{'、'.join(difficult_points)}。")
    if acceptance_criteria:
        summary_parts.append(f"最终验收：{'；'.join(acceptance_criteria)}。")

    outline = CourseKnowledgeOutput(
        course_id=course_id,
        course_name=course_name,
        grade_year=grade_year,
        personalization_summary="".join(summary_parts),
        sections=sections,
        learning_sequence=_learning_sequence_texts(sections, preferred_sequence_ids),
        total_estimated_hours=f"{max(len(learning_sequence), 1) * 3}-{max(len(learning_sequence), 1) * 5} 小时",
    )
    return outline.model_dump()


def _normalize_total_estimated_hours(value: object, fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    if isinstance(value, int):
        return f"{value} 小时"
    return fallback


def _normalize_generated_sections(raw_sections: object, fallback_sections: list[dict]) -> list[dict]:
    if not isinstance(raw_sections, list) or not raw_sections:
        return fallback_sections

    normalized_sections: list[dict] = []
    for index, item in enumerate(raw_sections, start=1):
        if hasattr(item, "model_dump"):
            payload = item.model_dump()
        elif isinstance(item, dict):
            payload = item
        else:
            continue

        title = _clean_text(payload.get("title"))
        if not title:
            continue

        section_id = _clean_text(payload.get("section_id")) or str(index)
        if "." not in section_id:
            title = _strip_top_level_title_prefix(title)
        parent_section_id = payload.get("parent_section_id")
        if parent_section_id is not None:
            parent_section_id = _clean_text(parent_section_id) or None
        depth = payload.get("depth")
        if not isinstance(depth, int):
            depth = section_id.count(".") + 1
        order_index = payload.get("order_index")
        if not isinstance(order_index, int):
            order_index = index

        normalized_sections.append(
            {
                "section_id": section_id,
                "parent_section_id": parent_section_id,
                "depth": depth,
                "title": title,
                "order_index": order_index,
                "description": _clean_text(payload.get("description")),
                "key_knowledge_points": _string_list(payload.get("key_knowledge_points")),
            }
        )

    if not normalized_sections:
        return fallback_sections

    has_nested_sections = any(
        section.get("parent_section_id") is not None and int(section.get("depth", 1)) > 1
        for section in normalized_sections
        if isinstance(section, dict)
    )
    if not has_nested_sections:
        return fallback_sections

    top_level_ids = {
        section["section_id"]
        for section in normalized_sections
        if isinstance(section, dict) and section.get("parent_section_id") is None
    }
    child_parent_ids = {
        section["parent_section_id"]
        for section in normalized_sections
        if isinstance(section, dict) and section.get("parent_section_id") is not None
    }
    if top_level_ids and not top_level_ids.issubset(child_parent_ids):
        return fallback_sections

    top_level_children: dict[str, list[dict]] = {}
    for section in normalized_sections:
        if not isinstance(section, dict):
            continue
        parent_section_id = section.get("parent_section_id")
        if parent_section_id is None:
            continue
        top_level_children.setdefault(str(parent_section_id), []).append(section)

    required_titles = {"学习目标", "任务拆解", "检查点"}
    for top_level_id in top_level_ids:
        children = top_level_children.get(top_level_id, [])
        child_titles = {
            _clean_text(child.get("title"))
            for child in children
            if isinstance(child, dict)
        }
        if child_titles != required_titles:
            return fallback_sections
        expected_child_ids = {f"{top_level_id}.1", f"{top_level_id}.2", f"{top_level_id}.3"}
        actual_child_ids = {
            _clean_text(child.get("section_id"))
            for child in children
            if isinstance(child, dict)
        }
        if actual_child_ids != expected_child_ids:
            return fallback_sections

    return normalized_sections


def _normalize_generated_course_outline(
    selected_course: dict,
    profile: dict,
    raw_outline: object,
) -> dict:
    fallback_outline = _build_local_course_outline(selected_course, profile)
    if hasattr(raw_outline, "model_dump"):
        payload = raw_outline.model_dump()
    elif isinstance(raw_outline, dict):
        payload = raw_outline
    else:
        return fallback_outline

    course_id = _clean_text(payload.get("course_id")) or fallback_outline["course_id"]
    course_name = _clean_text(payload.get("course_name")) or fallback_outline["course_name"]
    grade_year = _clean_text(payload.get("grade_year")) or fallback_outline["grade_year"]
    personalization_summary = (
        _clean_text(payload.get("personalization_summary"))
        or fallback_outline["personalization_summary"]
    )
    sections = _normalize_generated_sections(payload.get("sections"), fallback_outline["sections"])
    section_ids = [section["section_id"] for section in sections if isinstance(section, dict)]
    learning_sequence = _string_list(payload.get("learning_sequence"))
    if learning_sequence and all(section_id in section_ids for section_id in learning_sequence):
        learning_sequence = _learning_sequence_texts(sections, learning_sequence)
    elif learning_sequence:
        learning_sequence = [step for step in learning_sequence if step]
    else:
        preferred_sequence_ids = [section_id for section_id in section_ids if "." not in section_id]
        learning_sequence = _learning_sequence_texts(sections, preferred_sequence_ids)
    total_estimated_hours = _normalize_total_estimated_hours(
        payload.get("total_estimated_hours"),
        fallback_outline["total_estimated_hours"],
    )

    outline = CourseKnowledgeOutput(
        course_id=course_id,
        course_name=course_name,
        grade_year=grade_year,
        personalization_summary=personalization_summary,
        sections=sections,
        learning_sequence=learning_sequence,
        total_estimated_hours=total_estimated_hours,
    )
    return outline.model_dump()


def _build_analysis_input(selected_course: dict, profile: dict) -> str:
    return (
        "请为以下课程生成详细的章节大纲。\n\n"
        "输出前先完成以下分析：\n"
        "1. 判断这门课的主目标、当前用户基础与最容易卡住的难点。\n"
        "2. 判断哪些章节必须保留为主线，哪些内容应变成阶段任务、实践环节和验收点。\n"
        "3. 判断时间安排和学习节奏应该如何控制。\n"
        "4. 再把分析结果映射成层级化章节大纲。\n\n"
        f"课程信息：{json.dumps(selected_course, ensure_ascii=False, indent=2)}\n"
        f"用户画像：{json.dumps(profile, ensure_ascii=False, indent=2)}"
    )


async def run_course_knowledge_agent(state: OrchestrationState, llm: BaseChatModel) -> dict:
    """Generate detailed course outline, auto-resolving next course if not specified."""
    tool_args = extract_last_tool_call_args(state)
    course_id = tool_args.get("course_id", "")
    latest_grade_year = str(state.get("latest_grade_year", "")).strip()

    profile = state.get("profile", {})
    year_learning_paths = state.get("year_learning_paths", {})
    if not is_complete_profile_data(profile):
        return {"error": "请先完成基础画像。"}
    if not year_learning_paths:
        return {"error": "请先生成学习路径。"}

    try:
        selected_course = _select_course_for_outline(
            state.get("year_learning_paths"),
            course_id,
            latest_grade_year,
        )
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    input_text = _build_analysis_input(selected_course, profile)

    structured_llm = llm.with_structured_output(CourseKnowledgeDraftOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    try:
        result = await asyncio.wait_for(
            chain.ainvoke({"query": input_text}),
            timeout=_STRUCTURED_OUTLINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "CourseKnowledgeAgent structured output timed out after %.1fs",
            _STRUCTURED_OUTLINE_TIMEOUT_SECONDS,
        )
        outline_dict = _build_local_course_outline(selected_course, profile)
        logger.info(
            "CourseKnowledgeAgent fell back to local outline after timeout for user %s, course %s",
            state["user_id"],
            selected_course.get("course_node_id", ""),
        )
    except Exception as exc:
        logger.warning("CourseKnowledgeAgent structured output failed: %s", exc)
        outline_dict = _build_local_course_outline(selected_course, profile)
        logger.info(
            "CourseKnowledgeAgent fell back to local outline for user %s, course %s",
            state["user_id"],
            selected_course.get("course_node_id", ""),
        )
    else:
        outline_dict = _normalize_generated_course_outline(selected_course, profile, result)

    from sqlmodel import Session

    from app.database import get_engine
    from app.services.course_knowledge_service import upsert_user_course_knowledge_outline

    try:
        with Session(get_engine()) as db_session:
            upsert_user_course_knowledge_outline(db_session, state["user_id"], outline_dict)
        logger.info("CourseKnowledgeOutline persisted for user %s, course %s", state["user_id"], course_id)
    except Exception as exc:
        logger.error("Failed to persist course_knowledge for user %s: %s", state["user_id"], exc)
        return {"error": "课程大纲保存失败，请稍后重试。", "hard_error": True}

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
