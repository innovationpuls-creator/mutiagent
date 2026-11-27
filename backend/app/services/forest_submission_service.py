"""Immutable quiz submissions, atomic progress writes, and exact-result recovery."""

from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import ChapterQuiz, ChapterQuizAttempt
from app.schemas import ForestQuizAttemptCreateRequest
from app.services.forest_service import (
    _attempt_to_read,
    _chapter_ids_for_course,
    _chapter_is_available,
    _next_chapter_id,
    _top_level_sections,
    quiz_version,
    submit_quiz_attempt,
)
from app.services.leaf_service import read_leaf_course
from app.services.learning_path_service import (
    get_all_year_learning_paths,
    get_canopy_overview,
    get_current_learning_course,
)
from app.services.student_lock import lock_student


def submission_attempt_id(uid: str, submission_id: UUID) -> str:
    return (
        f"attempt_{uuid5(NAMESPACE_URL, f'onetree:forest:{uid}:{submission_id}').hex}"
    )


def read_submission(
    session: Session, uid: str, quiz_id: str, submission_id: UUID
) -> dict:
    attempt = session.get(ChapterQuizAttempt, submission_attempt_id(uid, submission_id))
    if (
        attempt is None
        or attempt.user_uid != uid
        or attempt.quiz_id != quiz_id
        or attempt.recovery_snapshot is None
    ):
        raise HTTPException(status_code=404, detail="尚未确认本次提交结果")
    snapshot = dict(attempt.recovery_snapshot)
    created_at = snapshot.pop("_attempt_created_at", None)
    data = _attempt_to_read(attempt).model_dump(mode="json")
    if created_at:
        data["created_at"] = created_at
    return {"attempt": data, **snapshot}


def existing_submission(
    session: Session, uid: str, quiz_id: str, payload: ForestQuizAttemptCreateRequest
) -> dict | None:
    if payload.client_submission_id is None:
        return None
    attempt = session.get(
        ChapterQuizAttempt,
        submission_attempt_id(uid, payload.client_submission_id),
        populate_existing=True,
    )
    if attempt is None:
        return None
    if (
        attempt.quiz_id != quiz_id
        or attempt.quiz_version != payload.quiz_version
        or attempt.answers != payload.answers
    ):
        raise HTTPException(
            status_code=409, detail="本次提交标识已绑定其他答案，请重新确认测验"
        )
    return read_submission(session, uid, quiz_id, payload.client_submission_id)


def validate_quiz_context(session: Session, uid: str, quiz: ChapterQuiz) -> None:
    leaf = read_leaf_course(session, uid, quiz.course_node_id)
    chapters = _top_level_sections(leaf.outline or {})
    if leaf.access_state == "locked" or not any(
        c.get("section_id") == quiz.chapter_id for c in chapters
    ):
        raise HTTPException(status_code=409, detail="课程或章节已更新，请重新进入测验")
    if not _chapter_is_available(
        session, uid, quiz.course_node_id, quiz.chapter_id, chapters
    ):
        raise HTTPException(status_code=403, detail="章节尚未解锁")


def prepare_submission(
    session: Session, uid: str, quiz_id: str, payload: ForestQuizAttemptCreateRequest
) -> tuple[list, str]:
    quiz = session.get(ChapterQuiz, quiz_id, populate_existing=True)
    if quiz is None or quiz.user_uid != uid:
        raise HTTPException(status_code=404, detail="测验已失效，请重新进入章节")
    version = quiz_version(quiz.questions)
    if payload.quiz_version is not None and version != payload.quiz_version:
        raise HTTPException(
            status_code=409, detail="题目已更新，请重新进入测验；原草稿仍保留在本机"
        )
    validate_quiz_context(session, uid, quiz)
    return quiz.questions, version


def persist_submission(
    session: Session,
    uid: str,
    quiz_id: str,
    payload: ForestQuizAttemptCreateRequest,
    questions: list,
    version: str,
    grading: dict,
) -> dict:
    lock_student(session, uid)
    quiz = session.exec(
        select(ChapterQuiz)
        .where(ChapterQuiz.quiz_id == quiz_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    result = existing_submission(session, uid, quiz_id, payload)
    if result is not None:
        return result
    if quiz is None or quiz.user_uid != uid:
        raise HTTPException(status_code=404, detail="测验已失效，请重新进入章节")
    if quiz_version(quiz.questions) != version:
        raise HTTPException(status_code=409, detail="题目已更新，请重新进入测验")
    validate_quiz_context(session, uid, quiz)
    attempt_id = (
        submission_attempt_id(uid, payload.client_submission_id)
        if payload.client_submission_id
        else None
    )
    attempt, weaknesses = submit_quiz_attempt(
        session,
        uid,
        quiz_id,
        payload.answers,
        grading,
        questions_snapshot=questions,
        attempt_id=attempt_id,
        version=version,
        commit=False,
    )
    _year, chapter_ids = _chapter_ids_for_course(session, uid, quiz.course_node_id)
    next_chapter = (
        _next_chapter_id(chapter_ids, quiz.chapter_id) if attempt.passed else None
    )
    next_course = None
    if attempt.passed and next_chapter is None:
        from app.services.forest_service import _find_course

        found = _find_course(
            get_all_year_learning_paths(session, uid), quiz.course_node_id
        )
        current = get_current_learning_course(found[1]) if found else None
        if current and current.get("course_node_id") != quiz.course_node_id:
            next_course = current.get("course_node_id")
    snapshot = {
        "weaknesses": [
            {
                "knowledge_point_id": w.knowledge_point_id,
                "knowledge_point_name": w.knowledge_point_name,
                "severity": w.severity,
            }
            for w in weaknesses
        ],
        "canopy_overview": get_canopy_overview(session, uid),
        "next_unlocked_chapter_id": next_chapter,
        "next_course_id": next_course,
    }
    stored = session.get(ChapterQuizAttempt, attempt.attempt_id)
    stored.recovery_snapshot = {
        **snapshot,
        "_attempt_created_at": attempt.model_dump(mode="json")["created_at"],
    }
    session.add(stored)
    session.commit()
    return {"attempt": attempt.model_dump(mode="json"), **snapshot}
