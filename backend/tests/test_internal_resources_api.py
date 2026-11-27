from __future__ import annotations

import pytest

from app.core.config import DEFAULT_INTERNAL_API_TOKEN
from app.database import DEMO_USER_UID
from app.orchestration.agents.course_resources import video as video_mod
from app.services import course_generation_status_service as lock_service
from tests.test_internal_outline_api import (  # noqa: F401
    _compose,
    _context,
    _naming,
    ctx,
)

INTERNAL = {"X-Internal-Token": DEFAULT_INTERNAL_API_TOKEN}
BASE = f"/internal/students/{DEMO_USER_UID}"

GOOD_MARKDOWN = """## 学习目标
- 能说明时间复杂度的含义，并能用大 O 记号估算一段循环代码的增长趋势。
- 能区分最好、最坏与平均情况，并结合教材中的例子解释差异。

## 核心概念
时间复杂度描述算法运行时间随输入规模增长的趋势，而不是某台机器上的具体耗时。教材强调先抓主要增长项，再忽略常数系数与低阶项。

## 步骤讲解
| 步骤 | 操作 | 说明 |
| --- | --- | --- |
| 1 | 找出基本操作 | 通常是循环体内最频繁执行的语句 |
| 2 | 统计执行次数 | 写出关于规模 n 的表达式 |
| 3 | 保留主要增长项 | 去掉常数与低阶项得到大 O |

<!-- video:id=video_1 -->

<!-- animation:id=anim_1 -->

## 练习任务
1. 写出单层循环、双层嵌套循环各自的时间复杂度并说明理由。
2. 给定一段二分查找代码，推导它的执行次数与复杂度。

## 检查标准
- [ ] 能用自己的话解释大 O 记号的含义
- [ ] 能正确判断单层与嵌套循环的复杂度
- [ ] 能指出最好与最坏情况的差异
- [ ] 能把教材例子迁移到新的代码片段
"""


@pytest.fixture
def outlined(ctx):  # noqa: F811
    client, engine, path = ctx
    context = _context(client, "__all_current_grade__").json()
    outlines = [
        _compose(client, course, _naming(course)).json()["outline"]
        for course in context["courses"]
    ]
    client.post(
        f"{BASE}/course-outlines/batch",
        headers=INTERNAL,
        json={"path_fingerprints": context["path_fingerprints"], "outlines": outlines},
    ).raise_for_status()
    course = context["courses"][0]
    leaves = [s for s in course["skeleton"] if s["depth"] == 2]
    return client, course["course_node_id"], [s["section_id"] for s in leaves]


@pytest.fixture(autouse=True)
def _clean_locks():
    lock_service._RUNNING.clear()
    yield
    lock_service._RUNNING.clear()


def _prepare(client, course_id, chapter="1", mode="generate"):
    return client.post(
        f"{BASE}/courses/{course_id}/chapters/{chapter}/generation-prepare",
        headers=INTERNAL,
        json={"mode": mode},
    )


def _section_url(course_id, section_id, tail):
    return f"{BASE}/courses/{course_id}/sections/{section_id}/{tail}"


def test_endpoints_require_token(outlined) -> None:
    client, course_id, _ = outlined
    res = client.post(
        f"{BASE}/courses/{course_id}/chapters/1/generation-prepare", json={}
    )
    assert res.status_code == 401


def test_prepare_gates_locks_and_releases(outlined) -> None:
    client, course_id, leaves = outlined
    other = _prepare(client, "year_3_course_2")
    assert other.json() == {
        "status": "refused",
        "message": "只能为当前课程生成教学内容。",
    }

    ready = _prepare(client, course_id).json()
    assert ready["status"] == "ready"
    assert ready["chapter_section_id"] == "1"
    assert [s["section_id"] for s in ready["sections"]] == [
        leaf for leaf in leaves if leaf.startswith("1.")
    ]
    assert all(s["checkpoints"] == {} for s in ready["sections"])

    # AC-6: a second request is refused while the first holds the chapter lock.
    busy = _prepare(client, course_id).json()
    assert busy == {"status": "busy", "message": "这一章正在生成。"}
    finish = client.post(
        f"{BASE}/courses/{course_id}/chapters/1/generation-finish",
        headers=INTERNAL,
        json={"succeeded_section_ids": []},
    )
    assert finish.json()["released"] is True
    assert _prepare(client, course_id).json()["status"] == "ready"

    # The default chapter reference resolves to the first generatable chapter.
    lock_service._RUNNING.clear()
    assert _prepare(client, course_id, "default").json()["chapter_section_id"] == "1"


def test_stale_lock_expires(outlined) -> None:
    client, course_id, _ = outlined
    assert _prepare(client, course_id).json()["status"] == "ready"
    for key, status in list(lock_service._RUNNING.items()):
        object.__setattr__(status, "started_at", status.started_at - 3600)
    assert _prepare(client, course_id).json()["status"] == "ready"


def test_markdown_prompt_uses_only_the_chunk_slice(outlined) -> None:
    client, course_id, leaves = outlined
    res = client.post(
        _section_url(course_id, leaves[0], "markdown/prompt"),
        headers=INTERNAL,
        json={"regeneration_focus": "多讲一些例题"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "多讲一些例题" in body["query"]
    assert "textbook_evidence_pack" in body["query"]
    assert "学习目标" in body["system_prompt"] + body["query"]
    # A split section (>8000 chars) used to make the evidence pack raise.
    assert "证据包超过" not in body["query"]


def test_markdown_validation_accepts_a_good_document_and_explains_bad_ones(
    outlined,
) -> None:
    client, course_id, leaves = outlined
    url = _section_url(course_id, leaves[0], "markdown/validate")
    bad = client.post(url, headers=INTERNAL, json={"raw_output": "只有一句话。"}).json()
    assert bad["ok"] is False and bad["issue"]
    good = client.post(url, headers=INTERNAL, json={"raw_output": GOOD_MARKDOWN}).json()
    assert good["ok"] is True, good
    value = good["value"]
    for heading in ("学习目标", "核心概念", "步骤讲解", "练习任务", "检查标准"):
        assert f"## {heading}" in value["markdown"]
    assert value["video_briefs"] and value["animation_briefs"]
    assert "<!-- video:id=" in value["markdown"]


def _save(client, course_id, section_id, phase, value=None, failure=""):
    return client.put(
        _section_url(course_id, section_id, "resources"),
        headers=INTERNAL,
        json={"phase": phase, "value": value, "failure": failure},
    )


def test_section_resources_merge_per_section_and_compose(outlined) -> None:
    client, course_id, leaves = outlined
    first, second = leaves[0], leaves[1]
    docs = {}
    for sid in (first, second):
        docs[sid] = client.post(
            _section_url(course_id, sid, "markdown/validate"),
            headers=INTERNAL,
            json={"raw_output": GOOD_MARKDOWN},
        ).json()["value"]
    assert _save(client, course_id, first, "markdown", docs[first]).status_code == 200
    assert _save(client, course_id, second, "markdown", docs[second]).status_code == 200

    # video: nothing found -> graceful degradation, saved as "unavailable" (AC-4).
    async def none_found(*_args, **_kwargs):
        return []

    original = video_mod._find_verified_video_from_search
    video_mod._find_verified_video_from_search = none_found
    try:
        found = client.post(
            _section_url(course_id, first, "video/search"), headers=INTERNAL
        ).json()
    finally:
        video_mod._find_verified_video_from_search = original
    assert found["status"] == "unavailable"
    assert _save(client, course_id, first, "video", found["value"]).status_code == 200

    prompt = client.post(
        _section_url(course_id, first, "animation/prompt"), headers=INTERNAL, json={}
    ).json()
    assert prompt["needed"] is True and prompt["query"]
    fallback = client.post(
        _section_url(course_id, first, "animation/validate"),
        headers=INTERNAL,
        json={"fallback": True},
    ).json()
    assert fallback["ok"] is True, fallback
    assert fallback["value"]["animations"][0]["html"]
    assert (
        _save(client, course_id, first, "animation", fallback["value"]).status_code
        == 200
    )

    composed = _save(client, course_id, first, "compose")
    assert composed.status_code == 200, composed.text

    # Only one of two sections is composed: a plain generate resumes (takes the lock).
    resumed = client.post(
        f"{BASE}/courses/{course_id}/chapters/1/generation-prepare",
        headers=INTERNAL,
        json={"mode": "generate"},
    ).json()
    assert resumed["status"] == "ready"
    client.post(
        f"{BASE}/courses/{course_id}/chapters/1/generation-finish",
        headers=INTERNAL,
        json={"succeeded_section_ids": []},
    ).raise_for_status()
    _save(client, course_id, second, "video", found["value"]).raise_for_status()
    _save(client, course_id, second, "animation", fallback["value"]).raise_for_status()
    _save(client, course_id, second, "compose").raise_for_status()
    detail = client.post(
        f"{BASE}/courses/{course_id}/chapters/1/generation-prepare",
        headers=INTERNAL,
        json={"mode": "generate"},
    ).json()
    # The whole chapter is composed => regenerate needs a focus; no lock is taken.
    assert detail["status"] == "needs_focus"
    by_id = {
        s["section_id"]: s
        for s in _prepare(client, course_id, mode="regenerate").json()["sections"]
    }
    assert by_id[first]["checkpoints"] == {
        "markdown": "completed",
        "video": "completed",
        "animation": "completed",
        "compose": "completed",
    }
    assert by_id[second]["checkpoints"]["compose"] == "completed"
    assert by_id[first]["has_composed"] and by_id[second]["has_composed"]


def test_failed_phase_records_a_retryable_error_and_keeps_other_phases(
    outlined,
) -> None:
    client, course_id, leaves = outlined
    sid = leaves[0]
    doc = client.post(
        _section_url(course_id, sid, "markdown/validate"),
        headers=INTERNAL,
        json={"raw_output": GOOD_MARKDOWN},
    ).json()["value"]
    _save(client, course_id, sid, "markdown", doc).raise_for_status()
    _save(
        client, course_id, sid, "animation", failure="HTML 动画未生成。"
    ).raise_for_status()
    sections = _prepare(client, course_id).json()["sections"]
    checkpoints = next(s for s in sections if s["section_id"] == sid)["checkpoints"]
    assert checkpoints == {"markdown": "completed", "animation": "failed"}
    # compose without a markdown/animation prerequisite is refused cleanly.
    refused = _save(client, course_id, leaves[1], "compose")
    assert refused.status_code == 422


def test_video_found_is_saved_as_available_and_composed(outlined, monkeypatch) -> None:
    """AC-4 (found path): a verified Bilibili hit becomes an `available` video block."""

    class _Source:
        url = "https://www.bilibili.com/video/BV1xx411c7mD"

    async def fake_search(*_args, **_kwargs):
        return [_Source()]

    async def fake_verify(_url):
        return {"status": "ok", "title": "时间复杂度入门讲解"}

    monkeypatch.setattr(video_mod, "_search_aliyun_bilibili_sources", fake_search)
    monkeypatch.setattr(video_mod, "_verify_bilibili_video_metadata", fake_verify)

    client, course_id, leaves = outlined
    sid = leaves[0]
    doc = client.post(
        _section_url(course_id, sid, "markdown/validate"),
        headers=INTERNAL,
        json={"raw_output": GOOD_MARKDOWN},
    ).json()["value"]
    _save(client, course_id, sid, "markdown", doc).raise_for_status()
    found = client.post(
        _section_url(course_id, sid, "video/search"), headers=INTERNAL
    ).json()
    assert found["status"] == "available", found
    assert found["value"]["videos"][0]["url"].startswith("https://www.bilibili.com/")
    _save(client, course_id, sid, "video", found["value"]).raise_for_status()
    anim = client.post(
        _section_url(course_id, sid, "animation/validate"),
        headers=INTERNAL,
        json={"fallback": True},
    ).json()["value"]
    _save(client, course_id, sid, "animation", anim).raise_for_status()
    assert _save(client, course_id, sid, "compose").status_code == 200


def test_unpublished_source_textbook_blocks_generation(outlined, ctx) -> None:  # noqa: F811
    """The resource gate mirrors the outline gate: an unpublished source book
    refuses generation instead of writing content from it."""
    from sqlmodel import Session

    from app.models import Textbook

    client, course_id, _ = outlined
    _, engine, _ = ctx
    with Session(engine) as session:
        for index in range(1, 6):
            book = session.get(Textbook, f"textbook-{index}")
            book.student_availability_status = "archived"
            session.add(book)
        session.commit()
    refused = _prepare(client, course_id).json()
    assert refused["status"] == "refused"
    assert refused["message"] == "教材未发布。"
