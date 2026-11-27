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
    ForestSubmissionRead,
)
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

        questions = await generate_quiz_questions(
            get_worker_llm(),
            chapter_id=chapter_id,
            chapter_title=str(quiz_session.chapter.get("title", "")),
            chapter_context=json.dumps(quiz_session.chapter, ensure_ascii=False),
            knowledge_point_ids=_extract_knowledge_point_ids(quiz_session.chapter),
        )
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
        grading = await grade_quiz_answers(
            get_worker_llm(), questions=questions, answers=payload.answers
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
                    get_worker_llm(), questions=questions, answers=payload.answers
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
