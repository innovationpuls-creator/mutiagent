from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import CultivationProgram, User
from app.schemas import CultivationProgramRead


def to_program_read(program: CultivationProgram, teacher: User | None) -> CultivationProgramRead:
    return CultivationProgramRead(
        program_id=program.program_id,
        teacher_uid=program.teacher_uid,
        teacher_name=teacher.username if teacher else "",
        teacher_identifier=teacher.identifier if teacher else "",
        school=program.school,
        major=program.major,
        class_name=program.class_name,
        courses=[course for course in program.courses if isinstance(course, dict)],
        published_at=program.published_at,
        updated_at=program.updated_at,
    )


def get_program_for_teacher(session: Session, teacher: User) -> CultivationProgramRead | None:
    _require_program_manager(teacher)
    program = session.exec(
        select(CultivationProgram).where(CultivationProgram.teacher_uid == teacher.uid)
    ).first()
    if program is None:
        return None
    return to_program_read(program, teacher)


def save_program_for_teacher(
    session: Session,
    teacher: User,
    courses: list[dict],
    school: str | None = None,
    major: str | None = None,
    class_name: str | None = None,
) -> CultivationProgramRead:
    _require_program_manager(teacher)
    program_school, program_major, program_class_name = _resolve_cohort(teacher, school, major, class_name)
    now = datetime.now(timezone.utc)
    program = session.exec(
        select(CultivationProgram).where(
            CultivationProgram.school == program_school,
            CultivationProgram.major == program_major,
            CultivationProgram.class_name == program_class_name,
        )
    ).first()
    if program is not None and program.teacher_uid != teacher.uid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该学校、专业、班级已有已发布人培方案",
        )
    if program is None:
        program = CultivationProgram(
            program_id=str(uuid4()),
            teacher_uid=teacher.uid,
            school=program_school,
            major=program_major,
            class_name=program_class_name,
            courses=courses,
            created_at=now,
            updated_at=now,
        )
    else:
        program.school = program_school
        program.major = program_major
        program.class_name = program_class_name
        program.courses = courses
        program.updated_at = now
    session.add(program)
    session.commit()
    session.refresh(program)
    return to_program_read(program, teacher)


def publish_program_for_teacher(
    session: Session,
    teacher: User,
    courses: list[dict],
    school: str | None = None,
    major: str | None = None,
    class_name: str | None = None,
) -> CultivationProgramRead:
    _require_program_manager(teacher)
    program_school, program_major, program_class_name = _resolve_cohort(teacher, school, major, class_name)
    existing = session.exec(
        select(CultivationProgram).where(
            CultivationProgram.school == program_school,
            CultivationProgram.major == program_major,
            CultivationProgram.class_name == program_class_name,
            CultivationProgram.teacher_uid != teacher.uid,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该学校、专业、班级已有已发布人培方案",
        )

    read = save_program_for_teacher(session, teacher, courses, program_school, program_major, program_class_name)
    program = session.get(CultivationProgram, read.program_id)
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人培方案不存在")
    program.published_at = datetime.now(timezone.utc)
    program.updated_at = program.published_at
    session.add(program)
    session.commit()
    session.refresh(program)
    return to_program_read(program, teacher)


def get_matched_program_for_student(session: Session, student: User) -> CultivationProgramRead | None:
    if not student.school.strip() or not student.major.strip() or not student.class_name.strip():
        return None
    program = session.exec(
        select(CultivationProgram).where(
            CultivationProgram.school == student.school.strip(),
            CultivationProgram.major == student.major.strip(),
            CultivationProgram.class_name == student.class_name.strip(),
            CultivationProgram.published_at.is_not(None),
        )
    ).first()
    if program is None:
        return None
    teacher = session.get(User, program.teacher_uid)
    return to_program_read(program, teacher)


def delete_program_for_cohort(session: Session, school: str, major: str, class_name: str) -> None:
    program = session.exec(
        select(CultivationProgram).where(
            CultivationProgram.school == school.strip(),
            CultivationProgram.major == major.strip(),
            CultivationProgram.class_name == class_name.strip(),
        )
    ).first()
    if program is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人培方案不存在")
    session.delete(program)
    session.commit()


def _require_program_manager(user: User) -> None:
    if user.role not in {"teacher", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理端权限")


def _resolve_cohort(
    user: User,
    school: str | None,
    major: str | None,
    class_name: str | None,
) -> tuple[str, str, str]:
    resolved_school = (school if school is not None else user.school).strip()
    resolved_major = (major if major is not None else user.major).strip()
    resolved_class_name = (class_name if class_name is not None else user.class_name).strip()
    if not resolved_school or not resolved_major or not resolved_class_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="学校、专业、班级不能为空")
    return resolved_school, resolved_major, resolved_class_name
