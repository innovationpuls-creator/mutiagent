import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import create_app
from app.models import (
    ChapterProgress,
    ChapterQuiz,
    ChapterQuizAttempt,
    ChapterWeakness,
    KnowledgeGap,
    Textbook,
    TextbookSectionContent,
    UserCourseKnowledgeOutline,
    UserYearLearningPath,
)
from app.report_schemas import EvidenceRequest, ReportNarrative
from app.services.growth_report_context import (
    build_report_context,
    read_report_evidence,
)
from app.services.growth_report_service import (
    _validate_numbers,
    generate_narrative,
    stream_growth_report,
    validate_narrative,
)
from tests.postgres import postgresql_test_url
from tests.test_canopy_api import _outline, _path, _register


class ModelDouble:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.prompts.append(messages)
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def report_db(tmp_path: Path):
    url = postgresql_test_url(tmp_path, "growth-report")
    client = TestClient(create_app(database_url=url))
    token, uid = _register(client, "report@example.com")
    _, other = _register(client, "other-report@example.com")
    engine = create_engine(url)
    with Session(engine) as session:
        session.add(
            UserYearLearningPath(user_uid=uid, grade_year="year_1", path_data=_path())
        )
        session.add(
            UserCourseKnowledgeOutline(
                user_uid=uid,
                course_id="year_1_course_1",
                grade_year="year_1",
                course_name="编程基础",
                outline_data=_outline("year_1_course_1", "year_1", "编程基础"),
            )
        )
        for owner, quiz_id in ((uid, "quiz-own"), (other, "quiz-secret")):
            session.add(
                ChapterQuiz(
                    quiz_id=quiz_id,
                    user_uid=owner,
                    course_node_id="year_1_course_1",
                    chapter_id="1",
                )
            )
        session.commit()
        now = datetime.now(timezone.utc)
        for index, score in enumerate((40, 85)):
            session.add(
                ChapterQuizAttempt(
                    attempt_id=f"own-{index}",
                    quiz_id="quiz-own",
                    user_uid=uid,
                    score=score,
                    passed=score > 70,
                    created_at=now + timedelta(seconds=index),
                    answers={"q1": {"text": "循环", "data_url": "SECRET_IMAGE_BYTES"}},
                    grading_result={"summary": "循环边界需要检查"},
                )
            )
        session.add(
            ChapterQuizAttempt(
                attempt_id="secret",
                quiz_id="quiz-secret",
                user_uid=other,
                score=99,
                answers={"secret": "PRIVATE"},
            )
        )
        session.add(
            ChapterProgress(
                user_uid=uid,
                course_node_id="year_1_course_1",
                chapter_id="1",
                state="passed",
                best_score=85,
            )
        )
        session.add(
            ChapterWeakness(
                weakness_id="weak",
                user_uid=uid,
                course_node_id="year_1_course_1",
                chapter_id="1",
                knowledge_point_id="loop",
                knowledge_point_name="循环",
                consumed=True,
            )
        )
        session.commit()
        yield session, uid, client, token
    engine.dispose()


def narrative():
    return {
        "overview": "你已开始通过测验检验学习成果。",
        "strengths": [
            {
                "title": "完成章节测验",
                "body": "已有通过测验的记录。",
                "evidence_ids": ["quiz:quiz-own"],
            }
        ],
        "improvements": [],
        "actions": [
            {
                "title": "复习循环",
                "body": "回到课程检查循环边界。",
                "check": "写出边界条件并完成练习。",
                "course_id": "year_1_course_1",
                "evidence_ids": ["path:year_1_course_1"],
            }
        ],
    }


def test_context_statistics_isolation_and_consumed_meaning(report_db):
    session, uid, _, _ = report_db
    context = build_report_context(session, uid)
    assert context.stats.model_dump() == {
        "passed_chapters": 1,
        "tested_chapters": 1,
        "attempts": 2,
    }
    assert "quiz:quiz-secret" not in context.evidence
    assert "weakness:weak" in context.evidence
    assert "不代表已经解决" in context.evidence["weakness:weak"].detail
    detail = read_report_evidence(
        session,
        uid,
        context,
        EvidenceRequest(tool="read_quiz", evidence_id="quiz:quiz-own"),
    )
    assert "SECRET_IMAGE_BYTES" not in detail and "PRIVATE" not in detail
    assert "循环边界" in detail
    with pytest.raises(ValueError):
        read_report_evidence(
            session,
            uid,
            context,
            EvidenceRequest(tool="read_quiz", evidence_id="quiz:quiz-secret"),
        )
    with pytest.raises(ValueError):
        read_report_evidence(
            session,
            uid,
            context,
            EvidenceRequest(tool="read_textbook", evidence_id="quiz:quiz-own"),
        )


def test_textbook_tool_is_published_bound_and_read_only(report_db):
    session, uid, _, _ = report_db
    outline = session.get(UserCourseKnowledgeOutline, (uid, "year_1_course_1"))
    data = dict(outline.outline_data)
    data["sections"] = [
        dict(
            data["sections"][0],
            source_textbook_id="book",
            source_section_ids=["section"],
            source_textbook_title="测试教材",
        )
    ]
    outline.outline_data = data
    session.add(outline)
    session.add(Textbook(textbook_id="book", source_id="source", title="测试教材"))
    session.add(
        TextbookSectionContent(
            section_content_id="content",
            textbook_id="book",
            section_id="section",
            title="循环",
            content_zh="循环的定义",
        )
    )
    session.commit()
    context = build_report_context(session, uid)
    request = EvidenceRequest(
        tool="read_textbook", evidence_id="textbook:year_1_course_1:1"
    )
    assert "未发布" in read_report_evidence(session, uid, context, request)
    book = session.get(Textbook, "book")
    book.student_availability_status = "published"
    session.add(book)
    session.commit()
    assert "循环的定义" in read_report_evidence(session, uid, context, request)
    assert not session.new and not session.dirty
    assert not session.exec(select(KnowledgeGap)).all()


@pytest.mark.parametrize("change", ["reference", "course", "strength"])
def test_rejects_invalid_report_links(report_db, change):
    session, uid, _, _ = report_db
    output = narrative()
    if change == "reference":
        output["actions"][0]["evidence_ids"] = ["quiz:quiz-secret"]
    elif change == "course":
        output["actions"][0]["course_id"] = "unknown-course"
    else:
        output["strengths"][0]["evidence_ids"] = ["path:year_1_course_1"]
    with pytest.raises(ValueError):
        validate_narrative(
            ReportNarrative.model_validate(output),
            build_report_context(session, uid),
            set(),
        )


def test_stream_and_authenticated_endpoint(report_db):
    _, _, client, token = report_db
    endpoint = "/api/branch/canopy/report/stream"
    assert client.post(endpoint).status_code == 401
    model = ModelDouble(
        [
            {"requests": [{"tool": "read_quiz", "evidence_id": "quiz:quiz-own"}]},
            narrative(),
        ]
    )
    with patch("app.api.branch.get_worker_llm", return_value=model):
        response = client.post(endpoint, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = response.text.strip().split("\n\n")
    assert [frame.splitlines()[0] for frame in frames] == [
        "event: report_stage",
        "event: report_stage",
        "event: report_stage",
        "event: report_completed",
    ]
    result = json.loads(frames[-1].split("data: ")[1])
    assert result["stats"]["attempts"] == 2
    assert len(result["evidence"]) == 2
    assert "循环边界" in str(model.prompts[-1])


def test_model_failure_is_error_not_fake_report(report_db):
    session, uid, _, _ = report_db

    async def collect():
        return [
            event
            async for event in stream_growth_report(
                session,
                uid,
                ModelDouble([RuntimeError("private model config")]),
            )
        ]

    events = asyncio.run(collect())
    assert "report_error" in events[-1]
    assert "private model config" not in events[-1]
    assert not any("report_completed" in event for event in events)


def test_no_learning_records_returns_honest_empty_report(report_db):
    session, _, client, _ = report_db
    _, uid = _register(client, "empty-report@example.com")
    output = {
        "overview": "尚无学习记录，学习表现待测验验证。",
        "strengths": [],
        "improvements": [],
        "actions": [],
    }

    async def collect():
        return [
            event
            async for event in stream_growth_report(
                session,
                uid,
                ModelDouble([{"requests": []}, output]),
            )
        ]

    events = asyncio.run(collect())
    assert "report_completed" in events[-1]
    assert "尚无测验作答记录" in events[-1]
    assert build_report_context(session, uid).stats.attempts == 0


def test_numeric_check_distinguishes_observations_from_proposed_exercises():
    output = narrative()
    output["actions"][0]["check"] = "完成5道练习，测试输入0和1。"
    _validate_numbers(ReportNarrative.model_validate(output), '{"attempts": 2}')
    output["overview"] = "你已完成999次测验。"
    with pytest.raises(ValueError, match="999"):
        _validate_numbers(ReportNarrative.model_validate(output), '{"attempts": 2}')


def test_invalid_model_reference_is_repaired_once(report_db):
    session, uid, _, _ = report_db
    invalid = narrative()
    invalid["strengths"][0]["evidence_ids"] = ["]quiz:quiz-own"]
    model = ModelDouble([invalid, narrative()])
    report = asyncio.run(
        generate_narrative(model, build_report_context(session, uid), {})
    )
    assert report.stats.attempts == 2
    assert len(model.prompts) == 2
    assert "]quiz:quiz-own" in str(model.prompts[-1])


def test_invalid_model_reference_stops_after_one_repair(report_db):
    session, uid, _, _ = report_db
    invalid = narrative()
    invalid["actions"][0]["course_id"] = "unknown-course"
    model = ModelDouble([invalid, invalid])
    with pytest.raises(ValueError):
        asyncio.run(generate_narrative(model, build_report_context(session, uid), {}))
    assert len(model.prompts) == 2
