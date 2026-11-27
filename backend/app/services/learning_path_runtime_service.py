"""Internal helpers for the TS gateway's intake / learning-path agents (M5).

The model-facing steps moved to the gateway; the deterministic parts that already
encode the `learning_path.v2.course_node` contract stay here and are exposed over
`/internal/*`, so the contract has a single implementation.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import UserCourseKnowledgeOutline
from app.services.course_knowledge_service import (
    delete_user_course_outlines_by_grade_year,
)
from app.services.knowledge_base_service import (
    get_published_textbook_context_for_topic,
)
from app.services.learning_path_service import (
    get_all_year_learning_paths,
    get_learning_path_progress_snapshots,
    upsert_year_learning_path,
)

STARTED_STATES = {"in_progress", "completed"}


def textbook_context_for_intake(
    session: Session, learning_topic: str, student_goal_summary: str
) -> dict:
    """Published textbook outlines for a topic; registers a KnowledgeGap if none."""
    return get_published_textbook_context_for_topic(
        session, learning_topic, student_goal_summary=student_goal_summary
    )


def _started_titles(path: object) -> list[str]:
    if not isinstance(path, dict):
        return []
    nodes: list[object] = [path.get("current_learning_course")]
    grade_plans = path.get("grade_plans")
    for plan in grade_plans.values() if isinstance(grade_plans, dict) else []:
        course_nodes = plan.get("course_nodes") if isinstance(plan, dict) else None
        nodes.extend(course_nodes if isinstance(course_nodes, list) else [])
    titles: list[str] = []
    for node in nodes:
        if isinstance(node, dict) and node.get("progress_state") in STARTED_STATES:
            title = str(node.get("course_or_chapter_theme") or "").strip()
            if title:
                titles.append(title)
    return titles


def protected_courses(session: Session, user_uid: str) -> list[dict[str, str]]:
    """Titles a draft must not silently drop: has an outline, or already started."""
    protected: dict[str, str] = {}
    outlines = session.exec(
        select(UserCourseKnowledgeOutline).where(
            UserCourseKnowledgeOutline.user_uid == user_uid
        )
    ).all()
    for outline in outlines:
        name = (outline.course_name or "").strip()
        if name:
            protected[name] = "已有课程大纲"
    for path in get_all_year_learning_paths(session, user_uid).values():
        for title in _started_titles(path):
            protected[title] = "已开始学习"
    return [{"title": title, "reason": reason} for title, reason in protected.items()]


def progress_snapshots(session: Session, user_uid: str) -> list[dict[str, object]]:
    return get_learning_path_progress_snapshots(
        get_all_year_learning_paths(session, user_uid)
    )


def assemble_learning_path(
    session: Session,
    user_uid: str,
    *,
    profile: dict,
    grade_year: str,
    learning_topic: str,
    plan: dict,
    intake_courses: list[dict],
) -> dict:
    """Expand the model's lightweight plan into the full v2 contract.

    Raises ValueError (message is safe to show the model) when the plan is unusable.
    """
    from app.orchestration.agents.learning_path import (
        _apply_existing_progress_to_path,
        _build_learning_path_from_plan,
        _progress_snapshot_for_grade,
        _validate_learning_path_contract,
    )

    path = _build_learning_path_from_plan(
        profile,
        grade_year=grade_year,
        learning_topic=learning_topic,
        plan_data=plan,
        intake_courses=intake_courses,
    )
    snapshot = _progress_snapshot_for_grade(
        progress_snapshots(session, user_uid), grade_year
    )
    path = _apply_existing_progress_to_path(path, grade_year, snapshot)
    error = _validate_learning_path_contract(path)
    if error:
        raise ValueError(error)
    return path


def save_year_path(
    session: Session,
    user_uid: str,
    grade_year: str,
    learning_topic: str,
    path: dict,
) -> None:
    """One transaction: write the year path and drop that year's stale outlines."""
    try:
        upsert_year_learning_path(
            session, user_uid, grade_year, learning_topic, path, commit=False
        )
        delete_user_course_outlines_by_grade_year(
            session, user_uid, grade_year, commit=False
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
