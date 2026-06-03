from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import User
from app.services.learning_path_service import get_year_learning_path, upsert_year_learning_path


def build_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'learning-path.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(User(uid="user-1", username="路径用户", identifier="learning-path@example.com"))
    session.commit()
    return session


def test_upsert_year_learning_path_saves_latest_path_data(tmp_path: Path) -> None:
    session = build_session(tmp_path)
    first = {"grade_year": "year_1", "courses": []}
    second = {"grade_year": "year_1", "courses": [{"course_id": "year_1_course_1", "course_name": "Python"}]}

    upsert_year_learning_path(session, "user-1", "year_1", "Python", first)
    saved = upsert_year_learning_path(session, "user-1", "year_1", "Python进阶", second)
    loaded = get_year_learning_path(session, "user-1", "year_1")

    assert saved.path_data == second
    assert loaded is not None
    assert loaded["courses"][0]["course_name"] == "Python"
