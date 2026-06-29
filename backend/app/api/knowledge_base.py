from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.admin import require_admin_user
from app.core.security import create_get_current_user
from app.models import (
    KnowledgeBaseIngestionJob,
    KnowledgeGap,
    KnowledgeGapFollow,
    KnowledgeGapNotice,
    KnowledgeSource,
    Textbook,
    TextbookExtensionResource,
    TextbookSectionContent,
    User,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from app.schemas import (
    KnowledgeBaseAgentRequest,
    KnowledgeBaseAgentResponse,
    KnowledgeBaseIngestionJobRead,
    KnowledgeBaseSourceConfirmRequest,
    KnowledgeBaseSourceConfirmResponse,
    KnowledgeGapAdminRead,
    KnowledgeGapFindMaterialsResponse,
    KnowledgeGapFollowRead,
    KnowledgeGapNoticeRead,
    KnowledgeGapRead,
    KnowledgeGapUploadResponse,
    KnowledgeSourceCreateRequest,
    KnowledgeSourceRead,
    StructuredTextbookCreateRequest,
    TextbookExtensionResourceCreateRequest,
    TextbookExtensionResourceRead,
    TextbookRead,
)
from app.services.knowledge_base_service import (
    add_textbook_extension_resource,
    confirm_textbook_source_result,
    create_knowledge_base_ingestion_job,
    create_knowledge_source,
    create_uploaded_textbook,
    follow_knowledge_gap,
    list_admitted_knowledge_sources,
    list_knowledge_sources,
    publish_textbook,
    run_knowledge_base_agent,
    textbook_payload_covers_topic,
    upsert_structured_textbook,
)

SessionDependency = Callable[[], Generator[Session, None, None]]


def create_knowledge_base_router(session_dependency: SessionDependency) -> APIRouter:
    router = APIRouter(tags=["knowledge-base"])
    get_current_user = create_get_current_user(session_dependency)

    def require_admin(current_user: User = Depends(get_current_user)) -> User:
        return require_admin_user(current_user)

    def require_student(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要学生身份",
            )
        return current_user

    _register_source_routes(router, session_dependency, require_admin)
    _register_textbook_routes(router, session_dependency, require_admin)
    _register_textbook_outline_routes(router, session_dependency, require_admin)
    _register_textbook_lifecycle_routes(router, session_dependency, require_admin)
    _register_ingestion_job_routes(router, session_dependency, require_admin)
    _register_agent_routes(router, session_dependency, require_admin)
    _register_gap_routes(router, session_dependency, require_admin)
    _register_extension_routes(router, session_dependency, require_admin)
    _register_student_routes(router, session_dependency, require_student)
    return router


def _register_source_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.get(
        "/api/admin/knowledge-base/sources",
        response_model=list[KnowledgeSourceRead],
    )
    def admin_sources(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[KnowledgeSource]:
        return list_knowledge_sources(session)

    @router.post(
        "/api/admin/knowledge-base/sources",
        response_model=KnowledgeSourceRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_admin_source(
        payload: KnowledgeSourceCreateRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeSource:
        return create_knowledge_source(session, KnowledgeSource(**payload.model_dump()))


def _register_textbook_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.get(
        "/api/admin/knowledge-base/textbooks",
        response_model=list[TextbookRead],
    )
    def admin_textbooks(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[Textbook]:
        return list(session.exec(select(Textbook).order_by(Textbook.textbook_id)).all())

    @router.post(
        "/api/admin/knowledge-base/textbooks",
        response_model=TextbookRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_admin_textbook(
        payload: StructuredTextbookCreateRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Textbook:
        return _upsert_textbook_payload(session, payload)

    @router.post(
        "/api/admin/knowledge-base/textbooks/{textbook_id}/publish",
        response_model=TextbookRead,
    )
    def publish_admin_textbook(
        textbook_id: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Textbook:
        textbook = _get_textbook_or_404(session, textbook_id)
        if textbook.student_availability_status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已归档教材不能发布。",
            )
        try:
            return publish_textbook(session, textbook_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc


def _register_textbook_outline_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.put(
        "/api/admin/knowledge-base/textbooks/{textbook_id}/outline",
        response_model=TextbookRead,
    )
    def update_admin_textbook_outline(
        textbook_id: str,
        outline: dict[str, object],
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Textbook:
        textbook = _get_textbook_or_404(session, textbook_id)
        textbook.outline = outline
        session.add(textbook)
        session.commit()
        session.refresh(textbook)
        return textbook


def _register_textbook_lifecycle_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.post(
        "/api/admin/knowledge-base/textbooks/{textbook_id}/unpublish",
        response_model=TextbookRead,
    )
    def unpublish_admin_textbook(
        textbook_id: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Textbook:
        textbook = _get_textbook_or_404(session, textbook_id)
        if textbook.student_availability_status != "published":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有已发布教材可以下架。",
            )
        textbook.student_availability_status = "unpublished"
        textbook.unpublished_at = datetime.now(timezone.utc)
        session.add(textbook)
        session.commit()
        session.refresh(textbook)
        return textbook

    @router.delete(
        "/api/admin/knowledge-base/textbooks/{textbook_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_admin_textbook(
        textbook_id: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> Response:
        textbook = _get_textbook_or_404(session, textbook_id)
        if textbook.student_availability_status == "draft" and not _has_student_binding(
            session, textbook_id
        ):
            _delete_draft_textbook(session, textbook)
        else:
            textbook.student_availability_status = "archived"
            textbook.archived_at = datetime.now(timezone.utc)
            session.add(textbook)
            session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)


def _register_ingestion_job_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.post(
        "/api/admin/knowledge-base/textbooks/{textbook_id}/agent-organize",
        response_model=KnowledgeBaseIngestionJobRead,
        status_code=status.HTTP_201_CREATED,
    )
    def organize_admin_textbook(
        textbook_id: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeBaseIngestionJob:
        _get_textbook_or_404(session, textbook_id)
        try:
            return create_knowledge_base_ingestion_job(session, textbook_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @router.get(
        "/api/admin/knowledge-base/ingestion-jobs/{job_id}",
        response_model=KnowledgeBaseIngestionJobRead,
    )
    def read_admin_ingestion_job(
        job_id: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeBaseIngestionJob:
        job = session.get(KnowledgeBaseIngestionJob, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="知识库任务不存在。",
            )
        return job


def _register_agent_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.post(
        "/api/admin/knowledge-base/agent",
        response_model=KnowledgeBaseAgentResponse,
    )
    def admin_knowledge_base_agent(
        payload: KnowledgeBaseAgentRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeBaseAgentResponse:
        return run_knowledge_base_agent(session, payload.message)

    @router.post(
        "/api/admin/knowledge-base/source-results/confirm",
        response_model=KnowledgeBaseSourceConfirmResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def confirm_admin_source_result(
        payload: KnowledgeBaseSourceConfirmRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeBaseSourceConfirmResponse:
        try:
            textbook, job = confirm_textbook_source_result(
                session,
                payload.source_result,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return KnowledgeBaseSourceConfirmResponse(
            textbook=TextbookRead.model_validate(textbook),
            job=KnowledgeBaseIngestionJobRead.model_validate(job),
        )

    @router.post(
        "/api/admin/knowledge-base/uploads",
        response_model=KnowledgeBaseSourceConfirmResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_admin_textbook_file(
        title: str = Form(min_length=1, max_length=256),
        language: str = Form(default="zh", max_length=32),
        description: str = Form(default=""),
        tags: str = Form(default=""),
        file: UploadFile = File(...),
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeBaseSourceConfirmResponse:
        try:
            textbook, job = create_uploaded_textbook(
                session,
                title=title,
                language=language,
                description=description,
                tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
                file_name=file.filename or "textbook.pdf",
                file_bytes=await file.read(),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return KnowledgeBaseSourceConfirmResponse(
            textbook=TextbookRead.model_validate(textbook),
            job=KnowledgeBaseIngestionJobRead.model_validate(job),
        )


def _register_gap_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.get(
        "/api/admin/knowledge-base/gaps",
        response_model=list[KnowledgeGapAdminRead],
    )
    def admin_gaps(
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[KnowledgeGapAdminRead]:
        sources = list_admitted_knowledge_sources(session)
        gaps = session.exec(select(KnowledgeGap).order_by(KnowledgeGap.gap_id)).all()
        return [
            KnowledgeGapAdminRead(
                **gap.model_dump(),
                sources=sources,
                actions=["find-materials", "upload"],
            )
            for gap in gaps
        ]

    @router.post(
        "/api/admin/knowledge-base/gaps/{gap_id}/find-materials",
        response_model=KnowledgeGapFindMaterialsResponse,
    )
    def find_admin_gap_materials(
        gap_id: str,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeGapFindMaterialsResponse:
        gap = _get_gap_or_404(session, gap_id)
        _reject_closed_gap_action(gap)
        gap.status = "material_searching"
        session.add(gap)
        session.commit()
        session.refresh(gap)
        return KnowledgeGapFindMaterialsResponse(
            gap=KnowledgeGapRead.model_validate(gap),
            sources=list_admitted_knowledge_sources(session),
        )

    @router.post(
        "/api/admin/knowledge-base/gaps/{gap_id}/upload",
        response_model=KnowledgeGapUploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def upload_admin_gap_materials(
        gap_id: str,
        payload: StructuredTextbookCreateRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeGapUploadResponse:
        gap = _get_gap_or_404(session, gap_id)
        _reject_closed_gap_action(gap)
        if not textbook_payload_covers_topic(
            payload.textbook.title,
            payload.textbook.description,
            payload.textbook.tags,
            payload.textbook.outline,
            gap.normalized_topic,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="上传教材未覆盖该知识缺口。",
            )
        gap.status = "material_found"
        session.add(gap)
        textbook = _upsert_textbook_payload(session, payload)
        session.refresh(gap)
        session.refresh(textbook)
        return KnowledgeGapUploadResponse(
            gap=KnowledgeGapRead.model_validate(gap),
            textbook=TextbookRead.model_validate(textbook),
        )


def _register_extension_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_admin: Callable[..., User],
) -> None:
    @router.get(
        "/api/admin/knowledge-base/textbooks/{textbook_id}/extension-resources",
        response_model=list[TextbookExtensionResourceRead],
    )
    def admin_extension_resources(
        textbook_id: str,
        section_id: list[str] = Query(default_factory=list),
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> list[TextbookExtensionResource]:
        _get_textbook_or_404(session, textbook_id)
        stmt = select(TextbookExtensionResource).where(
            TextbookExtensionResource.textbook_id == textbook_id
        )
        if section_id:
            stmt = stmt.where(TextbookExtensionResource.section_id.in_(section_id))
        return list(
            session.exec(
                stmt.order_by(
                    TextbookExtensionResource.section_id,
                    TextbookExtensionResource.resource_id,
                )
            ).all()
        )

    @router.post(
        "/api/admin/knowledge-base/textbooks/{textbook_id}/extension-resources",
        response_model=TextbookExtensionResourceRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_admin_extension_resource(
        textbook_id: str,
        payload: TextbookExtensionResourceCreateRequest,
        _: User = Depends(require_admin),
        session: Session = Depends(session_dependency),
    ) -> TextbookExtensionResource:
        _get_textbook_or_404(session, textbook_id)
        resource = TextbookExtensionResource(
            textbook_id=textbook_id,
            **payload.model_dump(),
        )
        try:
            return add_textbook_extension_resource(session, resource)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc


def _register_student_routes(
    router: APIRouter,
    session_dependency: SessionDependency,
    require_student: Callable[..., User],
) -> None:
    @router.post(
        "/api/knowledge-base/gaps/{gap_id}/follow",
        response_model=KnowledgeGapFollowRead,
    )
    def follow_gap(
        gap_id: str,
        current_user: User = Depends(require_student),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeGapFollowRead:
        try:
            return follow_knowledge_gap(session, gap_id, current_user.uid)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except IntegrityError as exc:
            session.rollback()
            existing_follow = _get_existing_follow(session, gap_id, current_user.uid)
            if existing_follow is not None:
                return existing_follow
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="知识缺口关注已存在。",
            ) from exc

    @router.get(
        "/api/knowledge-base/notices",
        response_model=list[KnowledgeGapNoticeRead],
    )
    def notices(
        current_user: User = Depends(require_student),
        session: Session = Depends(session_dependency),
    ) -> list[KnowledgeGapNotice]:
        return list(
            session.exec(
                select(KnowledgeGapNotice)
                .where(KnowledgeGapNotice.user_uid == current_user.uid)
                .order_by(KnowledgeGapNotice.created_at, KnowledgeGapNotice.notice_id)
            ).all()
        )

    @router.post(
        "/api/knowledge-base/notices/{notice_id}/read",
        response_model=KnowledgeGapNoticeRead,
    )
    def read_notice(
        notice_id: str,
        current_user: User = Depends(require_student),
        session: Session = Depends(session_dependency),
    ) -> KnowledgeGapNotice:
        notice = session.exec(
            select(KnowledgeGapNotice).where(
                KnowledgeGapNotice.notice_id == notice_id,
                KnowledgeGapNotice.user_uid == current_user.uid,
            )
        ).first()
        if notice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="知识库提醒不存在。",
            )
        if notice.read_at is None:
            notice.read_at = datetime.now(timezone.utc)
            session.add(notice)
            session.commit()
            session.refresh(notice)
        return notice


def _upsert_textbook_payload(
    session: Session, payload: StructuredTextbookCreateRequest
) -> Textbook:
    textbook = Textbook(**payload.textbook.model_dump())
    sections = [
        TextbookSectionContent(
            textbook_id=textbook.textbook_id,
            **section.model_dump(),
        )
        for section in payload.sections
    ]
    try:
        return upsert_structured_textbook(session, textbook, sections)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _get_textbook_or_404(session: Session, textbook_id: str) -> Textbook:
    textbook = session.get(Textbook, textbook_id)
    if textbook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="教材不存在。",
        )
    return textbook


def _get_gap_or_404(session: Session, gap_id: str) -> KnowledgeGap:
    gap = session.get(KnowledgeGap, gap_id)
    if gap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识缺口不存在。",
        )
    return gap


def _reject_closed_gap_action(gap: KnowledgeGap) -> None:
    if gap.status in {"resolved", "closed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="知识缺口已结束，不能继续处理。",
        )


def _get_existing_follow(
    session: Session, gap_id: str, user_uid: str
) -> KnowledgeGapFollow | None:
    return session.exec(
        select(KnowledgeGapFollow).where(
            KnowledgeGapFollow.gap_id == gap_id,
            KnowledgeGapFollow.user_uid == user_uid,
        )
    ).first()


def _has_student_binding(session: Session, textbook_id: str) -> bool:
    learning_paths = session.exec(select(UserYearLearningPath)).all()
    if any(
        _contains_source_textbook_id(row.path_data, textbook_id)
        for row in learning_paths
    ):
        return True

    course_outlines = session.exec(select(UserCourseKnowledgeOutline)).all()
    return any(
        _contains_source_textbook_id(row.outline_data, textbook_id)
        for row in course_outlines
    )


def _contains_source_textbook_id(value: object, textbook_id: str) -> bool:
    if isinstance(value, dict):
        if value.get("source_textbook_id") == textbook_id:
            return True
        return any(
            _contains_source_textbook_id(nested_value, textbook_id)
            for nested_value in value.values()
        )
    if isinstance(value, list):
        return any(_contains_source_textbook_id(item, textbook_id) for item in value)
    return False


def _delete_draft_textbook(session: Session, textbook: Textbook) -> None:
    jobs = session.exec(
        select(KnowledgeBaseIngestionJob).where(
            KnowledgeBaseIngestionJob.textbook_id == textbook.textbook_id
        )
    ).all()
    resources = session.exec(
        select(TextbookExtensionResource).where(
            TextbookExtensionResource.textbook_id == textbook.textbook_id
        )
    ).all()
    sections = session.exec(
        select(TextbookSectionContent).where(
            TextbookSectionContent.textbook_id == textbook.textbook_id
        )
    ).all()
    for job in jobs:
        session.delete(job)
    for resource in resources:
        session.delete(resource)
    for section in sections:
        session.delete(section)
    session.delete(textbook)
    session.commit()
