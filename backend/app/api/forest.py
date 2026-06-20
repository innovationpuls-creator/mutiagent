from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.models import ChapterQuiz, User
from app.orchestration.agents.quiz import (
    generate_quiz_questions,
    grade_quiz_answers,
    stream_forest_ai_response,
)
from app.orchestration.llm import get_worker_llm
from app.schemas import (
    ForestAiStreamRequest,
    ForestAttemptRead,
    ForestQuizAttemptCreateRequest,
    ForestQuizGenerateRequest,
    ForestQuizRead,
    ForestQuizSessionReadResponse,
)
from app.services.forest_service import (
    _chapter_ids_for_course,
    _next_chapter_id,
    generate_or_read_quiz,
    read_forest_quiz_session,
    submit_quiz_attempt,
)
from app.services.learning_path_service import (
    get_canopy_overview,
    get_year_learning_path,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def _extract_knowledge_point_ids(chapter: dict) -> list[str]:
    """从章节大纲数据中提取所有知识点 ID。"""
    kp_ids: list[str] = []
    kp_ids.extend(chapter.get("core_knowledge_point_ids") or [])
    for hierarchy in chapter.get("knowledge_hierarchy") or []:
        if isinstance(hierarchy, dict):
            kp_ids.extend(hierarchy.get("knowledge_point_ids") or [])
    key_kps = chapter.get("key_knowledge_points", [])
    if isinstance(key_kps, list):
        for kp in key_kps:
            if isinstance(kp, str):
                kp_ids.append(kp)
            elif isinstance(kp, dict):
                kp_id = kp.get("knowledge_point_id") or kp.get("id")
                if kp_id:
                    kp_ids.append(str(kp_id))
    return list(dict.fromkeys(kp_ids))


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_forest_ai_events(
    payload: ForestAiStreamRequest,
) -> AsyncGenerator[str, None]:
    try:
        async for chunk in stream_forest_ai_response(
            get_worker_llm(),
            message=payload.message,
            context=payload.active_question_context.model_dump(),
            image_attachment=payload.image_attachment,
        ):
            yield _sse("forest_ai_text_chunk", {"chunk": chunk})
        yield _sse("forest_ai_completed", {"message": "completed"})
    except Exception as exc:
        yield _sse("forest_error", {"message": str(exc) or "Forest AI 暂时不可用"})


def create_forest_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/api/forest", tags=["forest"])
    get_current_user = create_get_current_user(session_dependency)

    @router.get(
        "/courses/{course_node_id}/chapters/{chapter_id}/quiz",
        response_model=ForestQuizSessionReadResponse,
    )
    def get_forest_quiz_session(
        course_node_id: str,
        chapter_id: str,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ForestQuizSessionReadResponse:
        return read_forest_quiz_session(
            session, current_user.uid, course_node_id, chapter_id
        )

    @router.post(
        "/courses/{course_node_id}/chapters/{chapter_id}/quiz/generate",
        response_model=ForestQuizRead,
    )
    async def generate_forest_quiz(
        course_node_id: str,
        chapter_id: str,
        payload: ForestQuizGenerateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ForestQuizRead:
        quiz_session = read_forest_quiz_session(
            session, current_user.uid, course_node_id, chapter_id
        )
        if quiz_session.progress.state == "locked":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="章节尚未解锁"
            )
        if (
            quiz_session.quiz is not None
            and quiz_session.quiz.status == "ready"
            and not payload.regenerate
        ):
            return quiz_session.quiz

        questions = await generate_quiz_questions(
            get_worker_llm(),
            chapter_id=chapter_id,
            chapter_title=str(quiz_session.chapter.get("title", "")),
            chapter_context=json.dumps(quiz_session.chapter, ensure_ascii=False),
            knowledge_point_ids=_extract_knowledge_point_ids(quiz_session.chapter),
        )
        return generate_or_read_quiz(
            session,
            current_user.uid,
            course_node_id,
            chapter_id,
            questions,
            regenerate=payload.regenerate,
        )

    @router.post("/quizzes/{quiz_id}/attempts", response_model=ForestAttemptRead)
    async def create_forest_quiz_attempt(
        quiz_id: str,
        payload: ForestQuizAttemptCreateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ForestAttemptRead:
        quiz = session.get(ChapterQuiz, quiz_id)
        if quiz is None or quiz.user_uid != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="测验不存在"
            )

        grading_result = await grade_quiz_answers(
            get_worker_llm(),
            questions=quiz.questions,
            answers=payload.answers,
        )
        attempt, _weaknesses = submit_quiz_attempt(
            session, current_user.uid, quiz.quiz_id, payload.answers, grading_result
        )
        return attempt

    @router.post("/quizzes/{quiz_id}/attempts/stream")
    async def submit_quiz_attempt_stream(
        quiz_id: str,
        payload: ForestQuizAttemptCreateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        quiz = session.get(ChapterQuiz, quiz_id)
        if quiz is None or quiz.user_uid != current_user.uid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="测验不存在"
            )

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                yield _sse(
                    "status", {"phase": "grading", "message": "正在批改你的答案..."}
                )

                grading_result = await grade_quiz_answers(
                    get_worker_llm(),
                    questions=quiz.questions,
                    answers=payload.answers,
                )

                yield _sse(
                    "status", {"phase": "analyzing", "message": "正在分析薄弱知识点..."}
                )

                attempt, weaknesses = submit_quiz_attempt(
                    session,
                    current_user.uid,
                    quiz.quiz_id,
                    payload.answers,
                    grading_result,
                )

                weakness_data = [
                    {
                        "knowledge_point_id": w.knowledge_point_id,
                        "knowledge_point_name": w.knowledge_point_name,
                        "severity": w.severity,
                    }
                    for w in weaknesses
                ]

                if weakness_data:
                    yield _sse(
                        "status",
                        {
                            "phase": "weakness_found",
                            "message": f"发现 {len(weakness_data)} 个薄弱知识点",
                            "weak_points": weakness_data,
                        },
                    )

                yield _sse(
                    "status", {"phase": "unlocking", "message": "正在解锁下一章节..."}
                )

                canopy = get_canopy_overview(session, current_user.uid)
                grade_year, chapter_ids = _chapter_ids_for_course(
                    session, current_user.uid, quiz.course_node_id
                )
                next_chapter_id = _next_chapter_id(chapter_ids, quiz.chapter_id)

                next_unlocked_chapter_id = next_chapter_id if attempt.passed else None
                next_course_id = None
                if attempt.passed and not next_chapter_id:
                    updated_path = get_year_learning_path(
                        session, current_user.uid, grade_year
                    )
                    if updated_path:
                        current_course = updated_path.get("current_learning_course", {})
                        if (
                            current_course
                            and current_course.get("course_node_id")
                            != quiz.course_node_id
                        ):
                            next_course_id = current_course.get("course_node_id")

                yield _sse(
                    "done",
                    {
                        "attempt": {
                            "attempt_id": attempt.attempt_id,
                            "quiz_id": attempt.quiz_id,
                            "score": attempt.score,
                            "passed": attempt.passed,
                            "answers": attempt.answers,
                            "grading_result": attempt.grading_result,
                            "created_at": attempt.created_at.isoformat(),
                        },
                        "weaknesses": weakness_data,
                        "canopy_overview": canopy,
                        "next_unlocked_chapter_id": next_unlocked_chapter_id,
                        "next_course_id": next_course_id,
                    },
                )
            except Exception as exc:
                yield _sse("error", {"message": str(exc) or "测验提交失败"})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/ai/stream")
    async def stream_forest_ai(
        payload: ForestAiStreamRequest,
        _: User = Depends(get_current_user),
    ) -> StreamingResponse:
        return StreamingResponse(
            _stream_forest_ai_events(payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
