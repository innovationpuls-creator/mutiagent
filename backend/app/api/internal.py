from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, StreamingResponse

from app.model_config_schemas import (
    OAuthCredentialPayload,
    OAuthRefreshPayload,
    UsageRecordPayload,
)
from app.models import User
from app.services import chat_context_service as chat_service
from app.services import learning_path_runtime_service as path_service
from app.services import model_config_service as model_service
from app.services import outline_service, resource_service

INTERNAL_TOKEN_HEADER = "X-Internal-Token"


class TurnPayload(BaseModel):
    user_uid: str = Field(min_length=1)
    user_message: str = Field(min_length=1, max_length=4000)
    image_attachment: str | None = None
    assistant_message: str | None = None
    session_state_patch: dict | None = None


class StudentProfilePayload(BaseModel):
    profile_data: dict


class TextbookContextPayload(BaseModel):
    learning_topic: str = Field(min_length=1, max_length=200)
    student_goal_summary: str = Field(default="", max_length=4000)


class AssemblePathPayload(BaseModel):
    profile: dict
    learning_topic: str = Field(min_length=1)
    plan: dict
    intake_courses: list[dict]


class SaveYearPathPayload(BaseModel):
    learning_topic: str = Field(min_length=1)
    path_data: dict


class OutlineSourcePayload(BaseModel):
    course_id: str = Field(default="", max_length=200)


class ComposeOutlinePayload(BaseModel):
    course: dict
    naming: dict


class SaveOutlinesPayload(BaseModel):
    path_fingerprints: dict[str, str]
    outlines: list[dict] = Field(min_length=1)


class PreparePayload(BaseModel):
    mode: str = "generate"


class PromptPayload(BaseModel):
    issue: str = ""
    regeneration_focus: str = ""
    previous_html: str = ""


class ValidateMarkdownPayload(BaseModel):
    raw_output: str


class ValidateAnimationPayload(BaseModel):
    animations: list[dict] = Field(default_factory=list)
    fallback: bool = False


class SectionResourcePayload(BaseModel):
    phase: str
    value: dict | None = None
    failure: str = ""


class FinishPayload(BaseModel):
    succeeded_section_ids: list[str] = Field(default_factory=list)


class LegacyStreamPayload(BaseModel):
    user_uid: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    image_attachment: str | None = None


def create_internal_router(engine: Engine, internal_token: str | None) -> APIRouter:  # noqa: C901
    def verify_internal_token(
        provided: str | None = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
    ) -> None:
        if provided is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少内部令牌"
            )
        if not internal_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="内部接口未启用"
            )
        if not hmac.compare_digest(
            provided.encode("utf-8"), internal_token.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="内部令牌无效"
            )

    router = APIRouter(
        prefix="/internal",
        dependencies=[Depends(verify_internal_token)],
        include_in_schema=False,
    )

    @router.get("/health")
    def internal_health() -> JSONResponse:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "database": "unavailable"},
            )
        return JSONResponse(content={"status": "ok", "database": "connected"})

    @router.get("/users/{user_uid}/auth-status")
    def user_auth_status(user_uid: str) -> dict[str, str | bool | None]:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.uid == user_uid)).first()
            if user is None:
                return {
                    "user_uid": user_uid,
                    "exists": False,
                    "role": None,
                    "is_active": False,
                }
            return {
                "user_uid": user.uid,
                "exists": True,
                "role": user.role,
                "is_active": user.is_active,
            }

    @router.get("/users/{user_uid}/model-runtime-config")
    def model_runtime_config(user_uid: str, request: Request) -> JSONResponse:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.uid == user_uid)).first()
            if user is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            config = model_service.runtime_config(
                session, user_uid, request.app.state.model_cipher
            )
        return JSONResponse(content=jsonable_encoder(config))

    @router.post("/users/{user_uid}/providers/{provider_id}/oauth-refresh-lock")
    def oauth_refresh_lock(
        user_uid: str,
        provider_id: str,
        payload: OAuthRefreshPayload,
        request: Request,
    ) -> JSONResponse:
        with Session(engine) as session:
            result = model_service.oauth_refresh_lock(
                session,
                user_uid,
                provider_id,
                payload.previous_refresh_fingerprint,
                payload.new_credential,
                payload.expires_at,
                request.app.state.model_cipher,
            )
        return JSONResponse(content=jsonable_encoder(result))

    @router.put("/users/{user_uid}/providers/{provider_id}/oauth-credential")
    def save_oauth_credential(
        user_uid: str,
        provider_id: str,
        payload: OAuthCredentialPayload,
        request: Request,
    ) -> dict[str, bool]:
        with Session(engine) as session:
            if session.exec(select(User).where(User.uid == user_uid)).first() is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            model_service.save_oauth_credential(
                session,
                user_uid,
                provider_id,
                payload.credential,
                payload.expires_at,
                payload.account_label,
                request.app.state.model_cipher,
            )
        request.app.state.ai_gateway_client.invalidate_user_model_config(user_uid)
        return {"ok": True}

    @router.post("/users/{user_uid}/model-usage")
    def model_usage(user_uid: str, payload: UsageRecordPayload) -> dict[str, str]:
        with Session(engine) as session:
            if session.exec(select(User).where(User.uid == user_uid)).first() is None:
                raise HTTPException(status_code=404, detail="用户不存在")
            row = model_service.record_usage(session, user_uid, payload)
            return {"usage_id": row.usage_id}

    def _require_user(session: Session, user_uid: str) -> None:
        if session.exec(select(User).where(User.uid == user_uid)).first() is None:
            raise HTTPException(status_code=404, detail="用户不存在")

    @router.get("/chat/sessions/{session_id}/context")
    def chat_context(session_id: str, user_uid: str) -> JSONResponse:
        with Session(engine) as session:
            _require_user(session, user_uid)
            try:
                context = chat_service.build_chat_context(session, session_id, user_uid)
            except chat_service.SessionNotFoundError:
                raise HTTPException(status_code=404, detail="会话不存在") from None
        return JSONResponse(content=jsonable_encoder(context))

    @router.post("/chat/sessions/{session_id}/turn")
    def chat_turn(session_id: str, payload: TurnPayload) -> dict:
        with Session(engine) as session:
            try:
                return chat_service.persist_turn(
                    session,
                    session_id,
                    payload.user_uid,
                    user_message=payload.user_message,
                    image_attachment=payload.image_attachment,
                    assistant_message=payload.assistant_message,
                    session_state_patch=payload.session_state_patch,
                )
            except chat_service.SessionNotFoundError:
                raise HTTPException(status_code=404, detail="会话不存在") from None

    @router.put("/students/{user_uid}/profile")
    def put_student_profile(user_uid: str, payload: StudentProfilePayload) -> dict:
        profile = payload.profile_data
        if profile.get("type") not in {"collecting", "basic_profile"}:
            raise HTTPException(status_code=422, detail="画像类型无效")
        with Session(engine) as session:
            _require_user(session, user_uid)
            return chat_service.save_student_profile(session, user_uid, profile)

    @router.get("/students/{user_uid}/learning-overview")
    def learning_overview(user_uid: str) -> JSONResponse:
        with Session(engine) as session:
            _require_user(session, user_uid)
            overview = chat_service.build_learning_overview(session, user_uid)
        return JSONResponse(content=jsonable_encoder(overview))

    @router.post("/knowledge-base/textbook-context-for-intake")
    def textbook_context_for_intake(payload: TextbookContextPayload) -> dict:
        with Session(engine) as session:
            return path_service.textbook_context_for_intake(
                session, payload.learning_topic, payload.student_goal_summary
            )

    @router.get("/students/{user_uid}/protected-courses")
    def protected_courses(user_uid: str) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            return {"courses": path_service.protected_courses(session, user_uid)}

    @router.get("/students/{user_uid}/learning-paths/progress-snapshots")
    def progress_snapshots(user_uid: str) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            return {
                "snapshots": jsonable_encoder(
                    path_service.progress_snapshots(session, user_uid)
                )
            }

    @router.post("/students/{user_uid}/learning-paths/{grade_year}/assemble")
    def assemble_learning_path(
        user_uid: str, grade_year: str, payload: AssemblePathPayload
    ) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            try:
                path = path_service.assemble_learning_path(
                    session,
                    user_uid,
                    profile=payload.profile,
                    grade_year=grade_year,
                    learning_topic=payload.learning_topic,
                    plan=payload.plan,
                    intake_courses=payload.intake_courses,
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"学习路径规划无法装配：{exc}"
                ) from None
            return {"path_data": path}

    @router.put("/students/{user_uid}/learning-paths/{grade_year}")
    def put_year_learning_path(
        user_uid: str, grade_year: str, payload: SaveYearPathPayload
    ) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            path_service.save_year_path(
                session, user_uid, grade_year, payload.learning_topic, payload.path_data
            )
            return {"ok": True, "grade_year": grade_year}

    @router.post("/students/{user_uid}/outline-source-context")
    def outline_source_context(user_uid: str, payload: OutlineSourcePayload) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            try:
                return outline_service.source_context(
                    session, user_uid, payload.course_id
                )
            except outline_service.OutlineSourceError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.post("/students/{user_uid}/course-outlines/compose")
    def compose_course_outline(user_uid: str, payload: ComposeOutlinePayload) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
        try:
            return {
                "outline": outline_service.compose_outline(
                    payload.course, payload.naming
                )
            }
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.post("/students/{user_uid}/course-outlines/batch")
    def save_course_outlines(user_uid: str, payload: SaveOutlinesPayload) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            try:
                saved = outline_service.save_outlines(
                    session, user_uid, payload.path_fingerprints, payload.outlines
                )
            except outline_service.PathChangedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None
            return {"saved_course_ids": saved}

    def _resource_call(user_uid: str, call):
        with Session(engine) as session:
            _require_user(session, user_uid)
            try:
                return call(session)
            except resource_service.ResourceRequestError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None

    _RES = "/students/{user_uid}/courses/{course_id}"

    @router.post(_RES + "/chapters/{chapter_id}/generation-prepare")
    def generation_prepare(
        user_uid: str, course_id: str, chapter_id: str, payload: PreparePayload
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.prepare_generation(
                s, user_uid, course_id, chapter_id, payload.mode
            ),
        )

    @router.post(_RES + "/chapters/{chapter_id}/generation-finish")
    def generation_finish(
        user_uid: str, course_id: str, chapter_id: str, payload: FinishPayload
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.finish_generation(
                s, user_uid, course_id, chapter_id, payload.succeeded_section_ids
            ),
        )

    @router.post(_RES + "/sections/{section_id}/markdown/prompt")
    def section_markdown_prompt(
        user_uid: str, course_id: str, section_id: str, payload: PromptPayload
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.markdown_prompt(
                s,
                user_uid,
                course_id,
                section_id,
                payload.issue,
                payload.regeneration_focus,
            ),
        )

    @router.post(_RES + "/sections/{section_id}/markdown/validate")
    def section_markdown_validate(
        user_uid: str, course_id: str, section_id: str, payload: ValidateMarkdownPayload
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.validate_markdown(
                s, user_uid, course_id, section_id, payload.raw_output
            ),
        )

    @router.post(_RES + "/sections/{section_id}/video/search")
    async def section_video_search(
        user_uid: str, course_id: str, section_id: str
    ) -> dict:
        with Session(engine) as session:
            _require_user(session, user_uid)
            try:
                return await resource_service.search_section_video(
                    session, user_uid, course_id, section_id
                )
            except resource_service.ResourceRequestError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.post(_RES + "/sections/{section_id}/animation/prompt")
    def section_animation_prompt(
        user_uid: str, course_id: str, section_id: str, payload: PromptPayload
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.animation_prompt(
                s,
                user_uid,
                course_id,
                section_id,
                payload.issue,
                payload.previous_html,
            ),
        )

    @router.post(_RES + "/sections/{section_id}/animation/validate")
    def section_animation_validate(
        user_uid: str,
        course_id: str,
        section_id: str,
        payload: ValidateAnimationPayload,
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.validate_animations(
                s,
                user_uid,
                course_id,
                section_id,
                payload.animations,
                fallback=payload.fallback,
            ),
        )

    @router.put(_RES + "/sections/{section_id}/resources")
    def put_section_resources(
        user_uid: str, course_id: str, section_id: str, payload: SectionResourcePayload
    ) -> dict:
        return _resource_call(
            user_uid,
            lambda s: resource_service.save_section_phase(
                s,
                user_uid,
                course_id,
                section_id,
                payload.phase,
                payload.value,
                payload.failure,
            ),
        )

    @router.post("/chat/sessions/{session_id}/legacy-stream")
    async def legacy_stream(
        session_id: str, payload: LegacyStreamPayload
    ) -> StreamingResponse:
        """Transitional bridge (until M5-M7): run the pre-migration orchestration for
        turns that need a not-yet-migrated agent. Same SSE frames as the old route."""
        from app.api.orchestration import _stream_chat_events
        from app.schemas import ChatMessageRequest

        def _check(session: Session) -> None:
            _require_user(session, payload.user_uid)
            try:
                chat_service.load_owned_session_row(
                    session, session_id, payload.user_uid
                )
            except chat_service.SessionNotFoundError:
                raise HTTPException(status_code=404, detail="会话不存在") from None

        with Session(engine) as session:
            await run_in_threadpool(_check, session)

        request_payload = ChatMessageRequest(
            session_id=session_id,
            message=payload.message,
            image_attachment=payload.image_attachment,
        )

        async def frames():
            with Session(engine) as session:
                async for frame in _stream_chat_events(
                    session_id=session_id,
                    user_uid=payload.user_uid,
                    user_message=payload.message,
                    db_session=session,
                    payload=request_payload,
                ):
                    yield frame

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
