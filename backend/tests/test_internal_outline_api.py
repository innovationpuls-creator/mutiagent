from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import Session, select

from app.core.config import DEFAULT_INTERNAL_API_TOKEN
from app.database import DEMO_USER_UID
from app.main import create_app
from app.models import (
    KnowledgeSource,
    Textbook,
    TextbookSectionContent,
    UserCourseKnowledgeOutline,
)
from app.services.knowledge_base_service import (
    create_knowledge_source,
    publish_textbook,
    upsert_structured_textbook,
)
from app.services.outline_service import split_text_ranges
from tests.postgres import postgresql_test_url
from tests.test_learning_path_agent_contract import (
    _complete_profile,
    _confirmed_intake,
    _llm_learning_path_plan_payload,
)

INTERNAL = {"X-Internal-Token": DEFAULT_INTERNAL_API_TOKEN}
ALL = "__all_current_grade__"
LONG_TEXTBOOK = "textbook-1"


def _paragraphs(total_chars: int, size: int = 900) -> str:
    """Chinese-ish text made of paragraphs separated by blank lines."""
    paragraphs: list[str] = []
    length = 0
    index = 0
    while length < total_chars:
        index += 1
        body = (f"第{index}段讲解内容。" * 200)[:size]
        paragraphs.append(body)
        length += len(body) + 2
    return "\n\n".join(paragraphs)[:total_chars]


@pytest.fixture
def ctx(tmp_path: Path):
    url = postgresql_test_url(tmp_path, "internal-outline")
    client = TestClient(create_app(database_url=url))
    engine = create_engine(url)
    intake = _confirmed_intake()
    with Session(engine) as session:
        create_knowledge_source(
            session,
            KnowledgeSource(
                source_id="src-o",
                name="来源",
                base_url="https://example.test/s",
                status="enabled",
                source_kind="open_textbook",
                download_requirement="公开下载",
                ai_search_requirement="允许搜索",
                download_status="verified",
                parse_status="supported",
                license_review_status="approved",
                human_review_status="reviewed",
            ),
        )
        for index in range(1, 6):
            tid = f"textbook-{index}"
            sections = [
                (f"{tid}-section-1", "Complexity Analysis"),
                (f"{tid}-section-2", "Linear Structures"),
            ]
            tb = Textbook(
                textbook_id=tid,
                source_id="src-o",
                title=f"Data Structures {index}",
                original_title="Data Structures",
                language="en",
                translated_language="zh",
                description="数据结构",
                tags=["数据结构"],
                download_url="https://example.test/b.pdf",
                file_asset_url="https://example.test/b.md",
                outline={
                    "sections": [{"section_id": s, "title": t} for s, t in sections]
                },
                ingestion_status="completed",
                outline_review_status="approved",
                student_availability_status="draft",
            )
            rows = [
                TextbookSectionContent(
                    section_content_id=f"sc-{s}",
                    textbook_id=tid,
                    section_id=s,
                    parent_section_id=None,
                    order_index=order,
                    title=t,
                    original_title=t,
                    content_zh=_paragraphs(13000)
                    if tid == LONG_TEXTBOOK
                    else _paragraphs(3000),
                    content_char_count=0,
                )
                for order, (s, t) in enumerate(sections, start=1)
            ]
            upsert_structured_textbook(session, tb, rows)
            publish_textbook(session, tid)
    plan = _llm_learning_path_plan_payload([c["title"] for c in intake["courses"]])
    assembled = client.post(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3/assemble",
        headers=INTERNAL,
        json={
            "profile": _complete_profile(),
            "learning_topic": intake["learning_topic"],
            "plan": plan,
            "intake_courses": intake["courses"],
        },
    )
    assert assembled.status_code == 200, assembled.text
    path = assembled.json()["path_data"]
    client.put(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3",
        headers=INTERNAL,
        json={"learning_topic": intake["learning_topic"], "path_data": path},
    ).raise_for_status()
    return client, engine, path


def _context(client, course_id: str = ""):
    return client.post(
        f"/internal/students/{DEMO_USER_UID}/outline-source-context",
        headers=INTERNAL,
        json={"course_id": course_id},
    )


def _naming(skeleton_course: dict, **overrides) -> dict:
    texts = {
        s["section_id"]: {
            "title": f"第 {s['section_id']} 部分的中文讲解",
            "description": "用自然的中文说明这一部分要学什么。",
            "key_knowledge_points": ["中文知识点一", "中文知识点二"],
        }
        for s in skeleton_course["skeleton"]
    }
    texts.update(overrides)
    return {
        "personalization_summary": "按你的节奏安排的中文说明",
        "section_texts": texts,
    }


def _compose(client, course: dict, naming: dict):
    return client.post(
        f"/internal/students/{DEMO_USER_UID}/course-outlines/compose",
        headers=INTERNAL,
        json={"course": course, "naming": naming},
    )


def test_split_text_ranges_prefers_paragraph_boundaries() -> None:
    text = _paragraphs(13000)
    ranges = split_text_ranges(text)
    assert len(ranges) == 2
    assert ranges[0][0] == 0 and ranges[-1][1] == len(text)
    assert ranges[0][1] == ranges[1][0]
    assert all(hi - lo <= 8000 for lo, hi in ranges)
    # The cut lands right after a blank line (paragraph end).
    assert text[ranges[0][1] - 2 : ranges[0][1]] == "\n\n" or text[ranges[0][1]] in "第"
    assert split_text_ranges("x" * 8000) == [(0, 8000)]
    long_single = "字" * 20000  # no paragraph or sentence breaks at all
    parts = split_text_ranges(long_single)
    assert len(parts) == 3
    assert parts[0][0] == 0 and parts[-1][1] == 20000
    assert all(hi - lo <= 8000 for lo, hi in parts)
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:], strict=False))


def test_new_endpoints_require_token(ctx) -> None:
    client, _, _ = ctx
    for path in (
        "outline-source-context",
        "course-outlines/compose",
        "course-outlines/batch",
    ):
        res = client.post(f"/internal/students/{DEMO_USER_UID}/{path}", json={})
        assert res.status_code == 401


def test_long_section_is_split_with_exact_ranges(ctx) -> None:
    client, engine, _ = ctx
    body = _context(client, ALL).json()
    assert len(body["courses"]) == 5
    first = body["courses"][0]
    children = [s for s in first["skeleton"] if s["depth"] == 2]
    chunks = [s for s in children if s.get("source_chunk_total")]
    chunks = chunks[:2]
    assert [c["source_chunk_index"] for c in chunks] == [1, 2]
    assert all(c["source_chunk_total"] == 2 for c in chunks)
    assert all(c["source_content_chars"] <= 8000 for c in children)
    lo1, hi1 = chunks[0]["source_char_range"]
    lo2, hi2 = chunks[1]["source_char_range"]
    assert lo1 == 0 and hi1 == lo2 and hi2 == 13000
    assert chunks[0]["source_content_chars"] == hi1 - lo1
    assert [c["section_id"] for c in children][:2] == ["1.1", "1.2"]
    assert body["path_fingerprints"]["year_3"]
    # Untouched sections carry no chunk metadata.
    assert all(
        s.get("source_chunk_index") is None for s in body["courses"][1]["skeleton"]
    )
    with Session(engine) as session:
        assert session.exec(select(UserCourseKnowledgeOutline)).all() == []


def test_single_course_by_name_and_current_default(ctx) -> None:
    client, _, path = ctx
    current = path["current_learning_course"]["course_or_chapter_theme"]
    assert _context(client, "").json()["courses"][0]["course_name"] == current
    by_name = _context(client, "线性结构实践").json()["courses"]
    assert [c["course_name"] for c in by_name] == ["线性结构实践"]
    missing = _context(client, "不存在的课")
    assert missing.status_code == 422


def test_compose_rejects_english_internal_ids_and_missing_sections(ctx) -> None:
    client, _, _ = ctx
    course = _context(client, "").json()["courses"][0]
    good = _compose(client, course, _naming(course))
    assert good.status_code == 200, good.text
    outline = good.json()["outline"]
    assert outline["course_id"] == course["course_node_id"]
    assert outline["sections"][0]["title"].startswith("第 1")
    assert any(s["source_chunk_total"] == 2 for s in outline["sections"])
    assert outline["learning_sequence"]

    english = _naming(
        course,
        **{
            "1.1": {
                "title": "Complexity Analysis",
                "description": "d",
                "key_knowledge_points": ["k"],
            }
        },
    )
    res = _compose(client, course, english)
    assert res.status_code == 422 and "英文教材标题" in res.json()["detail"]

    internal = _naming(
        course,
        **{
            "1.1": {
                "title": "讲解 sec_1_1 的内容",
                "description": "中文说明",
                "key_knowledge_points": ["中文点"],
            }
        },
    )
    res = _compose(client, course, internal)
    assert res.status_code == 422 and "sec_1_1" in res.json()["detail"]

    partial = _naming(course)
    partial["section_texts"].pop("1.2")
    res = _compose(client, course, partial)
    assert res.status_code == 422 and "缺少章节文案" in res.json()["detail"]


def test_batch_save_is_fingerprinted_and_partial_friendly(ctx) -> None:
    client, engine, path = ctx
    context = _context(client, ALL).json()
    outlines = [
        _compose(client, course, _naming(course)).json()["outline"]
        for course in context["courses"][:4]
    ]  # a fifth course "failed" in the agent and is simply not sent
    saved = client.post(
        f"/internal/students/{DEMO_USER_UID}/course-outlines/batch",
        headers=INTERNAL,
        json={"path_fingerprints": context["path_fingerprints"], "outlines": outlines},
    )
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["saved_course_ids"]) == 4
    with Session(engine) as session:
        rows = session.exec(select(UserCourseKnowledgeOutline)).all()
        assert len(rows) == 4

    # The path changes while a generation is "in flight": the stale outline is refused.
    changed = dict(path)
    changed["grade_plans"] = {
        "year_3": {
            **path["grade_plans"]["year_3"],
            "course_nodes": [
                {**node, "course_goal": "全新的课程目标"}
                for node in path["grade_plans"]["year_3"]["course_nodes"]
            ],
        }
    }
    client.put(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3",
        headers=INTERNAL,
        json={"learning_topic": "数据结构", "path_data": changed},
    ).raise_for_status()
    stale = client.post(
        f"/internal/students/{DEMO_USER_UID}/course-outlines/batch",
        headers=INTERNAL,
        json={
            "path_fingerprints": context["path_fingerprints"],
            "outlines": outlines[:1],
        },
    )
    assert stale.status_code == 409
    assert "重新生成" in stale.json()["detail"]


def test_unpublished_textbook_blocks_before_anything_else(ctx) -> None:
    client, engine, _ = ctx
    with Session(engine) as session:
        for index in range(1, 6):
            book = session.get(Textbook, f"textbook-{index}")
            book.student_availability_status = "archived"
            session.add(book)
        session.commit()
    res = _context(client, "")
    assert res.status_code == 422
    assert "教材当前不可用" in res.json()["detail"]
    # The whole-year request fails the same way instead of half-working.
    assert _context(client, ALL).status_code == 422


def test_course_without_a_binding_is_refused_not_guessed(ctx) -> None:
    """No keyword matching picks a textbook for a course: the binding is explicit."""
    client, engine, path = ctx
    for node in path["grade_plans"]["year_3"]["course_nodes"]:
        node["source_outline_section_ids"] = []
    client.put(
        f"/internal/students/{DEMO_USER_UID}/learning-paths/year_3",
        headers=INTERNAL,
        json={"learning_topic": "数据结构", "path_data": path},
    ).raise_for_status()
    res = _context(client, "")
    assert res.status_code == 422
    assert "没有绑定教材小节" in res.json()["detail"]
