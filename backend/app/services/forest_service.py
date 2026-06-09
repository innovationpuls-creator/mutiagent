from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import ChapterProgress, ChapterQuiz, ChapterQuizAttempt
from app.schemas import (
    ForestAttemptRead,
    ForestChapterProgressRead,
    ForestQuizQuestionRead,
    ForestQuizRead,
    ForestQuizSessionReadResponse,
)
from app.services.course_knowledge_service import get_user_course_knowledge_outline
from app.services.learning_path_service import get_all_year_learning_paths, get_grade_courses


PASSING_SCORE = 70


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _top_level_sections(outline: dict) -> list[dict]:
    sections = outline.get("sections")
    if not isinstance(sections, list):
        return []
    top_level = [
        section
        for section in sections
        if isinstance(section, dict) and section.get("parent_section_id") is None
    ]
    return sorted(
        top_level,
        key=lambda item: item.get("order_index") if isinstance(item.get("order_index"), int) else 0,
    )


def _find_course(
    year_paths: dict[str, dict],
    course_node_id: str,
) -> tuple[str, dict, dict] | None:
    for grade_year, path_data in year_paths.items():
        courses = get_grade_courses(path_data, grade_year)
        for course in courses:
            if isinstance(course, dict) and course.get("course_node_id") == course_node_id:
                return grade_year, path_data, course
    return None


def _read_quiz(
    session: Session,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
) -> ChapterQuiz | None:
    stmt = select(ChapterQuiz).where(
        ChapterQuiz.user_uid == user_uid,
        ChapterQuiz.course_node_id == course_node_id,
        ChapterQuiz.chapter_id == chapter_id,
    )
    return session.exec(stmt).first()


def _latest_attempt(session: Session, user_uid: str, quiz_id: str) -> ChapterQuizAttempt | None:
    stmt = (
        select(ChapterQuizAttempt)
        .where(
            ChapterQuizAttempt.user_uid == user_uid,
            ChapterQuizAttempt.quiz_id == quiz_id,
        )
        .order_by(ChapterQuizAttempt.created_at.desc())
    )
    return session.exec(stmt).first()


def _progress_to_read(progress: ChapterProgress) -> ForestChapterProgressRead:
    return ForestChapterProgressRead(
        course_node_id=progress.course_node_id,
        chapter_id=progress.chapter_id,
        state=progress.state,
        best_score=progress.best_score,
        latest_attempt_id=progress.latest_attempt_id,
        passed_at=progress.passed_at,
        updated_at=progress.updated_at,
    )


def _quiz_to_read(quiz: ChapterQuiz) -> ForestQuizRead:
    return ForestQuizRead(
        quiz_id=quiz.quiz_id,
        course_node_id=quiz.course_node_id,
        chapter_id=quiz.chapter_id,
        status=quiz.status,
        questions=[
            ForestQuizQuestionRead(**question)
            for question in quiz.questions
            if isinstance(question, dict)
        ],
        generation_error=quiz.generation_error,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
    )


def _attempt_to_read(attempt: ChapterQuizAttempt | None) -> ForestAttemptRead | None:
    if attempt is None:
        return None
    return ForestAttemptRead(
        attempt_id=attempt.attempt_id,
        quiz_id=attempt.quiz_id,
        score=attempt.score,
        passed=attempt.passed,
        answers=attempt.answers,
        grading_result=attempt.grading_result,
        created_at=attempt.created_at,
    )


def _ensure_progress(
    session: Session,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
    initial_state: str,
) -> ChapterProgress:
    progress = session.get(ChapterProgress, (user_uid, course_node_id, chapter_id))
    if progress is None:
        progress = ChapterProgress(
            user_uid=user_uid,
            course_node_id=course_node_id,
            chapter_id=chapter_id,
            state=initial_state,
        )
        session.add(progress)
        session.commit()
        session.refresh(progress)
    return progress


def _chapter_is_available(
    session: Session,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
    chapters: list[dict],
) -> bool:
    if chapters and chapters[0].get("section_id") == chapter_id:
        return True

    index = next(
        (idx for idx, chapter in enumerate(chapters) if chapter.get("section_id") == chapter_id),
        -1,
    )
    if index <= 0:
        return False

    previous_id = chapters[index - 1].get("section_id")
    if not isinstance(previous_id, str):
        return False

    previous_progress = session.get(ChapterProgress, (user_uid, course_node_id, previous_id))
    return previous_progress is not None and previous_progress.state == "passed"


def _course_to_read_dict(course_node_id: str, grade_year: str, course: dict) -> dict:
    title = _clean_text(course.get("course_or_chapter_theme")) or course_node_id
    goal = _clean_text(course.get("course_goal")) or "继续沿着学习路径稳步推进。"
    return {
        "course_node_id": course_node_id,
        "grade_id": grade_year,
        "course_or_chapter_theme": title,
        "course_goal": goal,
        "status": "current",
        "has_outline": True,
    }


def read_forest_quiz_session(
    session: Session,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
) -> ForestQuizSessionReadResponse:
    year_paths = get_all_year_learning_paths(session, user_uid)
    found = _find_course(year_paths, course_node_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程不存在")

    grade_year, _path_data, course = found
    outline = get_user_course_knowledge_outline(session, user_uid, course_node_id)
    if not isinstance(outline, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程大纲不存在")

    chapters = _top_level_sections(outline)
    chapter = next((item for item in chapters if item.get("section_id") == chapter_id), None)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

    available = _chapter_is_available(session, user_uid, course_node_id, chapter_id, chapters)
    progress = _ensure_progress(
        session,
        user_uid,
        course_node_id,
        chapter_id,
        "available" if available else "locked",
    )
    if progress.state == "locked" and available:
        progress.state = "available"
        progress.updated_at = datetime.now(timezone.utc)
        session.add(progress)
        session.commit()
        session.refresh(progress)

    quiz = _read_quiz(session, user_uid, course_node_id, chapter_id)
    latest_attempt = _latest_attempt(session, user_uid, quiz.quiz_id) if quiz is not None else None

    return ForestQuizSessionReadResponse(
        course=_course_to_read_dict(course_node_id, grade_year, course),
        chapter=chapter,
        quiz=_quiz_to_read(quiz) if quiz is not None else None,
        latest_attempt=_attempt_to_read(latest_attempt),
        progress=_progress_to_read(progress),
        next_unlocked_chapter_id=None,
        next_course_id=None,
    )


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
