from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import ChapterProgress, ChapterQuiz, ChapterQuizAttempt, ChapterWeakness
from app.schemas import (
    ForestAttemptRead,
    ForestChapterProgressRead,
    ForestQuizQuestionRead,
    ForestQuizRead,
    ForestQuizSessionReadResponse,
)
from app.services.course_knowledge_service import get_user_course_knowledge_outline
from app.services.learning_path_service import (
    advance_current_learning_course,
    get_all_year_learning_paths,
    get_grade_courses,
)


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


def _normalize_options(options_raw: object) -> list[dict[str, str]]:
    if not isinstance(options_raw, list):
        return []
    normalized_opts = []
    for idx, opt in enumerate(options_raw):
        if isinstance(opt, dict):
            option_id = _clean_text(opt.get("option_id"))
            text = _clean_text(opt.get("text"))
            if not option_id:
                option_id = chr(65 + idx)
            if not text:
                text = _clean_text(opt.get("option_text")) or _clean_text(opt.get("label")) or ""
            normalized_opts.append({"option_id": option_id, "text": text})
        elif isinstance(opt, str):
            opt_str = opt.strip()
            option_id = ""
            text = opt_str
            if len(opt_str) > 2 and opt_str[0].isalpha() and opt_str[1] in (".", ":", "、", " "):
                option_id = opt_str[0].upper()
                text = opt_str[2:].strip()
            elif len(opt_str) > 1 and opt_str[0].isalpha() and opt_str[0].isupper() and idx < 26:
                expected_letter = chr(65 + idx)
                if opt_str.startswith(expected_letter):
                    option_id = expected_letter
                    text = opt_str[len(expected_letter):].strip()
                    if text.startswith((".", ":", "、", " ")):
                        text = text[1:].strip()
            
            if not option_id:
                option_id = chr(65 + idx)
            normalized_opts.append({"option_id": option_id, "text": text})
    return normalized_opts


def _quiz_to_read(quiz: ChapterQuiz) -> ForestQuizRead:
    questions = []
    for question in quiz.questions:
        if isinstance(question, dict):
            questions.append(
                ForestQuizQuestionRead(
                    question_id=question.get("question_id") or "",
                    type=question.get("type") or "single_choice",
                    prompt=question.get("prompt") or "",
                    options=_normalize_options(question.get("options")),
                    starter_code=question.get("starter_code") or "",
                    image_prompt=question.get("image_prompt") or "",
                    points=question.get("points") or 0,
                )
            )
    return ForestQuizRead(
        quiz_id=quiz.quiz_id,
        course_node_id=quiz.course_node_id,
        chapter_id=quiz.chapter_id,
        status=quiz.status,
        questions=questions,
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


def first_generatable_chapter_id(
    session: Session,
    user_uid: str,
    course_node_id: str,
    outline: dict | None,
) -> str | None:
    if not isinstance(outline, dict):
        return "1"
    chapters = _top_level_sections(outline)
    if not chapters:
        return "1"
    for index, chapter in enumerate(chapters):
        chapter_id = chapter.get("section_id")
        if not isinstance(chapter_id, str):
            continue
        current_progress = session.get(ChapterProgress, (user_uid, course_node_id, chapter_id))
        if current_progress is not None and current_progress.state == "passed":
            continue
        if index == 0:
            return chapter_id
        previous_id = chapters[index - 1].get("section_id")
        if not isinstance(previous_id, str):
            return None
        previous_progress = session.get(ChapterProgress, (user_uid, course_node_id, previous_id))
        if previous_progress is not None and previous_progress.state == "passed":
            return chapter_id
        return None
    return None


def chapter_generation_is_available(
    session: Session,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
    outline: dict | None,
) -> bool:
    return first_generatable_chapter_id(session, user_uid, course_node_id, outline) == chapter_id


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

    composed_markdowns = outline.get("section_composed_markdowns")
    if not isinstance(composed_markdowns, dict):
        composed_markdowns = {}
    chapter_markdown_data = composed_markdowns.get(chapter_id)
    if not chapter_markdown_data:
        markdowns = outline.get("section_markdowns")
        if not isinstance(markdowns, dict):
            markdowns = {}
        chapter_markdown_data = markdowns.get(chapter_id)

    if isinstance(chapter_markdown_data, dict):
        chapter = {**chapter, "composed_markdown": chapter_markdown_data}

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


def generate_or_read_quiz(
    session: Session,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
    questions: list[dict],
    *,
    regenerate: bool,
) -> ForestQuizRead:
    existing = _read_quiz(session, user_uid, course_node_id, chapter_id)
    if existing is not None and existing.status == "ready" and not regenerate:
        return _quiz_to_read(existing)

    now = datetime.now(timezone.utc)
    if existing is None:
        quiz = ChapterQuiz(
            quiz_id=make_id("quiz"),
            user_uid=user_uid,
            course_node_id=course_node_id,
            chapter_id=chapter_id,
            status="ready",
            questions=questions,
            created_at=now,
            updated_at=now,
        )
    else:
        quiz = existing
        quiz.status = "ready"
        quiz.questions = questions
        quiz.generation_error = ""
        quiz.updated_at = now

    session.add(quiz)
    session.commit()
    session.refresh(quiz)
    return _quiz_to_read(quiz)


def _chapter_ids_for_course(session: Session, user_uid: str, course_node_id: str) -> tuple[str, list[str]]:
    outline = get_user_course_knowledge_outline(session, user_uid, course_node_id)
    if not isinstance(outline, dict):
        return "", []
    chapters = _top_level_sections(outline)
    grade_year = _clean_text(outline.get("grade_year"))
    return grade_year, [
        chapter["section_id"]
        for chapter in chapters
        if isinstance(chapter.get("section_id"), str)
    ]


def _next_chapter_id(chapter_ids: list[str], chapter_id: str) -> str | None:
    index = chapter_ids.index(chapter_id) if chapter_id in chapter_ids else -1
    if index < 0 or index + 1 >= len(chapter_ids):
        return None
    return chapter_ids[index + 1]


def _resolve_knowledge_point_name(
    session: Session,
    user_uid: str,
    course_node_id: str,
    kp_id: str,
    *,
    outline: dict | None = None,
    year_paths: dict[str, dict] | None = None,
    preloaded: bool = False,
) -> str:
    """从课程大纲或学习路径中解析知识点名称，如果找不到则返回 kp_id 本身。"""
    if not kp_id:
        return ""

    def _safe_str(val: object) -> str:
        return str(val) if val is not None else ""

    # 1. 尝试从课程大纲 sections.key_knowledge_points 查找
    try:
        if outline is None and not preloaded:
            outline = get_user_course_knowledge_outline(session, user_uid, course_node_id)
        if isinstance(outline, dict):
            sections = outline.get("sections")
            if isinstance(sections, list):
                for section in sections:
                    if isinstance(section, dict):
                        key_kps = section.get("key_knowledge_points")
                        if isinstance(key_kps, list):
                            for kp in key_kps:
                                if isinstance(kp, str) and kp.strip() == kp_id:
                                    return kp.strip()
                                elif isinstance(kp, dict):
                                    if _safe_str(kp.get("knowledge_point_id")).strip() == kp_id or _safe_str(kp.get("id")).strip() == kp_id:
                                        return _safe_str(kp.get("name") or kp.get("title") or kp_id).strip()
    except Exception:
        pass

    # 2. 尝试从学习路径 core_knowledge_points 查找
    try:
        if year_paths is None and not preloaded:
            year_paths = get_all_year_learning_paths(session, user_uid)
        found = _find_course(year_paths, course_node_id)
        if found is not None:
            _, _, course = found
            if isinstance(course, dict):
                core_kps = course.get("core_knowledge_points")
                if isinstance(core_kps, list):
                    for kp in core_kps:
                        if isinstance(kp, dict):
                            if _safe_str(kp.get("knowledge_point_id")).strip() == kp_id or _safe_str(kp.get("id")).strip() == kp_id:
                                return _safe_str(kp.get("name") or kp.get("title") or kp_id).strip()
                        elif isinstance(kp, str) and kp.strip() == kp_id:
                            return kp.strip()
    except Exception:
        pass

    return kp_id


def _analyze_weakness(
    session: Session,
    *,
    user_uid: str,
    course_node_id: str,
    chapter_id: str,
    questions: list[dict],
    grading_result: dict,
) -> list[ChapterWeakness]:
    question_results = grading_result.get("question_results", [])
    if not isinstance(question_results, list):
        return []

    question_map = {}
    for q in questions:
        if isinstance(q, dict):
            question_map[q.get("question_id", "")] = q

    weak_points: dict[str, int] = {}
    for qr in question_results:
        if not isinstance(qr, dict):
            continue
        qid = qr.get("question_id", "")
        score = qr.get("score", 0)
        max_score = qr.get("max_score", 0)
        if max_score > 0 and score < max_score:
            question = question_map.get(qid, {})
            kp_ids = question.get("knowledge_point_ids", [])
            if not isinstance(kp_ids, list):
                continue
            for kp_id in kp_ids:
                kp_str = str(kp_id).strip()
                if kp_str:
                    weak_points[kp_str] = weak_points.get(kp_str, 0) + 1

    # Pre-fetch outline and year_paths once to prevent N+1 DB select query overhead
    outline = get_user_course_knowledge_outline(session, user_uid, course_node_id)
    year_paths = get_all_year_learning_paths(session, user_uid)

    weaknesses = []
    for kp_id, count in weak_points.items():
        severity = min(3, count)
        kp_name = _resolve_knowledge_point_name(
            session,
            user_uid,
            course_node_id,
            kp_id,
            outline=outline,
            year_paths=year_paths,
            preloaded=True,
        )
        weakness = ChapterWeakness(
            weakness_id=make_id("weakness"),
            user_uid=user_uid,
            course_node_id=course_node_id,
            chapter_id=chapter_id,
            knowledge_point_id=kp_id,
            knowledge_point_name=kp_name,
            severity=severity,
        )
        session.add(weakness)
        weaknesses.append(weakness)

    return weaknesses


def submit_quiz_attempt(
    session: Session,
    user_uid: str,
    quiz_id: str,
    answers: dict,
    grading_result: dict,
) -> tuple[ForestAttemptRead, list[ChapterWeakness]]:
    quiz = session.get(ChapterQuiz, quiz_id)
    if quiz is None or quiz.user_uid != user_uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测验不存在")

    score = int(grading_result.get("score", 0))
    passed = score > PASSING_SCORE
    attempt = ChapterQuizAttempt(
        attempt_id=make_id("attempt"),
        quiz_id=quiz.quiz_id,
        user_uid=user_uid,
        answers=answers,
        score=score,
        passed=passed,
        grading_result=grading_result,
    )
    session.add(attempt)

    weaknesses = _analyze_weakness(
        session,
        user_uid=user_uid,
        course_node_id=quiz.course_node_id,
        chapter_id=quiz.chapter_id,
        questions=quiz.questions if isinstance(quiz.questions, list) else [],
        grading_result=grading_result,
    )

    now = datetime.now(timezone.utc)
    current_progress = _ensure_progress(session, user_uid, quiz.course_node_id, quiz.chapter_id, "available")
    current_progress.best_score = max(current_progress.best_score, score)
    current_progress.latest_attempt_id = attempt.attempt_id
    current_progress.updated_at = now

    if passed:
        current_progress.state = "passed"
        current_progress.passed_at = now
        grade_year, chapter_ids = _chapter_ids_for_course(session, user_uid, quiz.course_node_id)
        next_chapter_id = _next_chapter_id(chapter_ids, quiz.chapter_id)
        if next_chapter_id:
            next_progress = _ensure_progress(session, user_uid, quiz.course_node_id, next_chapter_id, "available")
            next_progress.state = "available"
            next_progress.updated_at = now
            session.add(next_progress)
        elif grade_year:
            advance_current_learning_course(session, user_uid, grade_year, score)

    session.add(current_progress)
    session.commit()
    session.refresh(attempt)
    return _attempt_to_read(attempt), weaknesses  # type: ignore[return-value]


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
