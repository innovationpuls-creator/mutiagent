"""Forest, canopy and KB AI run in the TS gateway; Python brokers and persists."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import DEFAULT_INTERNAL_API_TOKEN
from app.main import create_app
from app.models import ChapterQuiz
from app.services.ai_gateway_client import AiGatewayError
from tests.postgres import postgresql_test_url
from tests.test_forest_api import _auth_headers, _seed_forest_data

INTERNAL = {"X-Internal-Token": DEFAULT_INTERNAL_API_TOKEN}
GENERATE = "/api/forest/courses/year_3_course_2/chapters/1/quiz/generate"

GOOD = [
    {
        "question_id": "q1",
        "type": "single_choice",
        "prompt": "题目",
        "options": [{"option_id": "A", "text": "甲"}, {"option_id": "B", "text": "乙"}],
        "correct_option_id": "A",
        "points": 100,
        "knowledge_point_ids": [],
    }
]


def _client(tmp_path: Path, name: str):
    url = postgresql_test_url(tmp_path, name)
    client = TestClient(create_app(database_url=url))
    return client, _seed_forest_data(url), url


def test_generation_sends_chapter_material_and_stores_the_gateway_questions(
    tmp_path: Path,
) -> None:
    client, uid, url = _client(tmp_path, "forest-gw-generate")
    sent: list[tuple[str, dict]] = []

    async def fake_gateway(path, body, timeout=240):
        sent.append((path, body))
        return {"questions": GOOD}

    with patch("app.api.forest.acall_gateway_ai", fake_gateway):
        response = client.post(
            GENERATE, json={"regenerate": False}, headers=_auth_headers(uid)
        )
    assert response.status_code == 200, response.text
    path, body = sent[0]
    assert path == "/internal/ai/quiz/generate"
    # The student's own uid selects the model; chapter material is attached.
    assert body["user_uid"] == uid and body["chapter_id"] == "1"
    assert "sections" in body and "knowledge_point_ids" in body
    assert response.json()["questions"][0]["question_id"] == "q1"


def test_gateway_failure_never_stores_filler_questions(tmp_path: Path) -> None:
    client, uid, url = _client(tmp_path, "forest-gw-fail")

    async def not_configured(*_a, **_k):
        raise AiGatewayError(428, "尚未配置可用的个人模型", "MODEL_NOT_CONFIGURED")

    with patch("app.api.forest.acall_gateway_ai", not_configured):
        response = client.post(
            GENERATE, json={"regenerate": False}, headers=_auth_headers(uid)
        )
    assert response.status_code == 428
    assert "模型" in response.json()["detail"]
    from sqlalchemy import create_engine

    with Session(create_engine(url)) as session:
        assert session.exec(select(ChapterQuiz)).all() == []


def test_internal_material_and_report_context(tmp_path: Path) -> None:
    client, uid, _ = _client(tmp_path, "forest-gw-internal")
    assert client.get(
        "/internal/forest/chapters/year_3_course_2/1/material",
        params={"user_uid": uid},
    ).status_code in (401, 403)
    material = client.get(
        "/internal/forest/chapters/year_3_course_2/1/material",
        params={"user_uid": uid},
        headers=INTERNAL,
    )
    assert material.status_code == 200, material.text
    assert material.json()["submitted"] is False
    assert material.json()["sections"]
    context = client.get(f"/internal/canopy/{uid}/report-context", headers=INTERNAL)
    assert context.status_code == 200
    assert "stats" in context.json()["summary"]
    bad = client.post(
        f"/internal/canopy/{uid}/report-evidence",
        json={"tool": "read_quiz", "evidence_id": "quiz:nope"},
        headers=INTERNAL,
    )
    assert bad.json()["ok"] is False
    invalid = client.post(
        f"/internal/canopy/{uid}/report-validate",
        json={
            "narrative": {
                "overview": "x",
                "strengths": [],
                "improvements": [],
                "actions": [],
            }
        },
        headers=INTERNAL,
    )
    assert invalid.status_code == 200 and "ok" in invalid.json()
