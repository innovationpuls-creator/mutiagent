from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Generator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.security import create_get_current_user
from app.database import run_db, session_factory_from_session
from app.models import User
from app.orchestration.agents.quiz import (
    normalize_grading_result,
    normalize_quiz_questions,
)
from app.schemas import (
    ForestAttemptRead,
    ForestQuizAttemptCreateRequest,
    ForestQuizGenerateRequest,
    ForestQuizRead,
    ForestQuizSessionReadResponse,
    ForestSubmissionRead,
)
from app.services.ai_gateway_client import (
    AiGatewayError,
    AiGatewayUnavailableError,
    acall_gateway_ai,
)
from app.services.forest_ai_service import quiz_generation_material
from app.services.forest_service import (
    generate_or_read_quiz,
    read_forest_quiz_session,
)
from app.services.forest_submission_service import (
    existing_submission,
    persist_submission,
    prepare_submission,
    read_submission,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


async def _gateway(path: str, body: dict) -> dict:
    """Run one AI job on the student's own model; surface gateway errors faithfully."""
    try:
        return await acall_gateway_ai(path, body)
    except AiGatewayError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    except AiGatewayUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="AI 服务暂时不可用，请稍后重试"
        ) from exc


async def generate_quiz_questions(uid: str, material: dict) -> list[dict]:
    generated = await _gateway(
        "/internal/ai/quiz/generate", {"user_uid": uid, **material}
    )
    try:
        return normalize_quiz_questions(generated.get("questions"))
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="出题结果不合规，请稍后重试"
        ) from exc


async def grade_quiz_answers(uid: str, questions: list, answers: dict) -> dict:
    result = await _gateway(
        "/internal/ai/quiz/grade",
        {"user_uid": uid, "questions": questions, "answers": answers},
    )
    return normalize_grading_result(result)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_forest_router(session_dependency: SessionDependency) -> APIRouter:  # noqa: C901
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
        factory = session_factory_from_session(session)
        quiz_session = await run_db(
            factory,
            read_forest_quiz_session,
            current_user.uid,
            course_node_id,
            chapter_id,
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

        material = await run_db(
            factory,
            quiz_generation_material,
            current_user.uid,
            course_node_id,
            quiz_session.chapter,
        )
        questions = await generate_quiz_questions(current_user.uid, material)
        return await run_db(
            factory,
            generate_or_read_quiz,
            current_user.uid,
            course_node_id,
            chapter_id,
            questions,
            regenerate=payload.regenerate,
            expected_chapter=quiz_session.chapter,
        )

    @router.post("/quizzes/{quiz_id}/attempts", response_model=ForestAttemptRead)
    async def create_forest_quiz_attempt(
        quiz_id: str,
        payload: ForestQuizAttemptCreateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> ForestAttemptRead:
        factory = session_factory_from_session(session)
        existing = await run_db(
            factory, existing_submission, current_user.uid, quiz_id, payload
        )
        if existing:
            return ForestAttemptRead.model_validate(existing["attempt"])
        questions, version = await run_db(
            factory, prepare_submission, current_user.uid, quiz_id, payload
        )
        grading = await grade_quiz_answers(current_user.uid, questions, payload.answers)
        result = await run_db(
            factory,
            persist_submission,
            current_user.uid,
            quiz_id,
            payload,
            questions,
            version,
            grading,
        )
        return ForestAttemptRead.model_validate(result["attempt"])

    @router.get(
        "/quizzes/{quiz_id}/submissions/{client_submission_id}",
        response_model=ForestSubmissionRead,
    )
    def recover_submission(
        quiz_id: str,
        client_submission_id: UUID,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> dict:
        return read_submission(session, current_user.uid, quiz_id, client_submission_id)

    @router.post("/quizzes/{quiz_id}/attempts/stream")
    async def submit_quiz_attempt_stream(
        quiz_id: str,
        payload: ForestQuizAttemptCreateRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(session_dependency),
    ) -> StreamingResponse:
        factory = session_factory_from_session(session)
        existing = await run_db(
            factory, existing_submission, current_user.uid, quiz_id, payload
        )
        questions, version = (
            ([], "")
            if existing
            else await run_db(
                factory, prepare_submission, current_user.uid, quiz_id, payload
            )
        )

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                if existing:
                    yield _sse("done", existing)
                    return
                yield _sse(
                    "status", {"phase": "grading", "message": "正在批改你的答案…"}
                )
                grading = await grade_quiz_answers(
                    current_user.uid, questions, payload.answers
                )
                yield _sse(
                    "status", {"phase": "analyzing", "message": "正在分析学习进度…"}
                )
                result = await run_db(
                    factory,
                    persist_submission,
                    current_user.uid,
                    quiz_id,
                    payload,
                    questions,
                    version,
                    grading,
                )
                yield _sse("done", result)
            except Exception as exc:
                yield _sse(
                    "error",
                    {
                        "message": str(exc.detail)
                        if isinstance(exc, HTTPException)
                        else str(exc) or "测验提交失败",
                        "status_code": exc.status_code
                        if isinstance(exc, HTTPException)
                        else 500,
                    },
                )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
