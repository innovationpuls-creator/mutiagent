from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import HTTPException, status
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
    users = session.exec(select(User)).all()
    accounts = {"student": 0, "teacher": 0, "admin": 0}
    cohorts = set()
    for user in users:
        accounts[user.role] = accounts.get(user.role, 0) + 1
        if user.school.strip() and user.major.strip() and user.class_name.strip():
            cohorts.add((user.school, user.major, user.class_name))

    return DataOverviewResponse(
        accounts=accounts,
        cohorts=len(cohorts),
        programs=len(session.exec(select(CultivationProgram)).all()),
        learning_data={
            "profiles": len(session.exec(select(UserProfile)).all()),
            "year_learning_paths": len(
                session.exec(select(UserYearLearningPath)).all()
            ),
            "course_outlines": len(
                session.exec(select(UserCourseKnowledgeOutline)).all()
            ),
            "chapter_quizzes": len(session.exec(select(ChapterQuiz)).all()),
            "chapter_progress": len(session.exec(select(ChapterProgress)).all()),
            "resource_quality": len(session.exec(select(CourseResourceQuality)).all()),
            "conversation_sessions": len(
                session.exec(select(ConversationSession)).all()
            ),
        },
    )


def list_data_cohorts(session: Session) -> list[DataCohortRead]:
    users = session.exec(select(User)).all()
    grouped: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"student": 0, "teacher": 0, "admin": 0}
    )
    for user in users:
        if (
            not user.school.strip()
            or not user.major.strip()
            or not user.class_name.strip()
        ):
            continue
        grouped[(user.school, user.major, user.class_name)][user.role] += 1

    programs = session.exec(select(CultivationProgram)).all()
    program_map = {
        (program.school, program.major, program.class_name): program
        for program in programs
    }
    rows: list[DataCohortRead] = []
    for (school, major, class_name), counts in sorted(grouped.items()):
        program = program_map.get((school, major, class_name))
        teacher = session.get(User, program.teacher_uid) if program else None
        rows.append(
            DataCohortRead(
                school=school,
                major=major,
                class_name=class_name,
                student_count=counts["student"],
                teacher_count=counts["teacher"],
                admin_count=counts["admin"],
                has_program=program is not None,
                program_teacher_name=teacher.username if teacher else None,
                program_updated_at=program.updated_at if program else None,
            )
        )
    return rows


def list_data_programs(session: Session):
    programs = session.exec(
        select(CultivationProgram).order_by(CultivationProgram.updated_at.desc())
    ).all()
    rows = []
    for program in programs:
        rows.append(to_program_read(program, session.get(User, program.teacher_uid)))
    return rows


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
