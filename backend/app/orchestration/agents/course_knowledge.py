"""Course knowledge agent contracts and prompt assembly."""

# ruff: noqa: C901,E501

from __future__ import annotations

import asyncio
import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlmodel import Session

from app.database import get_engine
from app.orchestration.agents.models import (
    CourseKnowledgeOutput,
    SectionItem,
)
from app.orchestration.agents.profile import is_complete_profile_data
from app.orchestration.agents.prompts import COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import (
    extract_last_tool_call_args,
    extract_last_tool_call_id,
)
from app.orchestration.state import OrchestrationState
from app.services.knowledge_base_service import (
    get_textbook_section_binding_context,
    require_student_visible_textbooks,
)
from app.services.learning_path_service import iter_year_learning_paths

logger = logging.getLogger(__name__)

SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS = 180.0
YEAR_COURSE_OUTLINE_TIMEOUT_SECONDS = 360.0
COURSE_KNOWLEDGE_RETRY_ERROR = "课程大纲生成失败，请稍后重试。"
ALL_CURRENT_GRADE_COURSES_ID = "__all_current_grade__"
SOURCE_CONTENT_CHAR_LIMIT = 8000
_JSON_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(?P<body>.*?)```", re.DOTALL | re.IGNORECASE
)


def _normalized_course_match_text(value: object) -> str:
    return re.sub(
        r"[\s《》“”\"'：:，,。！？!?、；;（）()【】\[\]\-_/]+",
        "",
        str(value).strip().lower(),
    )


def _matches_course_identifier(course: dict, explicit_course_text: str) -> bool:
    if not explicit_course_text:
        return False
    course_id = _clean_text(course.get("course_node_id"))
    if course_id == explicit_course_text:
        return True
    course_name_key = _normalized_course_match_text(
        course.get("course_or_chapter_theme", "")
    )
    explicit_key = _normalized_course_match_text(explicit_course_text)
    return bool(course_name_key and explicit_key and course_name_key == explicit_key)


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
                if isinstance(course, dict) and _matches_course_identifier(
                    course, course_id
                ):
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
            if (
                isinstance(course, dict)
                and course.get("course_node_id") == current_course_id
            ):
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


def _extract_json_payload(raw_output: object) -> dict:
    if isinstance(raw_output, dict):
        return raw_output
    if hasattr(raw_output, "content"):
        raw_output = raw_output.content
    if not isinstance(raw_output, str):
        raise ValueError("课程大纲输出不是 JSON 文本。")

    text = raw_output.strip()
    if not text:
        raise ValueError("课程大纲输出为空。")

    code_block_match = _JSON_CODE_BLOCK_PATTERN.search(text)
    if code_block_match:
        text = code_block_match.group("body").strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"课程大纲输出不是合法 JSON：{exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("课程大纲 JSON 顶层必须是对象。")
    return payload


def _strip_top_level_title_prefix(title: str) -> str:
    if not title:
        return ""
    prefixes = (
        "第一章：",
        "第二章：",
        "第三章：",
        "第四章：",
        "第五章：",
        "第六章：",
        "第七章：",
        "第八章：",
        "第九章：",
        "第十章：",
    )
    for prefix in prefixes:
        if title.startswith(prefix):
            return title[len(prefix) :].strip()
    return title


def _strip_subsection_id_prefix(title: str, section_id: str) -> str:
    if not title or not section_id:
        return title
    prefix = f"{section_id} "
    if title.startswith(prefix):
        return title[len(prefix) :].strip()
    prefix_no_space = f"{section_id}　"
    if title.startswith(prefix_no_space):
        return title[len(prefix_no_space) :].strip()
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


def _normalize_total_estimated_hours(value: object, fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    if isinstance(value, int):
        return f"{value} 小时"
    return fallback


def _is_positive_integer_text(value: str) -> bool:
    return value.isdigit() and int(value) > 0


def _is_direct_child_section_id(section_id: str, parent_id: str) -> bool:
    prefix = f"{parent_id}."
    if not section_id.startswith(prefix):
        return False
    suffix = section_id[len(prefix) :]
    return _is_positive_integer_text(suffix)


def _same_grade_course_sequence(
    year_learning_paths: dict | None,
    selected_course: dict,
    latest_grade_year: str = "",
) -> list[dict]:
    selected_course_id = _clean_text(selected_course.get("course_node_id"))
    selected_grade_year = _clean_text(selected_course.get("grade_id"))
    for path in iter_year_learning_paths(year_learning_paths, latest_grade_year):
        if not isinstance(path, dict):
            continue
        grade_plans = path.get("grade_plans")
        if not isinstance(grade_plans, dict):
            continue
        grade_plan = grade_plans.get(selected_grade_year)
        if not isinstance(grade_plan, dict):
            continue
        course_nodes = grade_plan.get("course_nodes")
        if not isinstance(course_nodes, list):
            continue
        sequence: list[dict] = []
        for index, course in enumerate(course_nodes, start=1):
            if not isinstance(course, dict):
                continue
            course_id = _clean_text(course.get("course_node_id"))
            course_name = _clean_text(course.get("course_or_chapter_theme"))
            if not course_id or not course_name:
                continue
            sequence.append(
                {
                    "order": index,
                    "course_id": course_id,
                    "course_name": course_name,
                    "is_current": course_id == selected_course_id,
                }
            )
        if sequence:
            return sequence
    return []


def _select_grade_courses_for_outlines(
    year_learning_paths: dict | None,
    latest_grade_year: str = "",
) -> tuple[str, list[dict], str]:
    if not year_learning_paths:
        raise ValueError("学习路径不存在，无法生成课程章节。")

    for path in iter_year_learning_paths(year_learning_paths, latest_grade_year):
        if not isinstance(path, dict):
            continue
        grade_plans = path.get("grade_plans")
        if not isinstance(grade_plans, dict):
            continue

        current = path.get("current_learning_course")
        current_course_id = ""
        current_grade_id = ""
        if isinstance(current, dict):
            current_course_id = _clean_text(current.get("course_node_id"))
            current_grade_id = _clean_text(current.get("grade_id"))

        grade_years: list[str] = []
        if latest_grade_year and latest_grade_year in grade_plans:
            grade_years.append(latest_grade_year)
        if (
            current_grade_id
            and current_grade_id in grade_plans
            and current_grade_id not in grade_years
        ):
            grade_years.append(current_grade_id)
        grade_years.extend(
            grade_year for grade_year in grade_plans if grade_year not in grade_years
        )

        for grade_year in grade_years:
            grade_plan = grade_plans.get(grade_year)
            if not isinstance(grade_plan, dict):
                continue
            course_nodes = grade_plan.get("course_nodes")
            if not isinstance(course_nodes, list):
                continue
            courses = [
                course
                for course in course_nodes
                if isinstance(course, dict)
                and _clean_text(course.get("course_node_id"))
                and _clean_text(course.get("course_or_chapter_theme"))
            ]
            if courses:
                return str(grade_year), courses, current_course_id

    raise ValueError("学习路径中的课程列表无法定位。")


def _normalize_generated_sections(raw_sections: object) -> list[dict]:
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("课程大纲缺少有效章节。")

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
        else:
            title = _strip_subsection_id_prefix(title, section_id)
        parent_section_id = payload.get("parent_section_id")
        if parent_section_id is not None:
            parent_section_id = _clean_text(parent_section_id) or None
        depth = payload.get("depth")
        if not isinstance(depth, int):
            depth = section_id.count(".") + 1
        order_index = payload.get("order_index")
        if not isinstance(order_index, int):
            order_index = index
        key_knowledge_points = _string_list(payload.get("key_knowledge_points"))
        if not key_knowledge_points:
            raise ValueError("课程大纲章节缺少 key_knowledge_points。")

        normalized_sections.append(
            {
                "section_id": section_id,
                "parent_section_id": parent_section_id,
                "depth": depth,
                "title": title,
                "order_index": order_index,
                "description": _clean_text(payload.get("description")),
                "key_knowledge_points": key_knowledge_points,
                "source_textbook_id": _clean_text(payload.get("source_textbook_id")),
                "source_textbook_title": _clean_text(
                    payload.get("source_textbook_title")
                ),
                "source_section_ids": _string_list(payload.get("source_section_ids")),
                "source_section_titles": _string_list(
                    payload.get("source_section_titles")
                ),
                "source_content_chars": payload.get("source_content_chars"),
            }
        )

    if not normalized_sections:
        raise ValueError("课程大纲缺少有效章节。")

    has_nested_sections = any(
        section.get("parent_section_id") is not None
        and int(section.get("depth", 1)) > 1
        for section in normalized_sections
        if isinstance(section, dict)
    )
    if not has_nested_sections:
        raise ValueError("课程大纲必须包含章内小节。")

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
        raise ValueError("每个一级章节必须包含章内小节。")

    top_level_children: dict[str, list[dict]] = {}
    for section in normalized_sections:
        if not isinstance(section, dict):
            continue
        parent_section_id = section.get("parent_section_id")
        if parent_section_id is None:
            continue
        top_level_children.setdefault(str(parent_section_id), []).append(section)

    for top_level_id in top_level_ids:
        if not _is_positive_integer_text(str(top_level_id)):
            raise ValueError("一级章节 section_id 必须使用 1、2 这种数字编号。")
        children = top_level_children.get(top_level_id, [])
        if len(children) < 3:
            raise ValueError("每个一级章节至少需要三个二级小节。")
        if not all(
            _is_direct_child_section_id(
                _clean_text(child.get("section_id")), str(top_level_id)
            )
            for child in children
        ):
            raise ValueError(
                "二级小节 section_id 必须使用 1.1、1.2、1.3 这种编号并归属对应一级章节。"
            )

    return [SectionItem(**section).model_dump() for section in normalized_sections]


def _normalize_generated_course_outline(
    selected_course: dict,
    raw_outline: object,
) -> dict:
    payload = (
        raw_outline
        if isinstance(raw_outline, dict)
        else _extract_json_payload(raw_outline)
    )

    course_id = _clean_text(selected_course.get("course_node_id"))
    course_name = _clean_text(selected_course.get("course_or_chapter_theme"))
    grade_year = _clean_text(selected_course.get("grade_id"))
    personalization_summary = (
        _clean_text(payload.get("personalization_summary"))
        or "课程大纲已根据当前学习画像与课程顺序生成。"
    )
    sections = _normalize_generated_sections(payload.get("sections"))
    sections = _apply_source_section_content_lengths(selected_course, sections)
    section_ids = [
        section["section_id"] for section in sections if isinstance(section, dict)
    ]
    learning_sequence = _string_list(payload.get("learning_sequence"))
    if learning_sequence and all(
        section_id in section_ids for section_id in learning_sequence
    ):
        learning_sequence = _learning_sequence_texts(sections, learning_sequence)
    elif learning_sequence:
        learning_sequence = [step for step in learning_sequence if step]
    else:
        preferred_sequence_ids = [
            section_id for section_id in section_ids if "." not in section_id
        ]
        learning_sequence = _learning_sequence_texts(sections, preferred_sequence_ids)
    total_estimated_hours = _normalize_total_estimated_hours(
        payload.get("total_estimated_hours"),
        "待评估",
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


def _source_section_contexts_for_courses(
    courses: list[dict],
) -> dict[str, list[dict[str, object]]]:
    contexts: dict[str, list[dict[str, object]]] = {}
    with Session(get_engine()) as db_session:
        for course in courses:
            course_id = _clean_text(course.get("course_node_id"))
            textbook_id = _clean_text(course.get("source_textbook_id"))
            section_ids = _string_list(course.get("source_outline_section_ids"))
            if not course_id or not textbook_id or not section_ids:
                continue
            contexts[course_id] = get_textbook_section_binding_context(
                db_session,
                textbook_id,
                section_ids,
            )
    return contexts


def _apply_source_section_content_lengths(
    selected_course: dict,
    sections: list[dict],
) -> list[dict]:
    textbook_id = _clean_text(selected_course.get("source_textbook_id"))
    textbook_title = _clean_text(selected_course.get("source_textbook_title"))
    allowed_section_ids = _string_list(
        selected_course.get("source_outline_section_ids")
    )
    if not textbook_id or not allowed_section_ids:
        return sections

    source_contexts = _source_section_contexts_for_courses([selected_course])
    course_id = _clean_text(selected_course.get("course_node_id"))
    source_rows = source_contexts.get(course_id, [])
    source_rows_by_id = {str(row["section_id"]): row for row in source_rows}
    allowed_set = set(allowed_section_ids)

    normalized_sections: list[dict] = []
    for section in sections:
        section_source_ids = _string_list(section.get("source_section_ids"))
        if not section_source_ids:
            raise ValueError("课程大纲章节缺少 source_section_ids。")
        if any(section_id not in allowed_set for section_id in section_source_ids):
            raise ValueError("课程大纲章节绑定了未授权教材小节。")
        source_section_rows = [
            source_rows_by_id[section_id] for section_id in section_source_ids
        ]
        _require_valid_source_section_group(source_section_rows)
        source_content_chars = sum(
            int(row["content_char_count"]) for row in source_section_rows
        )
        if source_content_chars > SOURCE_CONTENT_CHAR_LIMIT:
            raise ValueError(
                "source_content_chars 不能超过 8000，必须拆成多个学生端章节。"
            )

        normalized_section = {
            **section,
            "source_textbook_id": textbook_id,
            "source_textbook_title": textbook_title
            or _clean_text(section.get("source_textbook_title")),
            "source_section_ids": [
                str(row["section_id"]) for row in source_section_rows
            ],
            "source_section_titles": [str(row["title"]) for row in source_section_rows],
            "source_content_chars": source_content_chars,
        }
        normalized_sections.append(normalized_section)
    return normalized_sections


def _require_valid_source_section_group(source_rows: list[dict[str, object]]) -> None:
    if not source_rows:
        raise ValueError("课程大纲章节缺少有效教材小节。")
    if len(source_rows) > 7:
        raise ValueError("课程大纲章节最多绑定 7 个教材小节。")

    order_indexes = [int(row["order_index"]) for row in source_rows]
    if order_indexes != list(
        range(order_indexes[0], order_indexes[0] + len(source_rows))
    ):
        raise ValueError("课程大纲章节绑定的教材小节必须连续。")

    chapter_keys = {
        _source_section_chapter_key(
            str(row.get("section_id", "")),
            row.get("parent_section_id"),
        )
        for row in source_rows
    }
    if len(chapter_keys) > 1:
        raise ValueError("课程大纲章节不能跨原教材章。")


def _source_section_chapter_key(section_id: str, parent_section_id: object) -> str:
    parent = _clean_text(parent_section_id)
    if parent:
        return parent.split(".", 1)[0]
    return section_id.split(".", 1)[0]


def _normalize_generated_year_course_outlines(
    courses: list[dict],
    raw_output: object,
) -> list[dict]:
    payload = (
        raw_output
        if isinstance(raw_output, dict)
        else _extract_json_payload(raw_output)
    )

    raw_outlines = payload.get("course_outlines")
    if not isinstance(raw_outlines, list) or not raw_outlines:
        raise ValueError("全年课程大纲缺少 course_outlines。")

    expected_courses = {
        _clean_text(course.get("course_node_id")): course
        for course in courses
        if isinstance(course, dict) and _clean_text(course.get("course_node_id"))
    }
    raw_outline_map: dict[str, object] = {}
    for raw_outline in raw_outlines:
        if hasattr(raw_outline, "model_dump"):
            raw_payload = raw_outline.model_dump()
        elif isinstance(raw_outline, dict):
            raw_payload = raw_outline
        else:
            continue
        course_id = _clean_text(raw_payload.get("course_id"))
        if not course_id:
            raise ValueError("全年课程大纲存在缺少 course_id 的课程大纲。")
        if course_id not in expected_courses:
            raise ValueError("全年课程大纲包含学习路径之外的课程。")
        raw_outline_map[course_id] = raw_payload

    missing_course_ids = [
        course_id for course_id in expected_courses if course_id not in raw_outline_map
    ]
    if missing_course_ids:
        raise ValueError(f"全年课程大纲缺少课程：{', '.join(missing_course_ids)}")

    return [
        _normalize_generated_course_outline(
            course, raw_outline_map[_clean_text(course.get("course_node_id"))]
        )
        for course in courses
    ]


def _course_input_payload(
    course: dict,
    source_section_contexts: dict[str, list[dict[str, object]]] | None = None,
) -> dict:
    time_arrangement = course.get("time_arrangement", {})
    payload = {
        "course_id": _clean_text(course.get("course_node_id")),
        "course_name": _clean_text(course.get("course_or_chapter_theme")),
        "grade_year": _clean_text(course.get("grade_id")),
        "semester_scope": _clean_text(time_arrangement.get("semester_scope"))
        if isinstance(time_arrangement, dict)
        else "",
        "duration": _clean_text(time_arrangement.get("duration"))
        if isinstance(time_arrangement, dict)
        else "",
        "pace_reason": _clean_text(time_arrangement.get("pace_reason"))
        if isinstance(time_arrangement, dict)
        else "",
        "course_goal": _clean_text(course.get("course_goal")),
        "key_points": _string_list(course.get("key_points")),
        "difficult_points": _string_list(course.get("difficult_points")),
        "acceptance_criteria": _string_list(course.get("acceptance_criteria")),
        "source_textbook_id": _clean_text(course.get("source_textbook_id")),
        "source_textbook_title": _clean_text(course.get("source_textbook_title")),
        "source_outline_section_ids": _string_list(
            course.get("source_outline_section_ids")
        ),
    }
    course_id = payload["course_id"]
    if source_section_contexts is not None and course_id in source_section_contexts:
        payload["source_outline_sections"] = source_section_contexts[course_id]
    return payload


def _profile_input_payload(profile: dict) -> dict:
    confirmed_info = (
        profile.get("confirmed_info", {}) if isinstance(profile, dict) else {}
    )
    compact_profile = {
        "current_grade": _clean_text(confirmed_info.get("current_grade"))
        if isinstance(confirmed_info, dict)
        else "",
        "major": _clean_text(confirmed_info.get("major"))
        if isinstance(confirmed_info, dict)
        else "",
        "learning_stage": _clean_text(confirmed_info.get("learning_stage"))
        if isinstance(confirmed_info, dict)
        else "",
        "learning_method_preference": _clean_text(
            confirmed_info.get("learning_method_preference")
        )
        if isinstance(confirmed_info, dict)
        else "",
        "learning_pace_preference": _clean_text(
            confirmed_info.get("learning_pace_preference")
        )
        if isinstance(confirmed_info, dict)
        else "",
        "content_preference": _string_list(confirmed_info.get("content_preference"))
        if isinstance(confirmed_info, dict)
        else [],
        "knowledge_foundation": _clean_text(confirmed_info.get("knowledge_foundation"))
        if isinstance(confirmed_info, dict)
        else "",
        "weaknesses": _clean_text(confirmed_info.get("weaknesses"))
        if isinstance(confirmed_info, dict)
        else "",
        "short_term_goal": _clean_text(confirmed_info.get("short_term_goal"))
        if isinstance(confirmed_info, dict)
        else "",
        "weekly_available_time": _clean_text(
            confirmed_info.get("weekly_available_time")
        )
        if isinstance(confirmed_info, dict)
        else "",
        "constraints": _clean_text(confirmed_info.get("constraints"))
        if isinstance(confirmed_info, dict)
        else "",
    }
    summary_text = (
        _clean_text(profile.get("summary_text")) if isinstance(profile, dict) else ""
    )
    if summary_text:
        compact_profile["profile_summary"] = summary_text
    return compact_profile


def _build_analysis_input(
    selected_course: dict,
    profile: dict,
    year_learning_paths: dict | None,
    latest_grade_year: str = "",
    source_section_contexts: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    compact_course = _course_input_payload(selected_course, source_section_contexts)
    course_sequence = _same_grade_course_sequence(
        year_learning_paths,
        selected_course,
        latest_grade_year,
    )
    compact_profile = _profile_input_payload(profile)

    return (
        "请为以下课程生成详细的章节大纲。\n\n"
        "只使用下面与大纲规划直接相关的信息。当前课程名称必须与"
        "当前课程输入里的 course_name 完全一致。\n"
        "学习路径只提供同年级课程先后顺序，不提供章节；不要把课程顺序、"
        "阶段词或路径规划字段当作章节。\n"
        "输出前先完成以下分析：\n"
        "1. 判断这门课的主目标、当前用户基础与最容易卡住的难点。\n"
        "2. 判断这门课在同年级课程顺序里应该承接什么、为后续课程准备什么。\n"
        "3. 根据个人画像和课程顺序自行设计章节、1.1/1.2 这类小节"
        "和每个 section 的 key_knowledge_points。\n"
        "4. 再把分析结果映射成层级化章节大纲。\n"
        "5. sections[] 的 source_* 字段必须来自这些绑定教材小节，"
        "不能新增未绑定来源。\n\n"
        f"当前课程输入：{json.dumps(compact_course, ensure_ascii=False, indent=2)}\n"
        f"同年级课程顺序：{json.dumps(course_sequence, ensure_ascii=False, indent=2)}\n"
        f"学习者输入：{json.dumps(compact_profile, ensure_ascii=False, indent=2)}"
    )


def _build_year_analysis_input(
    grade_year: str,
    courses: list[dict],
    current_course_id: str,
    profile: dict,
    source_section_contexts: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    compact_courses = []
    for index, course in enumerate(courses, start=1):
        payload = _course_input_payload(course, source_section_contexts)
        payload["order"] = index
        payload["is_current"] = payload["course_id"] == current_course_id
        compact_courses.append(payload)

    return (
        "请一次性为当前年级的全部课程生成详细章节大纲。\n\n"
        "你必须利用全年课程顺序、课程之间的承接关系和学习者画像"
        "统一设计每门课的大纲。"
        "这不是逐门孤立生成；每门课的小节都要体现它承接前序课程、"
        "准备后续课程的位置。\n"
        "输出必须覆盖全年课程输入中的每一门课程，且 course_id 必须"
        "与输入完全一致；不要新增、删除或改名课程。\n"
        "每门课仍然只生成课程结构：章名、小节名、短结构说明和 "
        "key_knowledge_points。\n"
        "一级章节 section_id 必须使用 1、2 这种数字编号；每个一级章节"
        "必须至少包含 1.1、1.2 这种二级小节。\n"
        "不要把学习路径里的 learning_sequence、stage_titles 或课程顺序"
        "条目直接当作章节。\n\n"
        "sections[] 的 source_* 字段必须来自这些绑定教材小节，"
        "不能新增未绑定来源。\n\n"
        "输出 JSON 顶层只包含 grade_year、year_summary、course_outlines。\n"
        "course_outlines 是数组；每项必须包含 course_id、"
        "personalization_summary、sections、learning_sequence、"
        "total_estimated_hours。\n"
        "sections 是数组；每项必须包含 section_id、parent_section_id、"
        "depth、title、order_index、description、key_knowledge_points、"
        "source_textbook_id、source_textbook_title、source_section_ids、"
        "source_section_titles、source_content_chars。\n"
        "key_knowledge_points 必须是非空字符串数组。\n\n"
        f"当前年级：{grade_year}\n"
        "全年课程输入："
        f"{json.dumps(compact_courses, ensure_ascii=False, indent=2)}\n"
        "学习者输入："
        f"{json.dumps(_profile_input_payload(profile), ensure_ascii=False, indent=2)}"
    )


def _build_repair_input(original_input: str, error_message: str) -> str:
    return (
        f"{original_input}\n\n"
        "上一次输出没有通过课程大纲结构校验，请重新生成完整 JSON。\n"
        f"校验错误：{error_message}\n\n"
        "修复要求：\n"
        "1. 保持当前课程名称与当前课程输入里的 course_name 完全一致。\n"
        "2. 一级章节 section_id 必须使用 1、2 这种数字编号，对应第一章、第二章。\n"
        "3. 每个一级章节必须至少包含三个直属二级小节，编号必须使用 1.1、1.2、1.3、2.1、2.2、2.3 这种形式。\n"
        "4. 每个 section 的 key_knowledge_points 必须非空，且必须是该章或小节的具体知识点、小能力或验收点。\n"
        "5. 每个 section 必须包含 source_textbook_id、source_textbook_title、source_section_ids、source_section_titles、source_content_chars。\n"
        "6. 每个 section 的 source_* 字段必须来自这些绑定教材小节，不能新增未绑定来源。\n"
        "7. 不要使用学习路径里的 learning_sequence、stage_titles 或课程顺序条目作为章节。"
    )


async def _invoke_json_outline(
    chain: object,
    selected_course: dict,
    query: str,
) -> dict:
    result = await asyncio.wait_for(
        chain.ainvoke({"query": query}),
        timeout=SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS,
    )
    return _normalize_generated_course_outline(selected_course, result)


async def _invoke_json_year_outlines(
    chain: object,
    courses: list[dict],
    query: str,
) -> list[dict]:
    result = await asyncio.wait_for(
        chain.ainvoke({"query": query}),
        timeout=YEAR_COURSE_OUTLINE_TIMEOUT_SECONDS,
    )
    return _normalize_generated_year_course_outlines(courses, result)


def _append_json_output_contract(query: str, output_contract: str) -> str:
    return (
        f"{query}\n\n"
        "输出格式要求：必须只输出一个 JSON 对象，不要输出 Markdown 代码块、解释文字或额外前后缀。\n"
        "只按下面的普通 JSON 文本形状输出。\n"
        f"{output_contract}"
    )


_SINGLE_COURSE_JSON_CONTRACT = """\
单门课程 JSON 形状：
{
  "personalization_summary": "为什么这样安排这门课",
  "sections": [
    {
      "section_id": "1",
      "parent_section_id": null,
      "depth": 1,
      "title": "第一章：概念引入与直觉建立",
      "order_index": 1,
      "description": "这一章解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "1.1",
      "parent_section_id": "1",
      "depth": 2,
      "title": "1.1 生活中的类比分析",
      "order_index": 2,
      "description": "这一小节解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "1.2",
      "parent_section_id": "1",
      "depth": 2,
      "title": "1.2 核心定义与公式",
      "order_index": 3,
      "description": "这一小节解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "1.3",
      "parent_section_id": "1",
      "depth": 2,
      "title": "1.3 边界情况与分析",
      "order_index": 4,
      "description": "这一小节解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "2",
      "parent_section_id": null,
      "depth": 1,
      "title": "第二章：黄金法则应用",
      "order_index": 5,
      "description": "这一章解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "2.1",
      "parent_section_id": "2",
      "depth": 2,
      "title": "2.1 法则基本步骤",
      "order_index": 6,
      "description": "这一小节解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "2.2",
      "parent_section_id": "2",
      "depth": 2,
      "title": "2.2 实际场景应用",
      "order_index": 7,
      "description": "这一小节解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    },
    {
      "section_id": "2.3",
      "parent_section_id": "2",
      "depth": 2,
      "title": "2.3 综合实战演练",
      "order_index": 8,
      "description": "这一小节解决什么问题",
      "key_knowledge_points": ["具体知识点或能力点"],
      "source_textbook_id": "必须来自当前课程输入 source_textbook_id",
      "source_textbook_title": "必须来自当前课程输入 source_textbook_title",
      "source_section_ids": ["必须来自当前课程输入 source_outline_section_ids"],
      "source_section_titles": ["绑定教材小节标题"],
      "source_content_chars": 1200
    }
  ],
  "learning_sequence": ["第一章：面向用户的学习步骤", "第二章：面向用户的学习步骤"],
  "total_estimated_hours": "预计总学时"
}
"""


_YEAR_COURSES_JSON_CONTRACT = """\
全年课程 JSON 形状：
{
  "grade_year": "当前年级 ID",
  "year_summary": "全年课程大纲整体安排说明",
  "course_outlines": [
    {
      "course_id": "必须与输入课程 course_id 完全一致",
      "personalization_summary": "为什么这样安排这门课",
      "sections": [
        {
          "section_id": "1",
          "parent_section_id": null,
          "depth": 1,
          "title": "第一章章名",
          "order_index": 1,
          "description": "这一章解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "1.1",
          "parent_section_id": "1",
          "depth": 2,
          "title": "1.1 小节名",
          "order_index": 2,
          "description": "这一小节解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "1.2",
          "parent_section_id": "1",
          "depth": 2,
          "title": "1.2 小节名",
          "order_index": 3,
          "description": "这一小节解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "1.3",
          "parent_section_id": "1",
          "depth": 2,
          "title": "1.3 小节名",
          "order_index": 4,
          "description": "这一小节解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "2",
          "parent_section_id": null,
          "depth": 1,
          "title": "第二章章名",
          "order_index": 5,
          "description": "这一章解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "2.1",
          "parent_section_id": "2",
          "depth": 2,
          "title": "2.1 小节名",
          "order_index": 6,
          "description": "这一小节解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "2.2",
          "parent_section_id": "2",
          "depth": 2,
          "title": "2.2 小节名",
          "order_index": 7,
          "description": "这一小节解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        },
        {
          "section_id": "2.3",
          "parent_section_id": "2",
          "depth": 2,
          "title": "2.3 小节名",
          "order_index": 8,
          "description": "这一小节解决什么问题",
          "key_knowledge_points": ["具体知识点或能力点"],
          "source_textbook_id": "必须来自对应课程输入 source_textbook_id",
          "source_textbook_title": "必须来自对应课程输入 source_textbook_title",
          "source_section_ids": ["必须来自对应课程输入 source_outline_section_ids"],
          "source_section_titles": ["绑定教材小节标题"],
          "source_content_chars": 1200
        }
      ],
      "learning_sequence": ["第一章：面向用户的学习步骤", "第二章：面向用户的学习步骤"],
      "total_estimated_hours": "预计总学时"
    }
  ]
}
"""


def _current_outline_from_generated(
    outlines: list[dict],
    current_course_id: str,
) -> dict:
    if current_course_id:
        for outline in outlines:
            if (
                isinstance(outline, dict)
                and outline.get("course_id") == current_course_id
            ):
                return outline
    return outlines[0]


def _try_db_outline_translation(
    db_session: Session,
    course: dict,
    grade_year: str,
) -> dict | None:
    from sqlmodel import select

    from app.models import Textbook, TextbookSectionContent

    source_textbook_id = str(course.get("source_textbook_id") or "").strip()
    if not source_textbook_id or source_textbook_id == "None":
        theme = str(course.get("course_or_chapter_theme") or "").strip()
        if theme:
            normalized_theme = "".join(theme.lower().split())
            stmt = select(Textbook).where(
                Textbook.student_availability_status == "published"
            )
            all_tbs = db_session.exec(stmt).all()
            for tb in all_tbs:
                normalized_title = "".join(tb.title.lower().split())
                if normalized_title == normalized_theme:
                    course["source_textbook_id"] = tb.textbook_id
                    course["source_textbook_title"] = tb.title
                    source_textbook_id = tb.textbook_id
                    break

    if not source_textbook_id or source_textbook_id == "None":
        return None

    textbook = db_session.get(Textbook, source_textbook_id)
    if textbook is None or textbook.student_availability_status != "published":
        return None

    outline_data = textbook.outline
    if not outline_data or "chapters" not in outline_data:
        return None

    chapters = outline_data.get("chapters") or []
    translated_sections = []
    total_chars = 0

    for ch in chapters:
        ch_num = ch.get("chapter_number")
        ch_title = ch.get("title") or ""
        try:
            ch_order_index = int(ch_num)
        except (ValueError, TypeError):
            ch_order_index = 1

        ch_sec_id = str(ch_num)
        ch_sections = ch.get("sections") or []
        ch_source_ids = [
            str(s.get("section_id")).strip() for s in ch_sections if s.get("section_id")
        ]
        ch_source_titles = [
            str(s.get("title")).strip() for s in ch_sections if s.get("title")
        ]
        if not ch_source_ids:
            ch_source_ids = [ch_sec_id]
            ch_source_titles = [ch_title]

        chapter_item = {
            "section_id": ch_sec_id,
            "parent_section_id": None,
            "depth": 1,
            "title": ch_title,
            "order_index": ch_order_index,
            "description": f"{ch_title}说明。",
            "key_knowledge_points": [f"{ch_title}重点"],
            "source_textbook_id": textbook.textbook_id,
            "source_textbook_title": textbook.title,
            "source_section_ids": ch_source_ids,
            "source_section_titles": ch_source_titles,
            "source_content_chars": 0,
        }
        translated_sections.append(chapter_item)

        for idx, sec in enumerate(ch_sections):
            sec_id = str(sec.get("section_id")).strip()
            sec_title = str(sec.get("title")).strip()

            stmt = select(TextbookSectionContent).where(
                TextbookSectionContent.textbook_id == textbook.textbook_id,
                TextbookSectionContent.section_id == sec_id,
            )
            content_record = db_session.exec(stmt).first()
            content_zh = content_record.content_zh if content_record else ""
            content_chars = len(content_zh)
            total_chars += content_chars

            section_item = {
                "section_id": sec_id,
                "parent_section_id": ch_sec_id,
                "depth": 2,
                "title": sec_title,
                "order_index": idx + 1,
                "description": f"{sec_title}说明。",
                "key_knowledge_points": [f"{sec_title}知识点"],
                "source_textbook_id": textbook.textbook_id,
                "source_textbook_title": textbook.title,
                "source_section_ids": [sec_id],
                "source_section_titles": [sec_title],
                "source_content_chars": content_chars,
            }
            translated_sections.append(section_item)

    depth_2_sections = [s for s in translated_sections if s["depth"] == 2]
    if depth_2_sections:
        learning_sequence = [
            f"学习并掌握「{s['title']}」中的核心概念与工程实践。"
            for s in depth_2_sections
        ]
    else:
        learning_sequence = [
            f"阅读《{textbook.title}》相关章节。",
            "结合各小节的核心知识点进行练习与巩固。",
        ]

    estimated_hours = max(4, total_chars // 2000)
    output_dict = {
        "course_id": course.get("course_node_id") or "",
        "course_name": course.get("course_or_chapter_theme")
        or course.get("title")
        or "",
        "grade_year": course.get("grade_id") or grade_year or "",
        "personalization_summary": f"已基于教材《{textbook.title}》的真实大纲和正文结构生成课程详细大纲，无需 LLM 模型介入。",
        "sections": translated_sections,
        "learning_sequence": learning_sequence,
        "total_estimated_hours": f"{estimated_hours} 学时",
    }

    try:
        from app.orchestration.agents.models import CourseKnowledgeOutput

        outline_obj = CourseKnowledgeOutput(**output_dict)
        return outline_obj.model_dump()
    except Exception as e:
        logger.error("Direct translated outline validation failed: %s", e)
        return None


async def run_course_knowledge_agent(
    state: OrchestrationState, llm: BaseChatModel
) -> dict:
    """Generate detailed course outline, auto-resolving next course if not specified."""
    tool_args = extract_last_tool_call_args(state)
    course_id = _clean_text(tool_args.get("course_id", ""))
    latest_grade_year = str(state.get("latest_grade_year", "")).strip()

    profile = state.get("profile", {})
    year_learning_paths = state.get("year_learning_paths", {})
    if not is_complete_profile_data(profile):
        return {"error": "请先完成基础画像。"}
    if not year_learning_paths:
        return {"error": "请先生成学习路径。"}

    try:
        with Session(get_engine()) as db_session:
            selected_course = None
            if course_id != ALL_CURRENT_GRADE_COURSES_ID:
                selected_course = _select_course_for_outline(
                    state.get("year_learning_paths"),
                    course_id,
                    latest_grade_year,
                )
                source_textbook_id = str(
                    selected_course.get("source_textbook_id") or ""
                ).strip()
                if not source_textbook_id or source_textbook_id == "None":
                    theme = str(
                        selected_course.get("course_or_chapter_theme") or ""
                    ).strip()
                    if theme:
                        from sqlmodel import select

                        from app.models import Textbook

                        normalized_theme = "".join(theme.lower().split())
                        stmt = select(Textbook).where(
                            Textbook.student_availability_status == "published"
                        )
                        all_tbs = db_session.exec(stmt).all()
                        for tb in all_tbs:
                            normalized_title = "".join(tb.title.lower().split())
                            if normalized_title == normalized_theme:
                                selected_course["source_textbook_id"] = tb.textbook_id
                                selected_course["source_textbook_title"] = tb.title
                                break

                if (
                    selected_course.get("source_textbook_id")
                    and selected_course.get("source_textbook_id") != "None"
                ):
                    require_student_visible_textbooks(
                        db_session, selected_course.get("source_textbook_id", "")
                    )
            else:
                grade_year, grade_courses, current_course_id = (
                    _select_grade_courses_for_outlines(
                        year_learning_paths,
                        latest_grade_year,
                    )
                )
                for course in grade_courses:
                    source_textbook_id = str(
                        course.get("source_textbook_id") or ""
                    ).strip()
                    if not source_textbook_id or source_textbook_id == "None":
                        theme = str(course.get("course_or_chapter_theme") or "").strip()
                        if theme:
                            from sqlmodel import select

                            from app.models import Textbook

                            normalized_theme = "".join(theme.lower().split())
                            stmt = select(Textbook).where(
                                Textbook.student_availability_status == "published"
                            )
                            all_tbs = db_session.exec(stmt).all()
                            for tb in all_tbs:
                                normalized_title = "".join(tb.title.lower().split())
                                if normalized_title == normalized_theme:
                                    course["source_textbook_id"] = tb.textbook_id
                                    course["source_textbook_title"] = tb.title
                                    break

                    if (
                        course.get("source_textbook_id")
                        and course.get("source_textbook_id") != "None"
                    ):
                        require_student_visible_textbooks(
                            db_session, course.get("source_textbook_id", "")
                        )
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    generated_outlines: list[dict]
    if course_id != ALL_CURRENT_GRADE_COURSES_ID:
        try:
            assert selected_course is not None
        except ValueError as exc:
            return {"error": str(exc), "hard_error": True}

        with Session(get_engine()) as db_session:
            db_translated = _try_db_outline_translation(
                db_session, selected_course, latest_grade_year
            )

        if db_translated is not None:
            generated_outlines = [db_translated]
            current_outline = db_translated
        else:
            try:
                source_section_contexts = _source_section_contexts_for_courses(
                    [selected_course]
                )
            except ValueError as exc:
                return {"error": str(exc), "hard_error": True}

            input_text = _append_json_output_contract(
                _build_analysis_input(
                    selected_course,
                    profile,
                    year_learning_paths,
                    latest_grade_year,
                    source_section_contexts=source_section_contexts,
                ),
                _SINGLE_COURSE_JSON_CONTRACT,
            )

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT),
                    ("human", "{query}"),
                ]
            )
            chain = prompt | llm

            try:
                generated_outlines = [
                    await _invoke_json_outline(chain, selected_course, input_text)
                ]
            except asyncio.TimeoutError:
                logger.warning(
                    "CourseKnowledgeAgent JSON prompt output timed out after %.1fs",
                    SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS,
                )
                return {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}
            except Exception as exc:
                logger.warning(
                    "CourseKnowledgeAgent JSON prompt output failed, retrying once: %s",
                    exc,
                )
                repair_input = _build_repair_input(input_text, str(exc))
                try:
                    generated_outlines = [
                        await _invoke_json_outline(chain, selected_course, repair_input)
                    ]
                except asyncio.TimeoutError:
                    logger.warning(
                        "CourseKnowledgeAgent repair output timed out after %.1fs",
                        SINGLE_COURSE_OUTLINE_TIMEOUT_SECONDS,
                    )
                    return {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}
                except Exception as repair_exc:
                    logger.warning(
                        "CourseKnowledgeAgent repair output failed: %s", repair_exc
                    )
                    return {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}
            current_outline = generated_outlines[0]
    else:
        grade_year, grade_courses, current_course_id = (
            _select_grade_courses_for_outlines(
                year_learning_paths,
                latest_grade_year,
            )
        )

        db_translated_map = {}
        unmapped_courses = []
        with Session(get_engine()) as db_session:
            for course in grade_courses:
                db_translated = _try_db_outline_translation(
                    db_session, course, grade_year
                )
                if db_translated is not None:
                    db_translated_map[course["course_node_id"]] = db_translated
                else:
                    unmapped_courses.append(course)

        if unmapped_courses:
            try:
                source_section_contexts = _source_section_contexts_for_courses(
                    unmapped_courses
                )
            except ValueError as exc:
                return {"error": str(exc), "hard_error": True}

            input_text = _append_json_output_contract(
                _build_year_analysis_input(
                    grade_year,
                    unmapped_courses,
                    current_course_id,
                    profile,
                    source_section_contexts=source_section_contexts,
                ),
                _YEAR_COURSES_JSON_CONTRACT,
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT),
                    ("human", "{query}"),
                ]
            )
            chain = prompt | llm

            try:
                llm_generated = await _invoke_json_year_outlines(
                    chain, unmapped_courses, input_text
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "CourseKnowledgeAgent yearly JSON prompt output timed out after %.1fs",
                    YEAR_COURSE_OUTLINE_TIMEOUT_SECONDS,
                )
                return {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}
            except Exception as exc:
                logger.warning(
                    "CourseKnowledgeAgent yearly JSON prompt output failed, retrying once: %s",
                    exc,
                )
                repair_input = _build_repair_input(input_text, str(exc))
                try:
                    llm_generated = await _invoke_json_year_outlines(
                        chain, unmapped_courses, repair_input
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "CourseKnowledgeAgent yearly repair output timed out after %.1fs",
                        YEAR_COURSE_OUTLINE_TIMEOUT_SECONDS,
                    )
                    return {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}
                except Exception as repair_exc:
                    logger.warning(
                        "CourseKnowledgeAgent yearly repair output failed: %s",
                        repair_exc,
                    )
                    return {"error": COURSE_KNOWLEDGE_RETRY_ERROR, "hard_error": True}

            llm_generated_map = {out["course_id"]: out for out in llm_generated}
        else:
            llm_generated_map = {}

        generated_outlines = []
        for course in grade_courses:
            c_id = course["course_node_id"]
            if c_id in db_translated_map:
                generated_outlines.append(db_translated_map[c_id])
            else:
                generated_outlines.append(llm_generated_map[c_id])

        current_outline = _current_outline_from_generated(
            generated_outlines, current_course_id
        )

    from app.services.course_knowledge_service import (
        upsert_user_course_knowledge_outline,
    )

    try:
        with Session(get_engine()) as db_session:
            for outline_dict in generated_outlines:
                upsert_user_course_knowledge_outline(
                    db_session, state["user_id"], outline_dict
                )
        logger.info(
            "CourseKnowledgeOutline persisted for user %s, %d course(s)",
            state["user_id"],
            len(generated_outlines),
        )
    except Exception as exc:
        logger.error(
            "Failed to persist course_knowledge for user %s: %s", state["user_id"], exc
        )
        return {"error": "课程大纲保存失败，请稍后重试。", "hard_error": True}

    result = {"course_knowledge": current_outline}
    if len(generated_outlines) > 1:
        result["course_knowledges"] = generated_outlines
    return result


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
        if agent_result.get("course_knowledges") is not None:
            result["course_knowledges"] = agent_result["course_knowledges"]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return course_knowledge_node
