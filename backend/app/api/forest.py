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
    generate_or_read_quiz,
    read_forest_quiz_session,
    submit_quiz_attempt,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_forest_ai_events(payload: ForestAiStreamRequest) -> AsyncGenerator[str, None]:
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
        return read_forest_quiz_session(session, current_user.uid, course_node_id, chapter_id)

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
        quiz_session = read_forest_quiz_session(session, current_user.uid, course_node_id, chapter_id)
        if quiz_session.progress.state == "locked":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="章节尚未解锁")
        if quiz_session.quiz is not None and quiz_session.quiz.status == "ready" and not payload.regenerate:
            return quiz_session.quiz

        questions = await generate_quiz_questions(
            get_worker_llm(),
            chapter_id=chapter_id,
            chapter_title=str(quiz_session.chapter.get("title", "")),
            chapter_context=json.dumps(quiz_session.chapter, ensure_ascii=False),
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测验不存在")

        grading_result = await grade_quiz_answers(
            get_worker_llm(),
            questions=quiz.questions,
            answers=payload.answers,
        )
        return submit_quiz_attempt(session, current_user.uid, quiz.quiz_id, payload.answers, grading_result)

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
