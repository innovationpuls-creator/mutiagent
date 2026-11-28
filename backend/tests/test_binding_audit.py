from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import Textbook, User, UserYearLearningPath
from app.schema_upgrades import run_schema_upgrades
from app.services.binding_audit import audit_course_bindings
from tests.postgres import postgresql_test_url


def _course(course_id: str, **binding) -> dict:
    return {
        "course_node_id": course_id,
        "course_or_chapter_theme": f"课程{course_id}",
        **binding,
    }


def test_audit_reports_only_unusable_courses(tmp_path: Path) -> None:
    engine = create_engine(postgresql_test_url(tmp_path, "binding-audit"))
    run_schema_upgrades(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(uid="u1", username="u1", identifier="u1@example.test"))
        session.add(
            Textbook(
                textbook_id="tb-ok",
                source_id="s",
                title="T",
                student_availability_status="published",
            )
        )
        session.add(
            Textbook(
                textbook_id="tb-draft",
                source_id="s",
                title="D",
                student_availability_status="draft",
            )
        )
        session.add(
            UserYearLearningPath(
                user_uid="u1",
                grade_year="year_3",
                path_data={
                    "grade_plans": {
                        "year_3": {
                            "course_nodes": [
                                _course(
                                    "good",
                                    source_textbook_id="tb-ok",
                                    source_outline_section_ids=["a"],
                                ),
                                _course("none"),
                                _course(
                                    "nosections",
                                    source_textbook_id="tb-ok",
                                    source_outline_section_ids=[],
                                ),
                                _course(
                                    "unpublished",
                                    source_textbook_id="tb-draft",
                                    source_outline_section_ids=["a"],
                                ),
                            ]
                        }
                    }
                },
            )
        )
        session.commit()
        problems = audit_course_bindings(session)

    assert {p["course_node_id"]: p["reason"] for p in problems} == {
        "none": "没有教材绑定",
        "nosections": "没有绑定教材小节",
        "unpublished": "绑定的教材已不是已发布状态",
    }
    assert all(p["user_uid"] == "u1" for p in problems)
