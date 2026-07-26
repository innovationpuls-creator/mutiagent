from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterWeakness,
    ConversationSession,
    CourseResourceQuality,
    CultivationProgram,
    User,
    UserCourseKnowledgeOutline,
    UserProfile,
    UserYearLearningPath,
)
from app.schemas import DataCohortRead, DataOverviewResponse, UserLearningDataRead
from app.services.admin_account_service import delete_user_learning_data
from app.services.auth_service import to_user_read
from app.services.cultivation_program_service import (
    delete_program_for_cohort,
    to_program_read,
)


def get_data_overview(session: Session) -> DataOverviewResponse:
    accounts = {"student": 0, "admin": 0}
    for role, count in session.exec(
        select(User.role, func.count(User.uid)).group_by(User.role)
    ).all():
        category = "admin" if role in {"admin", "teacher"} else "student"
        accounts[category] += int(count)

    cohort_scopes = (
        select(User.school, User.major, User.class_name)
        .where(
            func.trim(User.school) != "",
            func.trim(User.major) != "",
            func.trim(User.class_name) != "",
        )
        .distinct()
        .subquery()
    )

    return DataOverviewResponse(
        accounts=accounts,
        cohorts=_count_statement(
            session, select(func.count()).select_from(cohort_scopes)
        ),
        programs=_count_model_rows(session, CultivationProgram),
        learning_data={
            "profiles": _count_model_rows(session, UserProfile),
            "year_learning_paths": _count_model_rows(session, UserYearLearningPath),
            "course_outlines": _count_model_rows(session, UserCourseKnowledgeOutline),
            "chapter_quizzes": _count_model_rows(session, ChapterQuiz),
            "chapter_progress": _count_model_rows(session, ChapterProgress),
            "resource_quality": _count_model_rows(session, CourseResourceQuality),
            "conversation_sessions": _count_model_rows(session, ConversationSession),
        },
    )


def list_data_cohorts(session: Session) -> list[DataCohortRead]:
    teacher = aliased(User)
    is_program_manager = User.role.in_(("admin", "teacher"))
    student_count = func.coalesce(func.sum(case((is_program_manager, 0), else_=1)), 0)
    admin_count = func.coalesce(func.sum(case((is_program_manager, 1), else_=0)), 0)
    cohort_rows = session.exec(
        select(
            User.school,
            User.major,
            User.class_name,
            student_count,
            admin_count,
            CultivationProgram.program_id,
            CultivationProgram.updated_at,
            teacher.username,
        )
        .select_from(User)
        .outerjoin(
            CultivationProgram,
            and_(
                CultivationProgram.school == User.school,
                CultivationProgram.major == User.major,
                CultivationProgram.class_name == User.class_name,
            ),
        )
        .outerjoin(teacher, teacher.uid == CultivationProgram.teacher_uid)
        .where(
            func.trim(User.school) != "",
            func.trim(User.major) != "",
            func.trim(User.class_name) != "",
        )
        .group_by(
            User.school,
            User.major,
            User.class_name,
            CultivationProgram.program_id,
            CultivationProgram.updated_at,
            teacher.username,
        )
        .order_by(User.school, User.major, User.class_name)
    ).all()
    rows: list[DataCohortRead] = []
    for (
        school,
        major,
        class_name,
        student_count_value,
        admin_count_value,
        program_id,
        program_updated_at,
        teacher_name,
    ) in cohort_rows:
        rows.append(
            DataCohortRead(
                school=school,
                major=major,
                class_name=class_name,
                student_count=int(student_count_value),
                admin_count=int(admin_count_value),
                has_program=program_id is not None,
                program_teacher_name=teacher_name if program_id is not None else None,
                program_updated_at=(
                    program_updated_at if program_id is not None else None
                ),
            )
        )
    return rows


def list_data_programs(session: Session):
    program_rows = session.exec(
        select(CultivationProgram, User)
        .outerjoin(User, User.uid == CultivationProgram.teacher_uid)
        .order_by(CultivationProgram.updated_at.desc())
    ).all()
    return [to_program_read(program, teacher) for program, teacher in program_rows]


def read_user_learning_data(session: Session, uid: str) -> UserLearningDataRead:
    user = session.get(User, uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    profile = session.get(UserProfile, uid)
    return UserLearningDataRead(
        user=to_user_read(user),
        profile=profile.profile_data if profile else None,
        year_learning_paths=[
            _model_dict(row)
            for row in session.exec(
                select(UserYearLearningPath).where(UserYearLearningPath.user_uid == uid)
            ).all()
        ],
        course_outlines=[
            _model_dict(row)
            for row in session.exec(
                select(UserCourseKnowledgeOutline).where(
                    UserCourseKnowledgeOutline.user_uid == uid
                )
            ).all()
        ],
        chapter_quizzes=[
            _model_dict(row)
            for row in session.exec(
                select(ChapterQuiz).where(ChapterQuiz.user_uid == uid)
            ).all()
        ],
        chapter_progress=[
            _model_dict(row)
            for row in session.exec(
                select(ChapterProgress).where(ChapterProgress.user_uid == uid)
            ).all()
        ],
        chapter_weaknesses=[
            _model_dict(row)
            for row in session.exec(
                select(ChapterWeakness).where(ChapterWeakness.user_uid == uid)
            ).all()
        ],
        resource_quality=[
            _model_dict(row)
            for row in session.exec(
                select(CourseResourceQuality).where(
                    CourseResourceQuality.user_uid == uid
                )
            ).all()
        ],
        conversation_sessions=[
            _model_dict(row)
            for row in session.exec(
                select(ConversationSession).where(ConversationSession.user_uid == uid)
            ).all()
        ],
    )


def delete_learning_data_for_user(session: Session, uid: str) -> None:
    if session.get(User, uid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    delete_user_learning_data(session, uid)
    session.commit()


def delete_program_for_data_cohort(
    session: Session, school: str, major: str, class_name: str
) -> None:
    delete_program_for_cohort(session, school, major, class_name)


def _model_dict(row: Any) -> dict:
    return row.model_dump(mode="json")


def _count_model_rows(session: Session, model: type[Any]) -> int:
    return _count_statement(session, select(func.count()).select_from(model))


def _count_statement(session: Session, statement: Any) -> int:
    return int(session.exec(statement).one())
