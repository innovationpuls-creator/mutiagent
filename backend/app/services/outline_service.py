"""Internal helpers for the TS gateway's course-outline agent (M6).

The model only names sections in Chinese. Everything that must be exact stays here:
reading bound textbook sections, the deterministic skeleton (including automatic
splitting of sections longer than 8000 characters), the student-facing text
compliance check, and the fingerprinted, atomic save.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re

from sqlmodel import Session, select

from app.models import TextbookSectionContent
from app.orchestration.agents import course_knowledge as legacy
from app.services.knowledge_base_service import (
    _section_available_content,
    get_textbook_section_binding_context,
    require_student_visible_textbooks,
)
from app.services.learning_path_service import (
    _course_identity,
    get_all_year_learning_paths,
    get_grade_courses,
    get_latest_grade_year,
    get_year_learning_path,
)

ALL_CURRENT_GRADE = legacy.ALL_CURRENT_GRADE_COURSES_ID
SOURCE_CHAR_LIMIT = legacy.SOURCE_CONTENT_CHAR_LIMIT
CHUNK_TARGET_MIN = 4000
CHUNK_TARGET_MAX = 7000
_INTERNAL_ID = re.compile(r"\bsec_\d+(?:_\d+)*\b", re.IGNORECASE)
_PARAGRAPH_END = re.compile(r"\n[ \t]*\n+")
_SENTENCE_END = re.compile(r"[。！？!?；;]+[ \t]*\n?|\n")


class OutlineSourceError(ValueError):
    """The request cannot be served; the message is safe to show the student."""


class PathChangedError(Exception):
    """The learning path changed while an outline was being generated."""


def split_text_ranges(
    text: str,
    limit: int = SOURCE_CHAR_LIMIT,
    low: int = CHUNK_TARGET_MIN,
    high: int = CHUNK_TARGET_MAX,
) -> list[tuple[int, int]]:
    """Split [0, len(text)) into contiguous ranges, each <= limit.

    Cuts prefer paragraph ends, then sentence ends, aiming at equal parts of about
    `low`-`high` characters; a hard cut at `limit` is the last resort.
    """
    total = len(text)
    if total <= limit:
        return [(0, total)]
    parts = max(2, math.ceil(total / high))
    paragraph_cuts = [m.end() for m in _PARAGRAPH_END.finditer(text)]
    sentence_cuts = [m.end() for m in _SENTENCE_END.finditer(text)]

    ranges: list[tuple[int, int]] = []
    start = 0
    for remaining in range(parts, 1, -1):
        ideal = start + (total - start) / remaining
        window_lo = max(start + 1, start + min(low, (total - start) // remaining))
        window_hi = min(start + limit, total - 1)
        cut = None
        for candidates in (paragraph_cuts, sentence_cuts):
            usable = [c for c in candidates if window_lo <= c <= window_hi]
            if usable:
                cut = min(usable, key=lambda c: abs(c - ideal))
                break
        if cut is None:
            cut = min(start + limit, total - 1)
        ranges.append((start, cut))
        start = cut
    ranges.append((start, total))
    # A late hard cut can leave an oversized tail: split it again.
    final: list[tuple[int, int]] = []
    for lo, hi in ranges:
        if hi - lo > limit:
            final.extend(
                (lo + a, lo + b)
                for a, b in split_text_ranges(text[lo:hi], limit, low, high)
            )
        else:
            final.append((lo, hi))
    return final


def path_fingerprint(path_data: dict | None, grade_year: str) -> str:
    """Course identity of one grade; mirrors what makes an outline stale."""
    identities = [
        list(_course_identity(course))
        for course in get_grade_courses(path_data or {}, grade_year)
    ]
    return hashlib.sha256(
        json.dumps(identities, ensure_ascii=False).encode()
    ).hexdigest()


def _content_by_section(
    session: Session, textbook_id: str, section_ids: list[str]
) -> dict[str, str]:
    rows = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == textbook_id,
            TextbookSectionContent.section_id.in_(section_ids),
        )
    ).all()
    return {row.section_id: _section_available_content(row) for row in rows}


def _unavailable(course: dict) -> OutlineSourceError:
    name = legacy._clean_text(course.get("course_or_chapter_theme")) or "该课程"
    return OutlineSourceError(
        f"《{name}》绑定的教材当前不可用（已下架或未发布），暂时无法生成课程大纲。"
    )


def build_skeleton(
    course: dict,
    source_rows: list[dict[str, object]],
    contents: dict[str, str],
) -> list[dict]:
    """Deterministic outline skeleton; long source sections become several sections."""
    if not source_rows:
        raise OutlineSourceError("课程缺少可用于生成大纲的教材小节。")
    sections: list[dict] = []
    order_index = 1
    for chapter_index, chapter_rows in enumerate(
        legacy._source_rows_by_chapter(source_rows), start=1
    ):
        chapter_id = str(chapter_index)
        sections.append(
            {
                "section_id": chapter_id,
                "parent_section_id": None,
                "depth": 1,
                "title": "",
                "order_index": order_index,
                "description": "",
                "key_knowledge_points": ["待命名"],
                **legacy._section_source_payload(course, chapter_rows),
            }
        )
        order_index += 1
        children = [
            row
            for row in chapter_rows
            if not (
                len(chapter_rows) > 1
                and str(row.get("section_id", ""))
                == legacy._source_section_chapter_key(
                    str(row.get("section_id", "")), row.get("parent_section_id")
                )
            )
        ] or chapter_rows
        child_index = 0
        for row in children:
            legacy._require_valid_source_section_group([row])
            chars = int(row["content_char_count"])
            ranges = (
                split_text_ranges(contents.get(str(row["section_id"]), ""))
                if chars > SOURCE_CHAR_LIMIT
                else [None]
            )
            for chunk_no, span in enumerate(ranges, start=1):
                child_index += 1
                payload = legacy._section_source_payload(course, [row])
                chunk: dict[str, object] = {
                    "source_chunk_index": None,
                    "source_chunk_total": None,
                    "source_char_range": None,
                }
                if span is not None:
                    payload["source_content_chars"] = span[1] - span[0]
                    chunk = {
                        "source_chunk_index": chunk_no,
                        "source_chunk_total": len(ranges),
                        "source_char_range": [span[0], span[1]],
                    }
                sections.append(
                    {
                        "section_id": f"{chapter_id}.{child_index}",
                        "parent_section_id": chapter_id,
                        "depth": 2,
                        "title": "",
                        "order_index": order_index,
                        "description": "",
                        "key_knowledge_points": ["待命名"],
                        **payload,
                        **chunk,
                    }
                )
                order_index += 1
    return sections


def _select_courses(
    year_paths: dict, course_ref: str, latest_grade_year: str
) -> tuple[str, list[dict], str]:
    """(grade_year, courses, current_course_id) for the request."""
    ref = course_ref.strip()
    if ref == ALL_CURRENT_GRADE:
        return legacy._select_grade_courses_for_outlines(year_paths, latest_grade_year)
    course = legacy._select_course_for_outline(year_paths, ref, latest_grade_year)
    grade_year = legacy._clean_text(course.get("grade_id")) or latest_grade_year
    current = ""
    for path in year_paths.values():
        node = path.get("current_learning_course") if isinstance(path, dict) else None
        if isinstance(node, dict):
            current = legacy._clean_text(node.get("course_node_id"))
            break
    return grade_year, [course], current


def source_context(session: Session, user_uid: str, course_ref: str) -> dict:
    year_paths = get_all_year_learning_paths(session, user_uid)
    if not year_paths:
        raise OutlineSourceError("请先生成学习路径。")
    latest = get_latest_grade_year(session, user_uid)
    try:
        grade_year, picked, current_course_id = _select_courses(
            year_paths, course_ref, latest
        )
    except ValueError as exc:
        raise OutlineSourceError(str(exc)) from None

    courses_out: list[dict] = []
    for original in picked:
        course = copy.deepcopy(original)
        legacy._fill_course_source_binding_from_textbook(session, course)
        textbook_id = legacy._clean_text(course.get("source_textbook_id"))
        section_ids = legacy._string_list(course.get("source_outline_section_ids"))
        if not textbook_id or not section_ids:
            raise OutlineSourceError("课程缺少已发布教材绑定。")
        try:
            require_student_visible_textbooks(session, textbook_id)
        except ValueError:
            raise _unavailable(course) from None
        try:
            rows = get_textbook_section_binding_context(
                session, textbook_id, section_ids
            )
        except ValueError as exc:
            raise OutlineSourceError(str(exc)) from None
        contents = _content_by_section(session, textbook_id, section_ids)
        sections = build_skeleton(course, rows, contents)
        courses_out.append(
            {
                "course_node_id": legacy._clean_text(course.get("course_node_id")),
                "course_name": legacy._clean_text(
                    course.get("course_or_chapter_theme")
                ),
                "grade_year": legacy._clean_text(course.get("grade_id")) or grade_year,
                "source_textbook_id": textbook_id,
                "source_textbook_title": legacy._clean_text(
                    course.get("source_textbook_title")
                ),
                "naming_context": legacy._course_context_for_naming(course),
                "skeleton": sections,
            }
        )
    return {
        "grade_year": grade_year,
        "current_course_id": current_course_id,
        "path_fingerprints": {
            grade_year: path_fingerprint(year_paths.get(grade_year), grade_year)
        },
        "courses": courses_out,
    }


def compose_outline(skeleton_course: dict, naming: dict) -> dict:
    """Validate the Chinese naming against the skeleton, then build the outline."""
    sections = skeleton_course["skeleton"]
    section_ids = [section["section_id"] for section in sections]
    summary, texts = legacy._naming_payload_texts(naming, section_ids)
    for section_id, text in texts.items():
        visible = "\n".join(
            [text["title"], text["description"], *text["key_knowledge_points"]]
        )
        if _INTERNAL_ID.search(visible):
            raise ValueError(
                f"章节 {section_id} 的可见文案包含教材内部编号（如 sec_1_1），"
                "请改成自然的中文教学表达。"
            )
    selected = {
        "course_node_id": skeleton_course["course_node_id"],
        "course_or_chapter_theme": skeleton_course["course_name"],
        "grade_id": skeleton_course["grade_year"],
    }
    try:
        return legacy._apply_outline_naming(selected, sections, summary, texts)
    except ValueError:
        raise
    except Exception as exc:  # pydantic validation of SectionItem
        raise ValueError(f"大纲结构校验失败：{exc}") from None


def save_outlines(
    session: Session,
    user_uid: str,
    path_fingerprints: dict[str, str],
    outlines: list[dict],
) -> list[str]:
    """Atomic save; refuses outlines made against a path that has since changed."""
    from app.services.course_knowledge_service import (
        upsert_user_course_knowledge_outline,
    )
    from app.services.leaf_service import read_leaf_course
    from app.services.student_lock import lock_student

    try:
        lock_student(session, user_uid)
        for outline in outlines:
            grade_year = str(outline.get("grade_year", ""))
            expected = path_fingerprints.get(grade_year)
            current = path_fingerprint(
                get_year_learning_path(session, user_uid, grade_year), grade_year
            )
            if expected is None or expected != current:
                raise PathChangedError("学习路径已更新，请重新生成课程大纲。")
            read_leaf_course(session, user_uid, str(outline.get("course_id", "")))
            upsert_user_course_knowledge_outline(
                session, user_uid, outline, commit=False
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return [str(outline.get("course_id", "")) for outline in outlines]
