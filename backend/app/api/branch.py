from __future__ import annotations

from collections.abc import Callable, Generator

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.security import create_get_current_user
from app.models import User, UserCourseKnowledgeOutline
from app.schemas import BranchCourseNodeRead, BranchOverviewReadResponse, BranchYearRead
from app.services.learning_path_service import (
    get_all_year_learning_paths,
    get_latest_year_learning_path_row,
)

SessionDependency = Callable[[], Generator[Session, None, None]]

YEAR_ORDER = ("year_1", "year_2", "year_3", "year_4")
YEAR_FALLBACK_NAMES = {
    "year_1": "大一",
    "year_2": "大二",
    "year_3": "大三",
    "year_4": "大四",
}


def _grade_name(path_data: dict, grade_id: str) -> str:
    grade_plans = path_data.get("grade_plans")
    if isinstance(grade_plans, dict):
        grade_plan = grade_plans.get(grade_id)
        if isinstance(grade_plan, dict):
            grade_name = grade_plan.get("grade_name")
            if isinstance(grade_name, str) and grade_name.strip():
                return grade_name.strip()
    return YEAR_FALLBACK_NAMES[grade_id]


def _grade_courses(path_data: dict, grade_id: str) -> list[dict]:
    grade_plans = path_data.get("grade_plans")
    if not isinstance(grade_plans, dict):
        return []
    grade_plan = grade_plans.get(grade_id)
    if not isinstance(grade_plan, dict):
        return []
    course_nodes = grade_plan.get("course_nodes")
    if not isinstance(course_nodes, list):
        return []
    return [course for course in course_nodes if isinstance(course, dict)]


def _current_course_id(path_data: dict) -> str | None:
    current_learning_course = path_data.get("current_learning_course")
    if not isinstance(current_learning_course, dict):
        return None
    course_id = current_learning_course.get("course_node_id")
    if isinstance(course_id, str) and course_id.strip():
        return course_id.strip()
    return None


def _current_progress_state(path_data: dict) -> str | None:
    current_learning_course = path_data.get("current_learning_course")
    if not isinstance(current_learning_course, dict):
        return None
    progress_state = current_learning_course.get("progress_state")
    if isinstance(progress_state, str) and progress_state.strip():
        return progress_state.strip()
    return None


def _course_status(current_index: int | None, index: int, current_progress_state: str | None) -> str:
    if current_index is None:
        return "locked"
    if index < current_index:
        return "completed"
    if index == current_index:
        if current_progress_state == "completed":
            return "completed"
        return "current"
    return "locked"


def create_branch_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/branch", tags=["branch"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get("/overview", response_model=BranchOverviewReadResponse)
    def read_branch_overview(
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> BranchOverviewReadResponse:
        paths_by_year = get_all_year_learning_paths(session, current_user.uid)
        outline_rows = list(
            session.exec(
                select(UserCourseKnowledgeOutline)
                .where(UserCourseKnowledgeOutline.user_uid == current_user.uid)
            ).all()
        )

        outlines_by_course_id = {
            row.course_id: row
            for row in outline_rows
            if isinstance(row.course_id, str) and row.course_id.strip()
        }
        latest = get_latest_year_learning_path_row(session, current_user.uid)

        years: dict[str, BranchYearRead] = {}
        for grade_id in YEAR_ORDER:
            path_data = paths_by_year.get(grade_id, {})
            courses = _grade_courses(path_data, grade_id)
            current_course_id = _current_course_id(path_data)
            current_progress_state = _current_progress_state(path_data)
            current_index = next(
                (
                    index
                    for index, course in enumerate(courses)
                    if course.get("course_node_id") == current_course_id
                ),
                None,
            )

            branch_courses: list[BranchCourseNodeRead] = []
            has_outline_content = False
            for index, course in enumerate(courses):
                course_id = course.get("course_node_id")
                if not isinstance(course_id, str) or not course_id.strip():
                    continue
                outline_row = outlines_by_course_id.get(course_id)
                outline_data = outline_row.outline_data if outline_row else None
                sections = outline_data.get("sections") if isinstance(outline_data, dict) else None
                has_outline = isinstance(sections, list) and len(sections) > 0
                has_outline_content = has_outline_content or has_outline
                theme = course.get("course_or_chapter_theme")
                goal = course.get("course_goal")
                branch_courses.append(
                    BranchCourseNodeRead(
                        course_node_id=course_id,
                        course_or_chapter_theme=theme.strip() if isinstance(theme, str) and theme.strip() else course_id,
                        course_goal=goal.strip() if isinstance(goal, str) and goal.strip() else "继续沿着学习路径稳步推进。",
                        status=_course_status(current_index, index, current_progress_state),
                        has_outline=has_outline,
                    )
                )

            has_courses = len(branch_courses) > 0
            years[grade_id] = BranchYearRead(
                grade_id=grade_id,
                grade_name=_grade_name(path_data, grade_id),
                has_courses=has_courses,
                has_outline_content=has_outline_content,
                is_clickable=has_courses,
                current_course_id=current_course_id,
                courses=branch_courses,
            )

        return BranchOverviewReadResponse(
            years=years,
            updated_at=latest.updated_at if latest else None,
        )

    return router
