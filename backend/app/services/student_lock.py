"""Serialize short writes that change one student's learning state."""

from sqlmodel import Session, select

from app.models import User


def lock_student(session: Session, user_uid: str) -> None:
    session.exec(
        select(User)
        .where(User.uid == user_uid)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
