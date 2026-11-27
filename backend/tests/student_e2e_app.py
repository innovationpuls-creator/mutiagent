"""Isolated real-API browser fixture; only model grading is deterministic."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine

from app.core.security import hash_password
from app.main import create_app
from app.models import User, UserCourseKnowledgeOutline
from app.services.forest_service import generate_or_read_quiz
from tests.postgres import postgresql_test_url
from tests.test_forest_api import _seed_forest_data

_fixture_directory = TemporaryDirectory(prefix="onetree-student-e2e-")


def create_student_e2e_app():
    database_url = os.environ.get("ONETREE_STUDENT_E2E_DATABASE_URL", "")
    if not database_url or not (make_url(database_url).database or "").endswith(
        "_test"
    ):
        raise RuntimeError(
            "Set ONETREE_STUDENT_E2E_DATABASE_URL "
            "to a dedicated *_test PostgreSQL database"
        )
    os.environ["DATABASE_URL"] = database_url
    url = postgresql_test_url(Path(_fixture_directory.name), "student-browser-api")
    app = create_app(database_url=url)
    uid = _seed_forest_data(url)
    with Session(create_engine(url)) as session:
        user = session.get(User, uid)
        user.password_hash = hash_password("student-password")
        session.add(user)
        outline_row = session.get(UserCourseKnowledgeOutline, (uid, "year_3_course_2"))
        outline = dict(outline_row.outline_data)
        outline["sections"] = [
            {
                **section,
                "source_textbook_id": "",
                "source_textbook_title": "",
                "source_section_ids": [],
                "source_section_titles": [],
                "source_content_chars": 0,
            }
            for section in outline["sections"]
        ]
        outline["section_composed_markdowns"] = {
            section["section_id"]: {
                "section_id": section["section_id"],
                "parent_section_id": None,
                "title": section["title"],
                "markdown": section["description"],
                "blocks": [{"type": "markdown", "markdown": section["description"]}],
                "generated_at": "2026-10-10T00:00:00Z",
            }
            for section in outline["sections"]
        }
        outline_row.outline_data = outline
        session.add(outline_row)
        session.commit()
        generate_or_read_quiz(
            session,
            uid,
            "year_3_course_2",
            "1",
            [
                {
                    "question_id": "choice",
                    "type": "single_choice",
                    "prompt": "选择正确答案",
                    "options": [{"option_id": "A", "text": "正确答案"}],
                    "correct_option_id": "A",
                    "points": 100,
                }
            ],
            regenerate=False,
        )

    import app.api.forest as forest_api

    async def grade(*_args, **_kwargs):
        return {"score": 100, "question_results": [], "summary": "通过"}

    forest_api.get_worker_llm = lambda: object()
    forest_api.grade_quiz_answers = grade
    return app
