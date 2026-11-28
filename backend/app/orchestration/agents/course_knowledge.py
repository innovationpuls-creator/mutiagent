"""Course knowledge agent contracts and prompt assembly."""

# ruff: noqa: C901,E501

from __future__ import annotations

import json
import re

from app.orchestration.agents.models import (
    CourseKnowledgeOutput,
    SectionItem,
)
from app.services.learning_path_service import iter_year_learning_paths

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


def _looks_like_internal_source_id(value: str) -> bool:
    text = _clean_text(value)
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", text))


def _visible_text_values(section: dict) -> list[str]:
    values = [
        _clean_text(section.get("title")),
        _clean_text(section.get("description")),
    ]
    values.extend(_string_list(section.get("key_knowledge_points")))
    return [value for value in values if value]


def _contains_internal_source_id_in_visible_text(section: dict) -> bool:
    internal_ids = [
        source_id
        for source_id in _string_list(section.get("source_section_ids"))
        if _looks_like_internal_source_id(source_id)
    ]
    if not internal_ids:
        return False
    visible_text = "\n".join(_visible_text_values(section))
    return any(source_id in visible_text for source_id in internal_ids)


def _contains_source_title_in_visible_text(section: dict) -> bool:
    source_titles = [
        title
        for title in _string_list(section.get("source_section_titles"))
        if title and not _contains_chinese_text(title)
    ]
    if not source_titles:
        return False
    visible_text = "\n".join(_visible_text_values(section))
    return any(title in visible_text for title in source_titles)


def _require_student_facing_section_text(section: dict) -> None:
    if _contains_internal_source_id_in_visible_text(section):
        raise ValueError("课程大纲可见文案不能包含教材内部小节 ID。")
    if _contains_source_title_in_visible_text(section):
        raise ValueError("课程大纲可见文案不能直接暴露英文教材标题。")
    visible_values = _visible_text_values(section)
    if visible_values and not all(
        _contains_chinese_text(value) for value in visible_values
    ):
        raise ValueError("课程大纲学生端可见文案必须使用中文。")


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
    internal_match = re.match(r"^(sec_\d+)_", section_id)
    if internal_match:
        return internal_match.group(1)
    return section_id.split(".", 1)[0]


def _course_context_for_naming(course: dict) -> dict:
    time_arrangement = course.get("time_arrangement", {})
    return {
        "course_name": _clean_text(course.get("course_or_chapter_theme")),
        "course_goal": _clean_text(course.get("course_goal")),
        "key_points": _string_list(course.get("key_points")),
        "difficult_points": _string_list(course.get("difficult_points")),
        "acceptance_criteria": _string_list(course.get("acceptance_criteria")),
        "semester_scope": _clean_text(time_arrangement.get("semester_scope"))
        if isinstance(time_arrangement, dict)
        else "",
        "duration": _clean_text(time_arrangement.get("duration"))
        if isinstance(time_arrangement, dict)
        else "",
    }


def _source_rows_by_chapter(
    source_rows: list[dict[str, object]],
) -> list[list[dict[str, object]]]:
    groups: list[list[dict[str, object]]] = []
    group_keys: list[str] = []
    for row in source_rows:
        chapter_key = _source_section_chapter_key(
            str(row.get("section_id", "")),
            row.get("parent_section_id"),
        )
        if chapter_key in group_keys:
            groups[group_keys.index(chapter_key)].append(row)
        else:
            group_keys.append(chapter_key)
            groups.append([row])
    return groups


def _section_source_payload(
    selected_course: dict,
    source_rows: list[dict[str, object]],
) -> dict:
    return {
        "source_textbook_id": _clean_text(selected_course.get("source_textbook_id")),
        "source_textbook_title": _clean_text(
            selected_course.get("source_textbook_title")
        ),
        "source_section_ids": [str(row["section_id"]) for row in source_rows],
        "source_section_titles": [str(row["title"]) for row in source_rows],
        "source_content_chars": sum(
            int(row["content_char_count"]) for row in source_rows
        ),
    }


def _naming_payload_texts(
    raw_output: object, section_ids: list[str]
) -> tuple[str, dict]:
    payload = _extract_json_payload(raw_output)
    personalization_summary = _clean_text(payload.get("personalization_summary"))
    if not personalization_summary:
        raise ValueError("课程大纲命名缺少 personalization_summary。")
    if not _contains_chinese_text(personalization_summary):
        raise ValueError("课程大纲学生端可见文案必须使用中文。")

    section_texts = payload.get("section_texts")
    if not isinstance(section_texts, dict):
        raise ValueError("课程大纲命名缺少 section_texts。")

    normalized: dict[str, dict] = {}
    for section_id in section_ids:
        raw_text = section_texts.get(section_id)
        if not isinstance(raw_text, dict):
            raise ValueError("课程大纲命名缺少章节文案。")
        title = _clean_text(raw_text.get("title"))
        description = _clean_text(raw_text.get("description"))
        key_knowledge_points = _string_list(raw_text.get("key_knowledge_points"))
        if not title or not description or not key_knowledge_points:
            raise ValueError("课程大纲命名章节文案不完整。")
        normalized[section_id] = {
            "title": title,
            "description": description,
            "key_knowledge_points": key_knowledge_points,
        }
    return personalization_summary, normalized


def _apply_outline_naming(
    selected_course: dict,
    sections: list[dict],
    personalization_summary: str,
    section_texts: dict[str, dict],
) -> dict:
    named_sections: list[dict] = []
    for section in sections:
        section_id = str(section["section_id"])
        named_section = {
            **section,
            **section_texts[section_id],
        }
        _require_student_facing_section_text(named_section)
        named_sections.append(SectionItem(**named_section).model_dump())

    top_level_ids = [
        section["section_id"]
        for section in named_sections
        if section.get("parent_section_id") is None
    ]
    total_child_sections = sum(
        1 for section in named_sections if section.get("parent_section_id") is not None
    )
    outline = CourseKnowledgeOutput(
        course_id=_clean_text(selected_course.get("course_node_id")),
        course_name=_clean_text(selected_course.get("course_or_chapter_theme")),
        grade_year=_clean_text(selected_course.get("grade_id")),
        personalization_summary=personalization_summary,
        sections=named_sections,
        learning_sequence=_learning_sequence_texts(named_sections, top_level_ids),
        total_estimated_hours=f"{max(4, total_child_sections * 2)} 小时",
    )
    return outline.model_dump()


def _contains_chinese_text(value: object) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(value or ""))
