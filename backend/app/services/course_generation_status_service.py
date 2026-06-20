from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class CourseGenerationStatus:
    user_uid: str
    course_node_id: str
    chapter_section_id: str
    message: str


_LOCK = Lock()
_RUNNING: dict[tuple[str, str, str], CourseGenerationStatus] = {}


def start_course_generation(
    user_uid: str, course_node_id: str, chapter_section_id: str
) -> CourseGenerationStatus:
    key = (user_uid, course_node_id, chapter_section_id)
    status = CourseGenerationStatus(
        user_uid=user_uid,
        course_node_id=course_node_id,
        chapter_section_id=chapter_section_id,
        message="AI 正在生成本章教学内容。",
    )
    with _LOCK:
        if key in _RUNNING:
            raise ValueError("这一章正在生成。")
        _RUNNING[key] = status
    return status


def finish_course_generation(
    user_uid: str, course_node_id: str, chapter_section_id: str
) -> None:
    key = (user_uid, course_node_id, chapter_section_id)
    with _LOCK:
        _RUNNING.pop(key, None)


def get_course_generation_status(
    user_uid: str, course_node_id: str
) -> CourseGenerationStatus | None:
    with _LOCK:
        for (
            running_user_uid,
            running_course_id,
            _chapter_id,
        ), status in _RUNNING.items():
            if running_user_uid == user_uid and running_course_id == course_node_id:
                return status
    return None
