from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Iterator

from sqlmodel import Session, select

from app.models import UserYearLearningPath


def _normalize_current_learning_courses(path_data: dict) -> dict:
    normalized = dict(path_data)

    current_courses = normalized.get("current_learning_courses")
    if isinstance(current_courses, list):
        normalized_current_courses = [course for course in current_courses if isinstance(course, dict)]
    else:
        normalized_current_courses = []

    current_course = normalized.get("current_learning_course")
    if not normalized_current_courses and isinstance(current_course, dict):
        normalized_current_courses = [current_course]
    elif normalized_current_courses and (
        not isinstance(current_course, dict) or current_course != normalized_current_courses[0]
    ):
        normalized["current_learning_course"] = normalized_current_courses[0]

    if normalized_current_courses:
        normalized["current_learning_courses"] = normalized_current_courses

    return normalized


def get_year_learning_path(session: Session, user_uid: str, grade_year: str) -> dict | None:
    row = session.get(UserYearLearningPath, (user_uid, grade_year))
    if row is None:
        return None
    return _normalize_current_learning_courses(row.path_data)


def get_all_year_learning_paths(session: Session, user_uid: str) -> dict[str, dict]:
    stmt = (
        select(UserYearLearningPath)
        .where(UserYearLearningPath.user_uid == user_uid)
        .order_by(UserYearLearningPath.updated_at.desc(), UserYearLearningPath.grade_year.asc())
    )
    rows = session.exec(stmt).all()
    return {
        row.grade_year: _normalize_current_learning_courses(row.path_data)
        for row in rows
    }


def get_latest_year_learning_path_row(session: Session, user_uid: str) -> UserYearLearningPath | None:
    stmt = (
        select(UserYearLearningPath)
        .where(UserYearLearningPath.user_uid == user_uid)
        .order_by(UserYearLearningPath.updated_at.desc(), UserYearLearningPath.grade_year.asc())
    )
    return session.exec(stmt).first()


def get_latest_grade_year(session: Session, user_uid: str) -> str:
    latest = get_latest_year_learning_path_row(session, user_uid)
    if latest is None:
        return ""
    return latest.grade_year


def iter_year_learning_paths(
    year_learning_paths: dict[str, dict] | None,
    preferred_grade_year: str = "",
) -> Iterator[dict]:
    if not isinstance(year_learning_paths, dict):
        return

    preferred_path = year_learning_paths.get(preferred_grade_year)
    if isinstance(preferred_path, dict):
        yield preferred_path

    for grade_year, path in year_learning_paths.items():
        if not isinstance(path, dict):
            continue
        if grade_year == preferred_grade_year and path is preferred_path:
            continue
        yield path


def get_preferred_year_learning_path(
    year_learning_paths: dict[str, dict] | None,
    preferred_grade_year: str = "",
) -> dict | None:
    for path in iter_year_learning_paths(year_learning_paths, preferred_grade_year):
        return path
    return None


def get_current_course_id_from_year_learning_paths(
    year_learning_paths: dict[str, dict] | None,
    preferred_grade_year: str = "",
) -> str:
    for path in iter_year_learning_paths(year_learning_paths, preferred_grade_year):
        current_courses = path.get("current_learning_courses")
        current = current_courses[0] if isinstance(current_courses, list) and current_courses and isinstance(current_courses[0], dict) else path.get("current_learning_course")
        if not isinstance(current, dict):
            continue
        course_id = current.get("course_node_id")
        if isinstance(course_id, str) and course_id.strip():
            return course_id.strip()
    return ""


def upsert_year_learning_path(
    session: Session,
    user_uid: str,
    grade_year: str,
    learning_topic: str,
    path_data: dict,
) -> UserYearLearningPath:
    now = datetime.now(timezone.utc)
    row = session.get(UserYearLearningPath, (user_uid, grade_year))
    if row is None:
        row = UserYearLearningPath(
            user_uid=user_uid,
            grade_year=grade_year,
            learning_topic=learning_topic,
            path_data=path_data,
            created_at=now,
            updated_at=now,
        )
    else:
        row.learning_topic = learning_topic
        row.path_data = path_data
        row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def find_current_course(path_data: dict) -> dict:
    normalized_path = _normalize_current_learning_courses(path_data)
    current_courses = normalized_path.get("current_learning_courses")
    current = current_courses[0] if isinstance(current_courses, list) and current_courses and isinstance(current_courses[0], dict) else normalized_path.get("current_learning_course")
    if not isinstance(current, dict):
        raise ValueError("学习路径缺少 current_learning_course。")
    grade_id = current.get("grade_id")
    course_id = current.get("course_node_id")
    grade_plans = normalized_path.get("grade_plans")
    if not isinstance(grade_plans, dict):
        raise ValueError("current_learning_course.grade_id 无法定位。")
    grade_plan = grade_plans.get(grade_id)
    if not isinstance(grade_plan, dict):
        raise ValueError("current_learning_course.grade_id 无法定位。")
    course_nodes = grade_plan.get("course_nodes")
    if not isinstance(course_nodes, list):
        raise ValueError("current_learning_course.course_node_id 无法定位。")
    for node in course_nodes:
        if isinstance(node, dict) and node.get("course_node_id") == course_id:
            return node
    raise ValueError("current_learning_course.course_node_id 无法定位。")


def _course_to_current(course: dict) -> dict:
    return {
        "grade_id": course["grade_id"],
        "course_node_id": course["course_node_id"],
        "course_or_chapter_theme": course["course_or_chapter_theme"],
        "course_goal": course["course_goal"],
        "time_arrangement": course["time_arrangement"],
        "current_focus": f"正在学习 {course['course_or_chapter_theme']}",
        "progress_state": "not_started",
        "next_action": "开始本课程第一项学习任务",
    }


def advance_current_learning_course(
    session: Session,
    user_uid: str,
    grade_year: str,
    score: int,
) -> dict:
    path_data = get_year_learning_path(session, user_uid, grade_year)
    if path_data is None:
        raise ValueError("学习路径不存在。")
    current = path_data.get("current_learning_course")
    if not isinstance(current, dict):
        raise ValueError("学习路径缺少 current_learning_course。")
    grade_id = current.get("grade_id")
    course_id = current.get("course_node_id")
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        raise ValueError("current_learning_course.grade_id 无法定位。")
    grade_plan = grade_plans.get(grade_id)
    if not isinstance(grade_plan, dict):
        raise ValueError("current_learning_course.grade_id 无法定位。")
    courses = grade_plan.get("course_nodes")
    if not isinstance(courses, list):
        raise ValueError("current_learning_course.course_node_id 无法定位。")
    index = next(
        (
            i
            for i, course in enumerate(courses)
            if isinstance(course, dict) and course.get("course_node_id") == course_id
        ),
        -1,
    )
    if index < 0:
        raise ValueError("current_learning_course.course_node_id 无法定位。")
    if score > 70 and index + 1 < len(courses):
        next_course = courses[index + 1]
        if not isinstance(next_course, dict):
            raise ValueError("current_learning_course.course_node_id 无法定位。")
        next_current_course = _course_to_current(next_course)
        path_data["current_learning_course"] = next_current_course
        path_data["current_learning_courses"] = [next_current_course]
    elif score > 70:
        current["progress_state"] = "completed"
        current["next_action"] = "当前年级课程已完成"
        path_data["current_learning_course"] = current
        path_data["current_learning_courses"] = [current]
    else:
        path_data = _normalize_current_learning_courses(path_data)
    upsert_year_learning_path(session, user_uid, grade_year, "", path_data)
    return _normalize_current_learning_courses(path_data)
