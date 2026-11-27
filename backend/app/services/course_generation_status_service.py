from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

# A crashed gateway must not leave a chapter locked forever.
LOCK_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class CourseGenerationStatus:
    user_uid: str
    course_node_id: str
    chapter_section_id: str
    message: str
    started_at: float = field(default_factory=time.monotonic)


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
        running = _RUNNING.get(key)
        if (
            running is not None
            and time.monotonic() - running.started_at < LOCK_TTL_SECONDS
        ):
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
