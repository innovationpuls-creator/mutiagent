"""Chat context assembly and turn persistence for the TS orchestration gateway.

The gateway owns orchestration; Python stays the data core. These helpers back the
``/internal/chat/*`` and ``/internal/students/*`` endpoints.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlmodel import Session, select

from app.orchestration.grade_contract import is_complete_profile_data
from app.services.conversation_session_service import (
    append_messages,
    latest_learning_path_intake,
    load_session,
    update_session_state,
)

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    """Session missing or owned by someone else (indistinguishable on purpose)."""


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def history_for_gateway(raw_messages: list[Any]) -> list[dict[str, str]]:
    """Plain role/content history; structured legacy entries are not chat turns."""
    chat_dicts = [
        m
        for m in raw_messages or []
        if not (isinstance(m, dict) and m.get("type") == "learning_path_intake")
    ]
    history: list[dict[str, str]] = []
    for message in chat_dicts:
        kind = message.get("type") if isinstance(message, dict) else None
        if kind == "human":
            role = "user"
        elif kind == "ai":
            role = "assistant"
        else:
            continue
        data = message.get("data")
        text = _text_of(data.get("content") if isinstance(data, dict) else "")
        if text.strip():
            history.append({"role": role, "content": text})
    return history


_LEAF_REGEN_PENDING_PATTERN = re.compile(
    r"\[LEAF_REGEN_PENDING\](?P<body>.*?)\[/LEAF_REGEN_PENDING\]", re.DOTALL
)
_PENDING_KEYS = {"course_node_id", "chapter_section_id"}


def _parse_key_value_block(body: str, allowed_keys: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    key_pattern = "|".join(
        re.escape(key) for key in sorted(allowed_keys, key=len, reverse=True)
    )
    inline_pattern = re.compile(
        rf"(?P<key>{key_pattern})\s*:\s*(?P<value>.*?)(?=\s+(?:{key_pattern})\s*:|$)",
        re.DOTALL,
    )
    for match in inline_pattern.finditer(body.strip()):
        key = match.group("key").strip()
        value = match.group("value").strip()
        if key in allowed_keys and value:
            result[key] = value
    if result:
        return result
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() in allowed_keys:
            result[key.strip()] = value.strip()
    return result


def parse_leaf_regeneration_pending_marker(text: str) -> dict[str, str] | None:
    """Read the pre-migration `[LEAF_REGEN_PENDING]` marker out of an old AI reply."""
    match = _LEAF_REGEN_PENDING_PATTERN.search(text)
    if match is None:
        return None
    parsed = _parse_key_value_block(match.group("body"), _PENDING_KEYS)
    return parsed if _PENDING_KEYS.issubset(parsed) else None


def _latest_ai_text(raw_messages: list[Any]) -> str:
    chat_dicts = [
        m for m in raw_messages or [] if isinstance(m, dict) and m.get("type") == "ai"
    ]
    for message in reversed(chat_dicts):
        data = message.get("data")
        text = _text_of(data.get("content") if isinstance(data, dict) else "")
        if text.strip():
            return text.strip()
    return ""


def effective_session_state(session_state: dict | None, raw_messages: list) -> dict:
    """Explicit ``session_state`` first; legacy sessions are read through the old
    in-message conventions so both shapes restore without migration of old rows."""
    state: dict[str, Any] = dict(session_state or {})
    if "learning_path_intake" not in state:
        intake = latest_learning_path_intake(raw_messages or [])
        if intake:
            state["learning_path_intake"] = intake
    if "pending_leaf_regeneration" not in state:
        marker = parse_leaf_regeneration_pending_marker(_latest_ai_text(raw_messages))
        if marker is not None:
            state["pending_leaf_regeneration"] = marker
    return state


def inject_unconsumed_weaknesses(
    session: Session, user_uid: str, profile: dict | None, course_id: str
) -> dict | None:
    if not profile or not course_id:
        return profile
    from app.models import ChapterWeakness

    stmt = select(ChapterWeakness).where(
        ChapterWeakness.user_uid == user_uid,
        ChapterWeakness.course_node_id == course_id,
        ChapterWeakness.consumed.is_(False),
    )
    unconsumed = session.exec(stmt).all()
    kp_names = list(
        dict.fromkeys(
            w.knowledge_point_name for w in unconsumed if w.knowledge_point_name
        )
    )
    if not kp_names:
        return profile
    suffix = f"[Adaptive Weaknesses] Recently struggled with: {', '.join(kp_names)}"
    original = profile.get("weaknesses", "")
    profile["weaknesses"] = f"{original}\n{suffix}" if original else suffix
    return profile


def load_owned_session_row(session: Session, session_id: str, user_uid: str):
    row = load_session(session, session_id)
    if row is None or row.user_uid != user_uid:
        raise SessionNotFoundError(session_id)
    return row


def build_chat_context(session: Session, session_id: str, user_uid: str) -> dict:
    from app.services.course_knowledge_service import get_user_course_knowledge_outline
    from app.services.learning_path_service import (
        get_all_year_learning_paths,
        get_current_course_id_from_year_learning_paths,
        get_latest_grade_year,
    )
    from app.services.profile_service import get_user_profile

    row = load_owned_session_row(session, session_id, user_uid)
    raw_messages = list(row.messages or [])
    profile = get_user_profile(session, user_uid)
    year_paths = get_all_year_learning_paths(session, user_uid)
    latest_grade_year = get_latest_grade_year(session, user_uid)
    course_id = get_current_course_id_from_year_learning_paths(
        year_paths, latest_grade_year
    )
    course_knowledge = (
        get_user_course_knowledge_outline(session, user_uid, course_id)
        if course_id
        else None
    )
    profile = inject_unconsumed_weaknesses(session, user_uid, profile, course_id)
    return {
        "session_id": session_id,
        "user_uid": user_uid,
        "history": history_for_gateway(raw_messages),
        "session_state": effective_session_state(row.session_state, raw_messages),
        "profile": profile,
        "has_complete_profile": is_complete_profile_data(profile),
        "year_learning_paths": year_paths or None,
        "latest_grade_year": latest_grade_year or None,
        "course_knowledge": course_knowledge,
    }


def _stored_message(kind: str, content: str | list) -> dict:
    """One chat message in the stored row shape (kept readable by older rows)."""
    data: dict[str, Any] = {
        "content": content,
        "additional_kwargs": {},
        "response_metadata": {},
        "type": kind,
        "name": None,
        "id": None,
    }
    if kind == "ai":
        data.update(tool_calls=[], invalid_tool_calls=[], usage_metadata=None)
    return {"type": kind, "data": data}


def _user_message(text: str, image_attachment: str | None) -> dict:
    if image_attachment:
        return _stored_message(
            "human",
            [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_attachment}},
            ],
        )
    return _stored_message("human", text)


def persist_turn(
    session: Session,
    session_id: str,
    user_uid: str,
    *,
    user_message: str,
    image_attachment: str | None,
    assistant_message: str | None,
    session_state_patch: dict | None,
) -> dict:
    """Atomically append one turn. Full write first; on failure fall back to the
    user message alone so a refresh never loses what the student typed."""
    load_owned_session_row(session, session_id, user_uid)
    human = _user_message(user_message, image_attachment)
    new = [human]
    if assistant_message and assistant_message.strip():
        new.append(_stored_message("ai", assistant_message))
    try:
        append_messages(session, session_id, new)
        if session_state_patch:
            update_session_state(session, session_id, session_state_patch)
        return {"persisted": "full" if len(new) == 2 else "user_only"}
    except Exception:
        logger.exception(
            "conversation_turn_persistence_failed", extra={"session_id": session_id}
        )
        session.rollback()
        try:
            append_messages(session, session_id, [human])
        except Exception:
            logger.exception(
                "conversation_turn_user_fallback_persistence_failed",
                extra={"session_id": session_id},
            )
            raise
        return {"persisted": "user_only"}


def save_student_profile(session: Session, user_uid: str, profile_data: dict) -> dict:
    from app.services.course_knowledge_service import delete_user_course_outlines
    from app.services.profile_service import upsert_user_profile
    from app.services.student_lock import lock_student

    lock_student(session, user_uid)
    upsert_user_profile(session, user_uid, profile_data, commit=False)
    # Same invariant as the legacy persist: any profile rewrite invalidates outlines.
    if profile_data.get("type") in {"basic_profile", "collecting"}:
        delete_user_course_outlines(session, user_uid, commit=False)
    session.commit()
    return {"saved": True, "type": profile_data.get("type")}


def _grade_name_from_path(year: str, path: dict) -> str:
    grade_plans = path.get("grade_plans")
    if isinstance(grade_plans, dict):
        grade_plan = grade_plans.get(year)
        if isinstance(grade_plan, dict):
            grade_name = grade_plan.get("grade_name")
            if isinstance(grade_name, str) and grade_name.strip():
                return grade_name.strip()
    grade_name = path.get("grade_name")
    if isinstance(grade_name, str) and grade_name.strip():
        return grade_name.strip()
    return year


def _course_nodes_from_path(year: str, path: dict) -> list[dict]:
    from app.services.learning_path_service import get_grade_courses

    grade_plans = path.get("grade_plans")
    if isinstance(grade_plans, dict):
        return get_grade_courses(path, year)

    courses = path.get("courses")
    if isinstance(courses, list):
        return [course for course in courses if isinstance(course, dict)]
    return []


def _course_title(course: dict) -> str:
    for key in ("course_or_chapter_theme", "course_name", "title"):
        value = course.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    course_id = course.get("course_node_id") or course.get("course_id")
    return str(course_id).strip() if course_id else "未命名课程"


def _format_learning_path_text(
    year_paths: dict[str, dict], latest_grade_year: str = ""
) -> str:
    from app.services.learning_path_service import YEAR_ORDER

    lines = ["你的学习路径里已经有这些课程："]
    ordered_years = [year for year in YEAR_ORDER if year in year_paths]
    ordered_years.extend(year for year in year_paths if year not in ordered_years)
    for year in ordered_years:
        path = year_paths.get(year)
        if not isinstance(path, dict):
            continue
        grade_name = _grade_name_from_path(year, path)
        courses = _course_nodes_from_path(year, path)
        lines.append(f"{grade_name}（{year}）：{len(courses)} 门课")
        for index, course in enumerate(courses, start=1):
            title = _course_title(course)
            goal = course.get("course_goal")
            suffix = (
                f"：{goal.strip()}" if isinstance(goal, str) and goal.strip() else ""
            )
            lines.append(f"{index}. {title}{suffix}")

    from app.services.learning_path_service import (
        get_current_course_id_from_year_learning_paths,
    )

    current_course_id = get_current_course_id_from_year_learning_paths(
        year_paths, latest_grade_year
    )
    if current_course_id:
        lines.append(f"当前学习节点：{current_course_id}")
    return "\n".join(lines)


def _chapter_prefix(section_id: str) -> str:
    numbers = {
        "1": "第一章",
        "2": "第二章",
        "3": "第三章",
        "4": "第四章",
        "5": "第五章",
        "6": "第六章",
        "7": "第七章",
        "8": "第八章",
        "9": "第九章",
        "10": "第十章",
        "11": "第十一章",
        "12": "第十二章",
    }
    return numbers.get(section_id, f"第{section_id}章")


def _section_display_title(section: dict) -> str:
    title = section.get("title")
    section_id = section.get("section_id")
    if not isinstance(title, str) or not title.strip():
        return ""
    if not isinstance(section_id, str) or "." in section_id:
        if isinstance(section_id, str) and section_id.strip():
            sid = section_id.strip()
            t = title.strip()
            if t.startswith(f"{sid} ") or t.startswith(f"{sid}　") or t == sid:
                return t
            return f"{sid} {t}"
        return title.strip()
    if title.startswith("第"):
        return title.strip()
    return f"{_chapter_prefix(section_id)}：{title.strip()}"


def _format_course_outline_text(course_knowledge: dict) -> str:  # noqa: C901
    course_name = str(course_knowledge.get("course_name", "")).strip()
    grade_year = str(course_knowledge.get("grade_year", "")).strip()
    lines = [f"课程大纲 · {grade_year}".strip(), course_name]

    def append_personalization(summary: object) -> None:
        if isinstance(summary, str) and summary.strip():
            lines.extend(["", "个性化安排", summary.strip()])

    def append_learning_sequence(learning_sequence: object) -> None:
        if isinstance(learning_sequence, list) and learning_sequence:
            lines.extend(["", "推荐学习步骤"])
            lines.extend(
                str(item).strip() for item in learning_sequence if str(item).strip()
            )

    def append_sections(sections: object) -> None:
        if not isinstance(sections, list) or not sections:
            return
        lines.extend(["", "章节展开"])
        for section in sections:
            if not isinstance(section, dict):
                continue
            display_title = _section_display_title(section)
            if not display_title:
                continue
            description = section.get("description")
            if isinstance(description, str) and description.strip():
                lines.append(f"{display_title}：{description.strip()}")
            else:
                lines.append(display_title)
            key_points = section.get("key_knowledge_points")
            if isinstance(key_points, list):
                joined_points = "、".join(
                    str(item).strip() for item in key_points if str(item).strip()
                )
                if joined_points:
                    lines.append(f"核心知识点：{joined_points}")

    def append_generated_resource(label: str, resources: object) -> None:
        if isinstance(resources, dict) and resources:
            lines.extend(["", label])
            lines.extend(sorted(str(section_id) for section_id in resources.keys()))

    append_personalization(course_knowledge.get("personalization_summary"))
    append_learning_sequence(course_knowledge.get("learning_sequence"))
    append_sections(course_knowledge.get("sections"))
    append_generated_resource(
        "已生成教学文档", course_knowledge.get("section_markdowns")
    )
    append_generated_resource(
        "已生成视频资源", course_knowledge.get("section_video_links")
    )
    append_generated_resource(
        "已生成动画资源", course_knowledge.get("section_html_animations")
    )
    return "\n".join(line for line in lines if line is not None)


def _format_course_next_step_text(course_knowledge: dict) -> str:
    course_name = str(course_knowledge.get("course_name", "")).strip() or "当前课程"
    sections = course_knowledge.get("sections")
    first_section_title = ""
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            parent_section_id = section.get("parent_section_id")
            depth = section.get("depth")
            if parent_section_id is not None and depth != 1:
                continue
            first_section_title = _section_display_title(section)
            if first_section_title:
                break

    target = f"的{first_section_title}" if first_section_title else ""
    return "\n".join(
        [
            f"下一步：进入《{course_name}》{target}。",
            "先生成第一章教学内容，再按小节完成练习与检查点。",
            "直接发送：开始学习这门课",
        ]
    )


def _course_titles(path: dict, grade_year: str) -> dict[str, str]:
    return {
        str(
            course.get("course_node_id") or course.get("course_id") or ""
        ): _course_title(course)
        for course in _course_nodes_from_path(grade_year, path)
    }


def build_learning_overview(session: Session, user_uid: str) -> dict:
    from app.services.course_knowledge_service import get_user_course_knowledge_outline
    from app.services.learning_path_service import (
        get_all_year_learning_paths,
        get_current_course_id_from_year_learning_paths,
        get_latest_grade_year,
        get_learning_path_progress_snapshots,
    )

    year_paths = get_all_year_learning_paths(session, user_uid)
    latest_grade_year = get_latest_grade_year(session, user_uid)
    course_id = get_current_course_id_from_year_learning_paths(
        year_paths, latest_grade_year
    )
    course_knowledge = (
        get_user_course_knowledge_outline(session, user_uid, course_id)
        if course_id
        else None
    )
    progress = []
    for snapshot in get_learning_path_progress_snapshots(year_paths):
        grade_year = str(snapshot.get("grade_year", ""))
        titles = _course_titles(year_paths.get(grade_year, {}), grade_year)
        progress.append(
            {
                **snapshot,
                "current_course_title": titles.get(
                    str(snapshot.get("current_course_id", "")), ""
                ),
                "next_course_title": titles.get(
                    str(snapshot.get("next_course_id", "")), ""
                ),
            }
        )
    return {
        "has_paths": bool(year_paths),
        "has_outline": bool(course_knowledge),
        "latest_grade_year": latest_grade_year or None,
        "current_course_id": course_id or None,
        "progress": progress,
        "path_text": _format_learning_path_text(year_paths, latest_grade_year or "")
        if year_paths
        else "",
        "outline_text": _format_course_outline_text(course_knowledge)
        if course_knowledge
        else "",
        "next_step_text": _format_course_next_step_text(course_knowledge)
        if course_knowledge
        else "",
    }
