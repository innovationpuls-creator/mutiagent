from __future__ import annotations

import copy
from datetime import datetime, timezone
from collections.abc import Iterator

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    UserCourseKnowledgeOutline,
    UserProfile,
    UserYearLearningPath,
)
from app.services.resource_quality_service import get_quality_scores_for_user


YEAR_ORDER = ("year_1", "year_2", "year_3", "year_4")
YEAR_INDEX = {grade_year: index for index, grade_year in enumerate(YEAR_ORDER)}
MILESTONE_DEFINITIONS = {
    1: {"title": "萌芽期 - 画像建立完成", "desc": "完成 AI 多轮对话评估，生成专属树苗。"},
    2: {"title": "繁枝期 - 学习路径规划完成", "desc": "成功生成完整四学年路径树分支。"},
    3: {"title": "叶茂期 - 点亮第一门课程", "desc": "获取并确认首门课程大纲与详细知识树。"},
    4: {"title": "成林期 - 开启首次章节测验", "desc": "系统生成首套定制测验题，开启深度评估。"},
    5: {"title": "成森期 - 顺利通过首门测验", "desc": "成功通关首个章节测验，达成成森里程碑。"},
}
GROWTH_TREE_SEED_STAGE = 1
GROWTH_TREE_MAX_ADVANCED_STEPS = 5
GROWTH_TREE_MAX_STAGE = GROWTH_TREE_SEED_STAGE + GROWTH_TREE_MAX_ADVANCED_STEPS


def _normalize_current_learning_course_progress(course: dict) -> dict:
    normalized_course = dict(course)
    if normalized_course.get("progress_state") != "completed":
        normalized_course["progress_state"] = "in_progress"
    return normalized_course


def _normalize_current_learning_courses(path_data: dict) -> dict:
    normalized = dict(path_data)

    current_courses = normalized.get("current_learning_courses")
    if isinstance(current_courses, list):
        normalized_current_courses = [
            _normalize_current_learning_course_progress(course)
            for course in current_courses
            if isinstance(course, dict)
        ]
    else:
        normalized_current_courses = []

    current_course = normalized.get("current_learning_course")
    if not normalized_current_courses and isinstance(current_course, dict):
        normalized_current_courses = [_normalize_current_learning_course_progress(current_course)]

    if normalized_current_courses:
        normalized["current_learning_course"] = normalized_current_courses[0]
        normalized["current_learning_courses"] = normalized_current_courses

    return normalized


def _expanded_grade_years(row_grade_year: str, path_data: dict) -> list[str]:
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return [row_grade_year] if row_grade_year else []

    ordered_grade_years: list[str] = []
    if row_grade_year and row_grade_year in grade_plans:
        ordered_grade_years.append(row_grade_year)

    for grade_year in YEAR_ORDER:
        if grade_year in grade_plans and grade_year not in ordered_grade_years:
            ordered_grade_years.append(grade_year)

    for grade_year, grade_plan in grade_plans.items():
        if not isinstance(grade_plan, dict):
            continue
        if grade_year not in ordered_grade_years:
            ordered_grade_years.append(grade_year)

    if not ordered_grade_years and row_grade_year:
        ordered_grade_years.append(row_grade_year)
    return ordered_grade_years


def get_current_learning_course(path_data: dict) -> dict | None:
    normalized_path = _normalize_current_learning_courses(path_data)
    current_courses = normalized_path.get("current_learning_courses")
    current = (
        current_courses[0]
        if isinstance(current_courses, list) and current_courses and isinstance(current_courses[0], dict)
        else normalized_path.get("current_learning_course")
    )
    return current if isinstance(current, dict) else None


def get_current_grade_year_from_path(path_data: dict) -> str:
    current = get_current_learning_course(path_data)
    if current is None:
        return ""
    grade_id = current.get("grade_id")
    return grade_id.strip() if isinstance(grade_id, str) and grade_id.strip() else ""


def get_grade_plan(path_data: dict, grade_year: str) -> dict | None:
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return None
    grade_plan = grade_plans.get(grade_year)
    return grade_plan if isinstance(grade_plan, dict) else None


def get_grade_courses(path_data: dict, grade_year: str) -> list[dict]:
    grade_plan = get_grade_plan(path_data, grade_year)
    if grade_plan is None:
        return []
    course_nodes = grade_plan.get("course_nodes")
    if not isinstance(course_nodes, list):
        return []
    return [course for course in course_nodes if isinstance(course, dict)]


def compare_grade_years(left_grade_year: str, right_grade_year: str) -> int:
    left_index = YEAR_INDEX.get(left_grade_year)
    right_index = YEAR_INDEX.get(right_grade_year)
    if left_index is None or right_index is None:
        return 0
    if left_index < right_index:
        return -1
    if left_index > right_index:
        return 1
    return 0


def _course_index(courses: list[dict], course_id: str) -> int:
    return next(
        (
            index
            for index, course in enumerate(courses)
            if isinstance(course, dict) and course.get("course_node_id") == course_id
        ),
        -1,
    )


def get_year_progress_snapshot(path_data: dict, grade_year: str) -> dict[str, object]:
    courses = get_grade_courses(path_data, grade_year)
    total_courses = len(courses)
    snapshot: dict[str, object] = {
        "grade_year": grade_year,
        "total_courses": total_courses,
        "completed_courses": 0,
        "current_course_id": "",
        "current_progress_state": "",
        "next_course_id": "",
    }
    if total_courses == 0:
        return snapshot

    current = get_current_learning_course(path_data)
    current_grade_year = get_current_grade_year_from_path(path_data)
    if not current_grade_year:
        first_course_id = courses[0].get("course_node_id")
        snapshot["next_course_id"] = first_course_id if isinstance(first_course_id, str) else ""
        return snapshot

    grade_compare = compare_grade_years(grade_year, current_grade_year)
    if grade_compare < 0:
        snapshot["completed_courses"] = total_courses
        snapshot["current_progress_state"] = "completed"
        return snapshot
    if grade_compare > 0:
        first_course_id = courses[0].get("course_node_id")
        snapshot["next_course_id"] = first_course_id if isinstance(first_course_id, str) else ""
        return snapshot

    course_id = current.get("course_node_id") if isinstance(current, dict) else ""
    if not isinstance(course_id, str) or not course_id.strip():
        first_course_id = courses[0].get("course_node_id")
        snapshot["next_course_id"] = first_course_id if isinstance(first_course_id, str) else ""
        return snapshot

    normalized_course_id = course_id.strip()
    current_index = _course_index(courses, normalized_course_id)
    if current_index < 0:
        first_course_id = courses[0].get("course_node_id")
        snapshot["next_course_id"] = first_course_id if isinstance(first_course_id, str) else ""
        return snapshot

    progress_state = current.get("progress_state")
    normalized_progress_state = progress_state.strip() if isinstance(progress_state, str) and progress_state.strip() else ""
    completed_courses = current_index + 1 if normalized_progress_state == "completed" else current_index

    snapshot["completed_courses"] = min(completed_courses, total_courses)
    snapshot["current_course_id"] = normalized_course_id
    snapshot["current_progress_state"] = normalized_progress_state

    if normalized_progress_state == "completed":
        if current_index + 1 < total_courses:
            next_course_id = courses[current_index + 1].get("course_node_id")
            snapshot["next_course_id"] = next_course_id if isinstance(next_course_id, str) else ""
        return snapshot

    snapshot["next_course_id"] = normalized_course_id
    return snapshot


def get_learning_path_progress_snapshots(
    year_learning_paths: dict[str, dict] | None,
) -> list[dict[str, object]]:
    if not isinstance(year_learning_paths, dict):
        return []

    ordered_years = [grade_year for grade_year in YEAR_ORDER if grade_year in year_learning_paths]
    ordered_years.extend(
        grade_year for grade_year in year_learning_paths if grade_year not in ordered_years
    )

    snapshots: list[dict[str, object]] = []
    for grade_year in ordered_years:
        path = year_learning_paths.get(grade_year)
        if not isinstance(path, dict):
            continue
        snapshots.append(get_year_progress_snapshot(path, grade_year))
    return snapshots


def get_year_learning_path(session: Session, user_uid: str, grade_year: str) -> dict | None:
    row = session.get(UserYearLearningPath, (user_uid, grade_year))
    if row is None:
        stmt = (
            select(UserYearLearningPath)
            .where(UserYearLearningPath.user_uid == user_uid)
            .order_by(UserYearLearningPath.updated_at.desc(), UserYearLearningPath.grade_year.asc())
        )
        rows = session.exec(stmt).all()
        for candidate in rows:
            normalized = _normalize_current_learning_courses(candidate.path_data)
            if grade_year in _expanded_grade_years(candidate.grade_year, normalized):
                return copy.deepcopy(normalized)
        return None
    return _normalize_current_learning_courses(row.path_data)


def get_all_year_learning_paths(session: Session, user_uid: str) -> dict[str, dict]:
    stmt = (
        select(UserYearLearningPath)
        .where(UserYearLearningPath.user_uid == user_uid)
        .order_by(UserYearLearningPath.updated_at.desc(), UserYearLearningPath.grade_year.asc())
    )
    rows = session.exec(stmt).all()
    paths_by_year: dict[str, dict] = {}
    for row in rows:
        normalized = _normalize_current_learning_courses(row.path_data)
        for grade_year in _expanded_grade_years(row.grade_year, normalized):
            if grade_year in paths_by_year:
                continue
            paths_by_year[grade_year] = copy.deepcopy(normalized)
    return paths_by_year


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


def _date_text(value: datetime | None) -> str:
    return value.strftime("%Y.%m.%d") if value is not None else "--"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _canopy_course_status(
    rendered_grade_id: str,
    current_grade_id: str,
    current_index: int | None,
    index: int,
    current_progress_state: str,
) -> str:
    grade_compare = compare_grade_years(rendered_grade_id, current_grade_id)
    if grade_compare < 0:
        return "completed"
    if grade_compare > 0:
        return "locked"
    if current_index is None:
        return "locked"
    if index < current_index:
        return "completed"
    if index == current_index:
        if current_progress_state == "completed":
            return "completed"
        return "current"
    return "locked"


def _canopy_courses_from_paths(paths_by_year: dict[str, dict]) -> list[dict[str, object]]:
    courses: list[dict[str, object]] = []
    for grade_id in YEAR_ORDER:
        path_data = paths_by_year.get(grade_id, {})
        grade_courses = get_grade_courses(path_data, grade_id)
        current = get_current_learning_course(path_data)
        current_grade_id = get_current_grade_year_from_path(path_data)
        current_course_id = ""
        current_progress_state = ""
        if isinstance(current, dict):
            course_id = current.get("course_node_id")
            progress_state = current.get("progress_state")
            current_course_id = course_id.strip() if isinstance(course_id, str) and course_id.strip() else ""
            current_progress_state = (
                progress_state.strip()
                if isinstance(progress_state, str) and progress_state.strip()
                else ""
            )
        current_index = next(
            (
                index
                for index, course in enumerate(grade_courses)
                if course.get("course_node_id") == current_course_id
            ),
            None,
        )

        for index, course in enumerate(grade_courses):
            course_id = course.get("course_node_id")
            if not isinstance(course_id, str) or not course_id.strip():
                continue
            title = course.get("course_or_chapter_theme")
            description = course.get("course_goal")
            courses.append(
                {
                    "id": course_id.strip(),
                    "title": title.strip() if isinstance(title, str) and title.strip() else course_id.strip(),
                    "grade": grade_id,
                    "status": _canopy_course_status(
                        grade_id,
                        current_grade_id,
                        current_index,
                        index,
                        current_progress_state,
                    ),
                    "score": None,
                    "description": (
                        description.strip()
                        if isinstance(description, str) and description.strip()
                        else "继续沿着学习路径稳步推进。"
                    ),
                    "prerequisite_ids": _string_list(course.get("prerequisite_node_ids")),
                }
            )
    return courses


def _canopy_growth_stage(completed_chapters: int) -> int:
    advanced_steps = min(completed_chapters, GROWTH_TREE_MAX_ADVANCED_STEPS)
    return GROWTH_TREE_SEED_STAGE + advanced_steps


def _canopy_active_rate(growth_stage: int) -> int:
    advanced_steps = growth_stage - GROWTH_TREE_SEED_STAGE
    return round((advanced_steps / GROWTH_TREE_MAX_ADVANCED_STEPS) * 100)


def get_canopy_overview(session: Session, user_uid: str) -> dict[str, object]:
    profile = session.get(UserProfile, user_uid)
    path_rows = list(
        session.exec(
            select(UserYearLearningPath).where(UserYearLearningPath.user_uid == user_uid)
        ).all()
    )
    outline_rows = list(
        session.exec(
            select(UserCourseKnowledgeOutline).where(UserCourseKnowledgeOutline.user_uid == user_uid)
        ).all()
    )
    quiz_rows = list(
        session.exec(select(ChapterQuiz).where(ChapterQuiz.user_uid == user_uid)).all()
    )
    passed_chapters = list(
        session.exec(
            select(ChapterProgress).where(
                ChapterProgress.user_uid == user_uid,
                ChapterProgress.state == "passed",
            )
        ).all()
    )

    completed_count = len(passed_chapters)
    growth_stage = _canopy_growth_stage(completed_count)

    dates = [
        profile.created_at if profile is not None else None,
        min((row.created_at for row in path_rows), default=None),
        min((row.created_at for row in outline_rows), default=None),
        min((row.created_at for row in quiz_rows), default=None),
        min((row.passed_at for row in passed_chapters if row.passed_at), default=None),
    ]
    milestones = []
    for stage_num in range(1, 6):
        definition = MILESTONE_DEFINITIONS[stage_num]
        milestone_date = dates[stage_num - 1]
        reached = milestone_date is not None
        milestones.append(
            {
                "date": _date_text(milestone_date),
                "title": definition["title"],
                "desc": definition["desc"],
                "reached": reached,
            }
        )

    scores = [row.best_score for row in passed_chapters if row.best_score > 0]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    attempts_count = session.exec(
        select(func.count(ChapterQuizAttempt.attempt_id)).where(
            ChapterQuizAttempt.user_uid == user_uid
        )
    ).one()
    focused_hours = len(passed_chapters) * 3.5 + int(attempts_count or 0) * 0.5

    courses = _canopy_courses_from_paths(get_all_year_learning_paths(session, user_uid))
    active_rate = _canopy_active_rate(growth_stage)
    quality_scores = get_quality_scores_for_user(session, user_uid)

    return {
        "courses": courses,
        "growth_stage": growth_stage,
        "completed_count": completed_count,
        "active_rate": active_rate,
        "avg_score": avg_score,
        "focused_hours": focused_hours,
        "milestones": milestones,
        "quality_scores": quality_scores,
    }


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
        current = get_current_learning_course(path)
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
    current = get_current_learning_course(normalized_path)
    if not isinstance(current, dict):
        raise ValueError("学习路径缺少 current_learning_course。")
    grade_id = current.get("grade_id")
    course_id = current.get("course_node_id")
    grade_plan = get_grade_plan(normalized_path, str(grade_id))
    if grade_plan is None:
        raise ValueError("current_learning_course.grade_id 无法定位。")
    course_nodes = get_grade_courses(normalized_path, str(grade_id))
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
        "progress_state": "in_progress",
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
