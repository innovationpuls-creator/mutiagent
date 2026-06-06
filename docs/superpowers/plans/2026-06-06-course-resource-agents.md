# Course Resource Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build chat-triggered section-level course resource generation agents that create Markdown documents, video links with covers, and HTML animations, then persist all resources into `UserCourseKnowledgeOutline.outline_data`.

**Architecture:** Keep the existing LangGraph orchestration and database table. Add three worker nodes after `course_knowledge_agent`: `section_markdown_agent`, `section_video_search_agent`, and `section_html_animation_agent`. Resources are keyed by exact `section_id` under `section_markdowns`, `section_video_links`, and `section_html_animations`; `1.1`, `1.2`, and `1.3` get separate resources when the user asks for the first chapter.

**Tech Stack:** FastAPI, LangGraph, LangChain `ChatOpenAI.with_structured_output`, SQLModel, pytest, existing `UserCourseKnowledgeOutline.outline_data` JSON storage.

---

## File Structure

- Create `backend/app/orchestration/agents/course_resources.py`
  - Section selection helpers.
  - Shared persistence helper that merges resource fields into existing `outline_data`.
  - `run_section_markdown_agent`, `run_section_video_search_agent`, `run_section_html_animation_agent`.
  - `create_section_markdown_agent_node`, `create_section_video_search_agent_node`, `create_section_html_animation_agent_node`.
- Modify `backend/app/orchestration/agents/models.py`
  - Add Pydantic output models for section Markdown, videos, and HTML animations.
- Modify `backend/app/orchestration/agents/prompts.py`
  - Add three system prompts for the new agents.
- Modify `backend/app/orchestration/llm.py`
  - Add `get_search_worker_llm()` that preserves thinking mode and adds `enable_search`.
- Modify `backend/app/orchestration/state.py`
  - Add `course_resource_plan` and `course_resource_result`.
- Modify `backend/app/orchestration/agents/supervisor.py`
  - Add three tools and force-call support for `section_markdown_agent`.
- Modify `backend/app/orchestration/rule_engine.py`
  - Add agent constants and teaching-content intent detection.
- Modify `backend/app/orchestration/graph.py`
  - Add nodes, labels, worker routing, and fixed resource pipeline.
- Modify `backend/app/api/orchestration.py`
  - Return existing resources from database when current course content is requested and resources already exist.
- Create `backend/tests/test_course_resource_agent_contract.py`
  - Unit and integration-style contract tests for all three agents and persistence.
- Modify `backend/tests/test_orchestration_llm.py`
  - Test the search LLM factory and graph worker LLM wiring.
- Modify `backend/tests/test_rule_engine.py`
  - Test teaching-content intent and force-call gating.
- Modify `backend/tests/test_supervisor_force_call.py`
  - Test forced `section_markdown_agent` tool call args.
- Modify `backend/tests/test_orchestration_api.py`
  - Test chat request persists section-level resources and returns completion text.

## Task 1: Models And Resource Helpers

**Files:**
- Modify: `backend/app/orchestration/agents/models.py`
- Create: `backend/app/orchestration/agents/course_resources.py`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Write failing tests for section selection, merge persistence, and cover fallback**

Create `backend/tests/test_course_resource_agent_contract.py` with these initial tests:

```python
from __future__ import annotations

from datetime import datetime

from app.orchestration.agents.course_resources import (
    _fallback_cover_data_url,
    _merge_course_resource_data,
    _target_sections_for_scope,
)


def _outline() -> dict:
    return {
        "course_id": "year_3_course_1",
        "course_name": "AI 应用开发",
        "grade_year": "year_3",
        "personalization_summary": "先完成需求拆解，再进入接口接入。",
        "sections": [
            {
                "section_id": "1",
                "parent_section_id": None,
                "depth": 1,
                "title": "需求拆解",
                "order_index": 1,
                "description": "确认功能边界与验收标准。",
                "key_knowledge_points": ["功能边界", "验收标准"],
            },
            {
                "section_id": "1.1",
                "parent_section_id": "1",
                "depth": 2,
                "title": "学习目标",
                "order_index": 2,
                "description": "明确本节学习目标。",
                "key_knowledge_points": ["功能边界"],
            },
            {
                "section_id": "1.2",
                "parent_section_id": "1",
                "depth": 2,
                "title": "任务拆解",
                "order_index": 3,
                "description": "把目标拆成任务。",
                "key_knowledge_points": ["任务拆分"],
            },
            {
                "section_id": "1.3",
                "parent_section_id": "1",
                "depth": 2,
                "title": "检查点",
                "order_index": 4,
                "description": "确认完成标准。",
                "key_knowledge_points": ["验收标准"],
            },
            {
                "section_id": "2",
                "parent_section_id": None,
                "depth": 1,
                "title": "接口接入",
                "order_index": 5,
                "description": "接入 LLM API。",
                "key_knowledge_points": ["API 调用"],
            },
            {
                "section_id": "2.1",
                "parent_section_id": "2",
                "depth": 2,
                "title": "学习目标",
                "order_index": 6,
                "description": "掌握接口接入目标。",
                "key_knowledge_points": ["API 调用"],
            },
        ],
        "learning_sequence": ["第一章：需求拆解", "第二章：接口接入"],
        "total_estimated_hours": "8 小时",
    }


def test_target_sections_for_chapter_scope_expands_child_sections() -> None:
    targets = _target_sections_for_scope(_outline(), "1", "chapter_sections")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3"]


def test_target_sections_default_first_chapter_uses_child_sections_not_parent() -> None:
    targets = _target_sections_for_scope(_outline(), "", "default_first_chapter")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3"]


def test_target_sections_course_scope_uses_all_non_root_sections() -> None:
    targets = _target_sections_for_scope(_outline(), "", "course_sections")

    assert [section["section_id"] for section in targets] == ["1.1", "1.2", "1.3", "2.1"]


def test_merge_course_resource_data_preserves_outline_fields() -> None:
    outline = _outline()
    merged = _merge_course_resource_data(
        outline,
        "section_markdowns",
        {
            "1.1": {
                "section_id": "1.1",
                "parent_section_id": "1",
                "title": "学习目标",
                "markdown": "# 学习目标",
                "animation_briefs": [],
                "generated_at": "2026-06-06T00:00:00Z",
            }
        },
    )

    assert merged["course_id"] == "year_3_course_1"
    assert merged["sections"] == outline["sections"]
    assert merged["section_markdowns"]["1.1"]["markdown"] == "# 学习目标"


def test_fallback_cover_data_url_is_stable_svg_data_url() -> None:
    value = _fallback_cover_data_url("学习目标")

    assert value.startswith("data:image/svg+xml;utf8,")
    assert "学习目标" in value
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py -q
```

Expected: FAIL because `app.orchestration.agents.course_resources` does not exist.

- [ ] **Step 3: Add Pydantic models**

Modify `backend/app/orchestration/agents/models.py` by appending these models after `CourseKnowledgeDraftOutput`:

```python

# ── Section Resource Agents ──────────────────────────────────────────────

class SectionAnimationBriefOutput(BaseModel):
    animation_id: str = Field(description="动画 ID")
    title: str = Field(description="动画标题")
    concept: str = Field(description="需要动画解释的概念")
    placement_hint: str = Field(default="", description="建议插入位置")


class SectionMarkdownOutput(BaseModel):
    section_id: str = Field(description="小节 ID")
    parent_section_id: str | None = Field(description="父章节 ID")
    title: str = Field(description="小节标题")
    markdown: str = Field(description="完整 Markdown 教学内容")
    animation_briefs: list[SectionAnimationBriefOutput] = Field(default_factory=list)


class SectionVideoItemOutput(BaseModel):
    title: str = Field(description="视频标题")
    url: str = Field(description="视频页面 URL")
    cover_url: str = Field(default="", description="视频封面 URL")
    source: str = Field(default="", description="视频来源站点")


class SectionVideoSearchOutput(BaseModel):
    section_id: str = Field(description="小节 ID")
    query: str = Field(description="实际搜索查询")
    videos: list[SectionVideoItemOutput] = Field(default_factory=list)


class SectionHtmlAnimationItemOutput(BaseModel):
    animation_id: str = Field(description="动画 ID")
    title: str = Field(description="动画标题")
    html: str = Field(description="可嵌入 HTML 片段")


class SectionHtmlAnimationOutput(BaseModel):
    section_id: str = Field(description="小节 ID")
    animations: list[SectionHtmlAnimationItemOutput] = Field(default_factory=list)
```

- [ ] **Step 4: Implement helper module**

Create `backend/app/orchestration/agents/course_resources.py` with:

```python
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _sections(outline: dict) -> list[dict]:
    value = outline.get("sections")
    if not isinstance(value, list):
        return []
    return [section for section in value if isinstance(section, dict)]


def _section_by_id(outline: dict, section_id: str) -> dict | None:
    for section in _sections(outline):
        if section.get("section_id") == section_id:
            return section
    return None


def _target_sections_for_scope(outline: dict, section_id: str, scope: str) -> list[dict]:
    sections = sorted(_sections(outline), key=lambda item: int(item.get("order_index", 0)))
    if scope == "single_section":
        section = _section_by_id(outline, section_id)
        if not section or int(section.get("depth", 1)) <= 1:
            raise ValueError("指定小节无法定位。")
        return [section]
    if scope == "chapter_sections":
        parent = _section_by_id(outline, section_id)
        if not parent or int(parent.get("depth", 1)) != 1:
            raise ValueError("指定章节无法定位。")
        return [
            section for section in sections
            if section.get("parent_section_id") == section_id and int(section.get("depth", 1)) > 1
        ]
    if scope == "course_sections":
        return [section for section in sections if int(section.get("depth", 1)) > 1]

    root_sections = [section for section in sections if int(section.get("depth", 1)) == 1]
    if not root_sections:
        raise ValueError("课程大纲缺少一级章节。")
    first_root_id = _clean_text(root_sections[0].get("section_id"))
    return [
        section for section in sections
        if section.get("parent_section_id") == first_root_id and int(section.get("depth", 1)) > 1
    ]


def _parent_section(outline: dict, section: dict) -> dict | None:
    parent_id = section.get("parent_section_id")
    if not isinstance(parent_id, str):
        return None
    return _section_by_id(outline, parent_id)


def _merge_course_resource_data(outline: dict, field_name: str, values: dict[str, dict]) -> dict:
    merged = deepcopy(outline)
    existing = merged.get(field_name)
    if not isinstance(existing, dict):
        existing = {}
    existing.update(values)
    merged[field_name] = existing
    return merged


def _fallback_cover_data_url(title: str) -> str:
    safe_title = _clean_text(title) or "课程视频"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
        "<rect width='640' height='360' fill='oklch(22% 0.04 220)'/>"
        "<circle cx='320' cy='150' r='54' fill='oklch(70% 0.12 190)' opacity='0.85'/>"
        "<polygon points='305,122 305,178 352,150' fill='oklch(96% 0.02 90)'/>"
        f"<text x='320' y='255' text-anchor='middle' font-size='28' fill='oklch(92% 0.02 90)'>{safe_title}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg, safe="/:=;,%#?&'() ")
```

- [ ] **Step 5: Run tests to verify helper behavior passes**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_target_sections_for_chapter_scope_expands_child_sections tests/test_course_resource_agent_contract.py::test_target_sections_default_first_chapter_uses_child_sections_not_parent tests/test_course_resource_agent_contract.py::test_target_sections_course_scope_uses_all_non_root_sections tests/test_course_resource_agent_contract.py::test_merge_course_resource_data_preserves_outline_fields tests/test_course_resource_agent_contract.py::test_fallback_cover_data_url_is_stable_svg_data_url -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/orchestration/agents/models.py backend/app/orchestration/agents/course_resources.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: add course resource helper contracts"
```

## Task 2: Section Markdown Agent

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources.py`
- Modify: `backend/app/orchestration/agents/prompts.py`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing test for Markdown agent**

Append this test to `backend/tests/test_course_resource_agent_contract.py`:

```python
import asyncio

from sqlmodel import Session

from app.database import build_engine, init_db, set_engine
from app.models import User, UserCourseKnowledgeOutline
from app.orchestration.agents.course_resources import run_section_markdown_agent
from app.orchestration.agents.models import SectionMarkdownOutput


def test_run_section_markdown_agent_writes_each_first_chapter_child_section(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class MarkdownChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            section_id = "1.1" if "学习目标" in payload["query"] else "1.2" if "任务拆解" in payload["query"] else "1.3"
            title = "学习目标" if section_id == "1.1" else "任务拆解" if section_id == "1.2" else "检查点"
            return SectionMarkdownOutput(
                section_id=section_id,
                parent_section_id="1",
                title=title,
                markdown=f"# {title}\n\n完整教学内容",
                animation_briefs=[],
            )

    class MarkdownPrompt:
        def __or__(self, _other):
            return MarkdownChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return MarkdownPrompt()

    captured = {"schema": None, "queries": []}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-markdown.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=_outline(),
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module
    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_markdown_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": _outline(),
                    "messages": [],
                },
                RecordingLlm(),
                {"course_id": "year_3_course_1", "section_id": "1", "scope": "chapter_sections"},
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is SectionMarkdownOutput
    assert len(captured["queries"]) == 3
    assert result["course_resource_plan"]["target_section_ids"] == ["1.1", "1.2", "1.3"]
    assert set(result["course_knowledge"]["section_markdowns"]) == {"1.1", "1.2", "1.3"}
    assert "1" not in result["course_knowledge"]["section_markdowns"]
    with Session(engine) as session:
        row = session.get(UserCourseKnowledgeOutline, ("user-1", "year_3_course_1"))
    assert row is not None
    assert set(row.outline_data["section_markdowns"]) == {"1.1", "1.2", "1.3"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_run_section_markdown_agent_writes_each_first_chapter_child_section -q
```

Expected: FAIL because `run_section_markdown_agent` is missing.

- [ ] **Step 3: Add Markdown prompt**

Append to `backend/app/orchestration/agents/prompts.py`:

```python

SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT = """\
你是课程教学内容生成智能体。你只为输入里的单个小节生成完整 Markdown 教学文档。

## 输出要求
- 必须输出 JSON，且只能输出 JSON 对象。
- section_id、parent_section_id、title 必须与输入小节一致。
- markdown 必须是完整教学内容，包含标题、学习目标、核心概念、步骤讲解、练习任务、检查标准。
- animation_briefs 只列出确实需要 HTML 动画解释的内容；不需要动画时输出空列表。
- 不要为一级大章生成文档，只处理输入中的二级或更深小节。
"""
```

- [ ] **Step 4: Implement Markdown agent functions**

Extend `backend/app/orchestration/agents/course_resources.py` with imports and functions:

```python
import asyncio
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlmodel import Session

from app.database import get_engine
from app.orchestration.agents.models import SectionMarkdownOutput
from app.orchestration.agents.prompts import SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
from app.orchestration.agents.utils import extract_last_tool_call_args, extract_last_tool_call_id
from app.orchestration.state import OrchestrationState
from app.services.course_knowledge_service import upsert_user_course_knowledge_outline

logger = logging.getLogger(__name__)

_RESOURCE_TIMEOUT_SECONDS = 60.0


def _tool_args(state: OrchestrationState, explicit_args: dict | None) -> dict:
    return explicit_args if explicit_args is not None else extract_last_tool_call_args(state)


def _markdown_input(outline: dict, section: dict) -> str:
    parent = _parent_section(outline, section)
    payload = {
        "course": {
            "course_id": outline.get("course_id", ""),
            "course_name": outline.get("course_name", ""),
            "grade_year": outline.get("grade_year", ""),
            "personalization_summary": outline.get("personalization_summary", ""),
        },
        "parent_section": parent or {},
        "section": section,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _persist_outline(user_id: str, outline: dict) -> None:
    with Session(get_engine()) as db_session:
        upsert_user_course_knowledge_outline(db_session, user_id, outline)


async def run_section_markdown_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    args = _tool_args(state, explicit_args)
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}

    scope = _clean_text(args.get("scope")) or "default_first_chapter"
    section_id = _clean_text(args.get("section_id"))
    try:
        targets = _target_sections_for_scope(outline, section_id, scope)
    except ValueError as exc:
        return {"error": str(exc), "hard_error": True}

    structured_llm = llm.with_structured_output(SectionMarkdownOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm

    resources: dict[str, dict] = {}
    for section in targets:
        try:
            generated = await asyncio.wait_for(
                chain.ainvoke({"query": _markdown_input(outline, section)}),
                timeout=_RESOURCE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Section markdown generation failed: %s", exc)
            return {"error": "小节教学文档生成失败，请稍后重试。", "hard_error": True}

        payload = generated.model_dump() if hasattr(generated, "model_dump") else dict(generated)
        sid = _clean_text(section.get("section_id"))
        resources[sid] = {
            "section_id": sid,
            "parent_section_id": section.get("parent_section_id"),
            "title": _clean_text(payload.get("title")) or _clean_text(section.get("title")),
            "markdown": _clean_text(payload.get("markdown")),
            "animation_briefs": payload.get("animation_briefs") if isinstance(payload.get("animation_briefs"), list) else [],
            "generated_at": _now_iso(),
        }

    updated_outline = _merge_course_resource_data(outline, "section_markdowns", resources)
    _persist_outline(str(state["user_id"]), updated_outline)
    target_ids = list(resources.keys())
    return {
        "course_knowledge": updated_outline,
        "course_resource_plan": {
            "course_id": updated_outline.get("course_id", ""),
            "scope": scope,
            "target_section_ids": target_ids,
            "markdown_section_ids": target_ids,
            "video_section_ids": [],
            "animation_section_ids": [],
        },
    }


def create_section_markdown_agent_node(llm: BaseChatModel):
    async def section_markdown_node(state: OrchestrationState) -> dict:
        agent_result = await run_section_markdown_agent(state, llm)
        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )
        result = {"messages": [tool_message]}
        for key in ("course_knowledge", "course_resource_plan", "response"):
            if agent_result.get(key) is not None:
                result[key] = agent_result[key]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result

    return section_markdown_node
```

- [ ] **Step 5: Run Markdown tests**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_run_section_markdown_agent_writes_each_first_chapter_child_section -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/orchestration/agents/course_resources.py backend/app/orchestration/agents/prompts.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: add section markdown agent"
```

## Task 3: Search LLM Factory And Video Agent

**Files:**
- Modify: `backend/app/orchestration/llm.py`
- Modify: `backend/app/orchestration/agents/course_resources.py`
- Modify: `backend/app/orchestration/agents/prompts.py`
- Modify: `backend/tests/test_orchestration_llm.py`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing LLM factory test**

Append to `backend/tests/test_orchestration_llm.py`:

```python
def test_search_worker_llm_enables_search(monkeypatch) -> None:
    import app.orchestration.llm as llm_module

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(llm_module, "ChatOpenAI", FakeChatOpenAI)
    llm_module._search_worker_llm = None

    search_worker = llm_module.get_search_worker_llm()

    extra_body = search_worker.kwargs["model_kwargs"]["extra_body"]
    assert extra_body["enable_thinking"] is True
    assert extra_body["enable_search"] is True
    assert extra_body["search_options"]["forced_search"] is True
    assert extra_body["search_options"]["search_strategy"] == "turbo"
```

- [ ] **Step 2: Run LLM factory test to verify it fails**

Run:

```bash
cd backend && uv run pytest tests/test_orchestration_llm.py::test_search_worker_llm_enables_search -q
```

Expected: FAIL because `get_search_worker_llm` does not exist.

- [ ] **Step 3: Implement search LLM factory**

Modify `backend/app/orchestration/llm.py`:

```python
_search_worker_llm: ChatOpenAI | None = None


def _build(
    timeout: int,
    *,
    enable_thinking: bool,
    enable_search: bool = False,
    max_retries: int = 1,
) -> ChatOpenAI:
    extra_body = {"enable_thinking": enable_thinking}
    if enable_search:
        extra_body.update({
            "enable_search": True,
            "search_options": {
                "forced_search": True,
                "search_strategy": "turbo",
            },
        })
    return ChatOpenAI(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        model=_MODEL,
        temperature=0.7,
        timeout=timeout,
        max_retries=max_retries,
        streaming=True,
        model_kwargs={"extra_body": extra_body},
    )


def get_search_worker_llm() -> ChatOpenAI:
    global _search_worker_llm
    if _search_worker_llm is None:
        _search_worker_llm = _build(_WORKER_TIMEOUT, enable_thinking=True, enable_search=True)
        logger.info("Search worker LLM initialized (timeout=%ds)", _WORKER_TIMEOUT)
    return _search_worker_llm
```

- [ ] **Step 4: Run LLM factory test**

Run:

```bash
cd backend && uv run pytest tests/test_orchestration_llm.py::test_search_worker_llm_enables_search -q
```

Expected: PASS.

- [ ] **Step 5: Add failing video agent test**

Append to `backend/tests/test_course_resource_agent_contract.py`:

```python
from app.orchestration.agents.course_resources import run_section_video_search_agent
from app.orchestration.agents.models import SectionVideoSearchOutput


def test_run_section_video_search_agent_writes_url_and_fallback_cover(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class VideoChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionVideoSearchOutput(
                section_id="1.1",
                query="AI 应用开发 学习目标 视频教程",
                videos=[
                    {
                        "title": "学习目标视频",
                        "url": "https://example.com/video",
                        "cover_url": "",
                        "source": "example.com",
                    }
                ],
            )

    class VideoPrompt:
        def __or__(self, _other):
            return VideoChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return VideoPrompt()

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "animation_briefs": [],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": []}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-video.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module
    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_video_search_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is SectionVideoSearchOutput
    videos = result["course_knowledge"]["section_video_links"]["1.1"]["videos"]
    assert videos[0]["url"] == "https://example.com/video"
    assert videos[0]["cover_status"] == "fallback"
    assert videos[0]["cover_url"].startswith("data:image/svg+xml;utf8,")
```

- [ ] **Step 6: Run video test to verify it fails**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_run_section_video_search_agent_writes_url_and_fallback_cover -q
```

Expected: FAIL because `run_section_video_search_agent` is missing.

- [ ] **Step 7: Add video prompt**

Append to `backend/app/orchestration/agents/prompts.py`:

```python

SECTION_VIDEO_SEARCH_AGENT_SYSTEM_PROMPT = """\
你是课程视频搜索智能体。你必须基于输入的小节教学内容联网搜索视频资源。

## 输出要求
- 必须输出 JSON，且只能输出 JSON 对象。
- 每条 videos 必须包含 title、url、cover_url、source。
- url 必须是可直接打开的视频页面 URL。
- cover_url 拿不到时输出空字符串，后端会生成降级封面。
- 只返回与输入小节相关的视频，不返回泛泛的课程首页。
"""
```

- [ ] **Step 8: Implement video agent**

Extend `backend/app/orchestration/agents/course_resources.py`:

```python
from app.orchestration.agents.models import SectionVideoSearchOutput
from app.orchestration.agents.prompts import SECTION_VIDEO_SEARCH_AGENT_SYSTEM_PROMPT


def _section_title(outline: dict, section_id: str) -> str:
    section = _section_by_id(outline, section_id)
    return _clean_text(section.get("title")) if section else section_id


def _video_input(outline: dict, section_id: str) -> str:
    mark = outline.get("section_markdowns", {}).get(section_id, {})
    payload = {
        "course_name": outline.get("course_name", ""),
        "section_id": section_id,
        "section_title": _section_title(outline, section_id),
        "section_markdown_excerpt": str(mark.get("markdown", ""))[:1200],
        "search_goal": "搜索适合该小节学习目标的视频教程，优先返回可直接打开的视频页面 URL。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_videos(section_id: str, outline: dict, raw: object) -> dict:
    payload = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
    videos: list[dict] = []
    for item in payload.get("videos", []):
        if not isinstance(item, dict):
            continue
        url = _clean_text(item.get("url"))
        if not url:
            continue
        title = _clean_text(item.get("title")) or _section_title(outline, section_id)
        cover_url = _clean_text(item.get("cover_url"))
        cover_status = "provided" if cover_url else "fallback"
        videos.append({
            "title": title,
            "url": url,
            "cover_url": cover_url or _fallback_cover_data_url(title),
            "cover_status": cover_status,
            "source": _clean_text(item.get("source")),
        })
    section = _section_by_id(outline, section_id) or {}
    return {
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "query": _clean_text(payload.get("query")),
        "videos": videos,
        "generated_at": _now_iso(),
    }


async def run_section_video_search_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}
    plan = state.get("course_resource_plan")
    if isinstance(plan, dict) and isinstance(plan.get("target_section_ids"), list):
        target_ids = [str(item) for item in plan["target_section_ids"]]
    else:
        args = _tool_args(state, explicit_args)
        scope = _clean_text(args.get("scope")) or "default_first_chapter"
        target_ids = [
            _clean_text(section.get("section_id"))
            for section in _target_sections_for_scope(outline, _clean_text(args.get("section_id")), scope)
        ]

    structured_llm = llm.with_structured_output(SectionVideoSearchOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SECTION_VIDEO_SEARCH_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm
    resources: dict[str, dict] = {}
    for section_id in target_ids:
        try:
            generated = await asyncio.wait_for(
                chain.ainvoke({"query": _video_input(outline, section_id)}),
                timeout=_RESOURCE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Section video search failed: %s", exc)
            resources[section_id] = _normalize_videos(section_id, outline, {"section_id": section_id, "query": "", "videos": []})
        else:
            resources[section_id] = _normalize_videos(section_id, outline, generated)

    updated_outline = _merge_course_resource_data(outline, "section_video_links", resources)
    _persist_outline(str(state["user_id"]), updated_outline)
    plan = dict(plan) if isinstance(plan, dict) else {}
    plan["video_section_ids"] = list(resources.keys())
    return {"course_knowledge": updated_outline, "course_resource_plan": plan}
```

- [ ] **Step 9: Run video tests**

Run:

```bash
cd backend && uv run pytest tests/test_orchestration_llm.py::test_search_worker_llm_enables_search tests/test_course_resource_agent_contract.py::test_run_section_video_search_agent_writes_url_and_fallback_cover -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 3**

```bash
git add backend/app/orchestration/llm.py backend/app/orchestration/agents/course_resources.py backend/app/orchestration/agents/prompts.py backend/tests/test_orchestration_llm.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: add section video search agent"
```

## Task 4: Section HTML Animation Agent

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources.py`
- Modify: `backend/app/orchestration/agents/prompts.py`
- Test: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing HTML animation test**

Append to `backend/tests/test_course_resource_agent_contract.py`:

```python
from app.orchestration.agents.course_resources import run_section_html_animation_agent
from app.orchestration.agents.models import SectionHtmlAnimationOutput


def test_run_section_html_animation_agent_uses_animation_briefs(tmp_path) -> None:
    class RecordingLlm:
        def with_structured_output(self, schema, *_args, **_kwargs):
            captured["schema"] = schema
            return object()

    class AnimationChain:
        async def ainvoke(self, payload):
            captured["queries"].append(payload["query"])
            return SectionHtmlAnimationOutput(
                section_id="1.1",
                animations=[
                    {
                        "animation_id": "section-1-1-animation-1",
                        "title": "目标到验收标准",
                        "html": "<section class=\"section-animation\" data-animation-id=\"section-1-1-animation-1\"></section>",
                    }
                ],
            )

    class AnimationPrompt:
        def __or__(self, _other):
            return AnimationChain()

    class PromptFactory:
        @staticmethod
        def from_messages(_messages):
            return AnimationPrompt()

    outline = _outline()
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "学习目标",
            "markdown": "# 学习目标\n\n完整教学内容",
            "animation_briefs": [
                {
                    "animation_id": "section-1-1-animation-1",
                    "title": "目标到验收标准",
                    "concept": "展示学习目标如何收敛为验收标准",
                    "placement_hint": "核心概念之后",
                }
            ],
            "generated_at": "2026-06-06T00:00:00Z",
        }
    }
    captured = {"schema": None, "queries": []}
    engine = build_engine(f"sqlite:///{tmp_path / 'section-animation.db'}")
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(User(uid="user-1", username="课程用户", identifier="course@example.com"))
        session.add(
            UserCourseKnowledgeOutline(
                user_uid="user-1",
                course_id="year_3_course_1",
                grade_year="year_3",
                course_name="AI 应用开发",
                outline_data=outline,
            )
        )
        session.commit()

    import app.orchestration.agents.course_resources as module
    original_factory = module.ChatPromptTemplate
    module.ChatPromptTemplate = PromptFactory
    try:
        result = asyncio.run(
            run_section_html_animation_agent(
                {
                    "user_id": "user-1",
                    "course_knowledge": outline,
                    "course_resource_plan": {
                        "course_id": "year_3_course_1",
                        "target_section_ids": ["1.1"],
                    },
                    "messages": [],
                },
                RecordingLlm(),
            )
        )
    finally:
        module.ChatPromptTemplate = original_factory

    assert captured["schema"] is SectionHtmlAnimationOutput
    animations = result["course_knowledge"]["section_html_animations"]["1.1"]["animations"]
    assert animations[0]["animation_id"] == "section-1-1-animation-1"
    assert "section-animation" in animations[0]["html"]
    assert result["course_resource_result"]["markdown_count"] == 1
    assert result["response"].startswith("《AI 应用开发》的 1.1 教学内容已生成")
```

- [ ] **Step 2: Run animation test to verify it fails**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_run_section_html_animation_agent_uses_animation_briefs -q
```

Expected: FAIL because `run_section_html_animation_agent` is missing.

- [ ] **Step 3: Add animation prompt**

Append to `backend/app/orchestration/agents/prompts.py`:

```python

SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT = """\
你是课程 HTML 动画生成智能体。你只根据输入的 animation_briefs 生成可嵌入 HTML 片段。

## 输出要求
- 必须输出 JSON，且只能输出 JSON 对象。
- animations 中的 animation_id 必须来自输入 animation_briefs。
- html 必须是单段可嵌入 HTML 字符串，根节点使用 class="section-animation"。
- 只使用内联 HTML、CSS 和少量 JavaScript，不依赖外部资源。
- 没有 animation_briefs 时输出 animations 空列表。
"""
```

- [ ] **Step 4: Implement animation agent**

Extend `backend/app/orchestration/agents/course_resources.py`:

```python
from app.orchestration.agents.models import SectionHtmlAnimationOutput
from app.orchestration.agents.prompts import SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT


def _animation_input(outline: dict, section_id: str) -> str:
    mark = outline.get("section_markdowns", {}).get(section_id, {})
    payload = {
        "course_name": outline.get("course_name", ""),
        "section_id": section_id,
        "section_title": _section_title(outline, section_id),
        "markdown": mark.get("markdown", ""),
        "animation_briefs": mark.get("animation_briefs", []),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_animations(section_id: str, outline: dict, raw: object) -> dict:
    payload = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
    mark = outline.get("section_markdowns", {}).get(section_id, {})
    allowed_ids = {
        item.get("animation_id")
        for item in mark.get("animation_briefs", [])
        if isinstance(item, dict)
    }
    animations: list[dict] = []
    for item in payload.get("animations", []):
        if not isinstance(item, dict):
            continue
        animation_id = _clean_text(item.get("animation_id"))
        html = _clean_text(item.get("html"))
        if not animation_id or animation_id not in allowed_ids or not html:
            continue
        animations.append({
            "animation_id": animation_id,
            "title": _clean_text(item.get("title")),
            "html": html,
            "generated_at": _now_iso(),
        })
    section = _section_by_id(outline, section_id) or {}
    return {
        "section_id": section_id,
        "parent_section_id": section.get("parent_section_id"),
        "animations": animations,
        "generated_at": _now_iso(),
    }


async def run_section_html_animation_agent(
    state: OrchestrationState,
    llm: BaseChatModel,
    explicit_args: dict | None = None,
) -> dict:
    outline = state.get("course_knowledge")
    if not isinstance(outline, dict):
        return {"error": "请先生成课程大纲。", "hard_error": True}
    plan = state.get("course_resource_plan")
    if isinstance(plan, dict) and isinstance(plan.get("target_section_ids"), list):
        target_ids = [str(item) for item in plan["target_section_ids"]]
    else:
        args = _tool_args(state, explicit_args)
        scope = _clean_text(args.get("scope")) or "default_first_chapter"
        target_ids = [
            _clean_text(section.get("section_id"))
            for section in _target_sections_for_scope(outline, _clean_text(args.get("section_id")), scope)
        ]

    structured_llm = llm.with_structured_output(SectionHtmlAnimationOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
    chain = prompt | structured_llm
    resources: dict[str, dict] = {}
    for section_id in target_ids:
        mark = outline.get("section_markdowns", {}).get(section_id, {})
        if not isinstance(mark, dict) or not mark.get("animation_briefs"):
            resources[section_id] = _normalize_animations(section_id, outline, {"section_id": section_id, "animations": []})
            continue
        try:
            generated = await asyncio.wait_for(
                chain.ainvoke({"query": _animation_input(outline, section_id)}),
                timeout=_RESOURCE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Section HTML animation generation failed: %s", exc)
            resources[section_id] = _normalize_animations(section_id, outline, {"section_id": section_id, "animations": []})
        else:
            resources[section_id] = _normalize_animations(section_id, outline, generated)

    updated_outline = _merge_course_resource_data(outline, "section_html_animations", resources)
    _persist_outline(str(state["user_id"]), updated_outline)
    markdown_count = len(updated_outline.get("section_markdowns", {}))
    video_count = sum(len(item.get("videos", [])) for item in updated_outline.get("section_video_links", {}).values() if isinstance(item, dict))
    animation_count = sum(len(item.get("animations", [])) for item in resources.values())
    generated_ids = list(resources.keys())
    course_name = _clean_text(updated_outline.get("course_name"))
    response = f"《{course_name}》的 {('、'.join(generated_ids))} 教学内容已生成：每个小节都有 Markdown 文档，视频与动画资源已同步保存。"
    return {
        "course_knowledge": updated_outline,
        "course_resource_result": {
            "course_id": updated_outline.get("course_id", ""),
            "generated_section_ids": generated_ids,
            "markdown_count": markdown_count,
            "video_count": video_count,
            "animation_count": animation_count,
        },
        "response": response,
    }
```

- [ ] **Step 5: Add node factory**

Append to `backend/app/orchestration/agents/course_resources.py`:

```python
def create_section_video_search_agent_node(llm: BaseChatModel):
    async def section_video_search_node(state: OrchestrationState) -> dict:
        agent_result = await run_section_video_search_agent(state, llm)
        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )
        result = {"messages": [tool_message]}
        for key in ("course_knowledge", "course_resource_plan", "response"):
            if agent_result.get(key) is not None:
                result[key] = agent_result[key]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result
    return section_video_search_node


def create_section_html_animation_agent_node(llm: BaseChatModel):
    async def section_html_animation_node(state: OrchestrationState) -> dict:
        agent_result = await run_section_html_animation_agent(state, llm)
        tool_call_id = extract_last_tool_call_id(state)
        tool_message = ToolMessage(
            content=json.dumps(agent_result, ensure_ascii=False),
            tool_call_id=tool_call_id or "unknown",
        )
        result = {"messages": [tool_message]}
        for key in ("course_knowledge", "course_resource_result", "response"):
            if agent_result.get(key) is not None:
                result[key] = agent_result[key]
        if agent_result.get("error") is not None:
            result["response"] = agent_result["error"]
        return result
    return section_html_animation_node
```

- [ ] **Step 6: Run animation tests**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py::test_run_section_html_animation_agent_uses_animation_briefs -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add backend/app/orchestration/agents/course_resources.py backend/app/orchestration/agents/prompts.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: add section html animation agent"
```

## Task 5: Graph, Supervisor, And Rule Wiring

**Files:**
- Modify: `backend/app/orchestration/state.py`
- Modify: `backend/app/orchestration/rule_engine.py`
- Modify: `backend/app/orchestration/agents/supervisor.py`
- Modify: `backend/app/orchestration/graph.py`
- Modify: `backend/tests/test_rule_engine.py`
- Modify: `backend/tests/test_supervisor_force_call.py`
- Modify: `backend/tests/test_orchestration_llm.py`

- [ ] **Step 1: Add failing rule engine tests**

Append to `backend/tests/test_rule_engine.py`:

```python
from app.orchestration.rule_engine import (
    AGENT_SECTION_MARKDOWN,
    AGENT_SECTION_VIDEO_SEARCH,
    AGENT_SECTION_HTML_ANIMATION,
    is_course_resource_generation_query,
)


def test_course_resource_generation_query_keywords() -> None:
    assert is_course_resource_generation_query("生成当前课程教学内容")
    assert is_course_resource_generation_query("生成第一章内容")
    assert is_course_resource_generation_query("开始学习这门课")
    assert not is_course_resource_generation_query("先看看学习路径")


def test_profile_and_path_without_outline_forces_course_knowledge_for_resources() -> None:
    state = {
        "query": "生成当前课程教学内容",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": None,
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_COURSE_KNOWLEDGE
    assert AGENT_SECTION_MARKDOWN in result.blocked_agents
    assert AGENT_SECTION_VIDEO_SEARCH in result.blocked_agents
    assert AGENT_SECTION_HTML_ANIMATION in result.blocked_agents


def test_profile_path_and_outline_forces_section_markdown_for_resources() -> None:
    state = {
        "query": "生成当前课程教学内容",
        "profile": _complete_profile(),
        "year_learning_paths": {"year_3": {"grade_plans": {"year_3": {"course_nodes": []}}}},
        "course_knowledge": {"course_id": "year_3_course_1", "sections": []},
        "messages": [],
    }
    result = evaluate(state)

    assert result.force_call == AGENT_SECTION_MARKDOWN
```

- [ ] **Step 2: Run rule tests to verify they fail**

Run:

```bash
cd backend && uv run pytest tests/test_rule_engine.py::test_course_resource_generation_query_keywords tests/test_rule_engine.py::test_profile_and_path_without_outline_forces_course_knowledge_for_resources tests/test_rule_engine.py::test_profile_path_and_outline_forces_section_markdown_for_resources -q
```

Expected: FAIL because new constants and intent helper are missing.

- [ ] **Step 3: Modify state**

Modify `backend/app/orchestration/state.py`:

```python
    course_resource_plan: Optional[dict]
    course_resource_result: Optional[dict]
```

- [ ] **Step 4: Modify rule engine**

Modify `backend/app/orchestration/rule_engine.py`:

```python
AGENT_SECTION_MARKDOWN = "section_markdown_agent"
AGENT_SECTION_VIDEO_SEARCH = "section_video_search_agent"
AGENT_SECTION_HTML_ANIMATION = "section_html_animation_agent"

ALL_WORKER_AGENTS = {
    AGENT_PROFILE,
    AGENT_LEARNING_PATH,
    AGENT_COURSE_KNOWLEDGE,
    AGENT_SECTION_MARKDOWN,
    AGENT_SECTION_VIDEO_SEARCH,
    AGENT_SECTION_HTML_ANIMATION,
}

_COURSE_RESOURCE_GENERATION_KEYWORDS = {
    "生成当前课程教学内容",
    "生成课程教学内容",
    "生成第一章内容",
    "生成章节内容",
    "开始学习这门课",
    "开始学习当前课程",
}


def is_course_resource_generation_query(query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return False
    return any(keyword in q for keyword in _COURSE_RESOURCE_GENERATION_KEYWORDS)


def _has_course_knowledge(state: dict) -> bool:
    value = state.get("course_knowledge")
    return isinstance(value, dict) and bool(value.get("sections"))
```

In `_rule_no_profile`, include section agents in `blocked_agents`.

In `_rule_has_profile_no_path`, include section agents in `blocked_agents`.

In `_rule_has_profile_and_path`, add before `is_navigation_query(query)`:

```python
    if is_course_resource_generation_query(query):
        if _has_course_knowledge(state):
            result.force_call = AGENT_SECTION_MARKDOWN
        else:
            result.force_call = AGENT_COURSE_KNOWLEDGE
            result.blocked_agents.add(AGENT_SECTION_MARKDOWN)
            result.blocked_agents.add(AGENT_SECTION_VIDEO_SEARCH)
            result.blocked_agents.add(AGENT_SECTION_HTML_ANIMATION)
        return result
```

- [ ] **Step 5: Add failing supervisor test**

Append to `backend/tests/test_supervisor_force_call.py`:

```python
from app.orchestration.rule_engine import AGENT_SECTION_MARKDOWN


def test_force_call_response_uses_section_markdown_for_course_resources() -> None:
    response = _force_call_response(
        AGENT_SECTION_MARKDOWN,
        {
            "query": "生成第一章内容",
            "course_knowledge": {"course_id": "year_3_course_1"},
        },
    )

    tool_call = response["messages"][0].tool_calls[0]
    assert tool_call["name"] == AGENT_SECTION_MARKDOWN
    assert tool_call["args"] == {
        "course_id": "year_3_course_1",
        "section_id": "1",
        "scope": "chapter_sections",
    }
```

- [ ] **Step 6: Modify supervisor tools and force call**

Modify `backend/app/orchestration/agents/supervisor.py`:

```python
from app.orchestration.rule_engine import (
    AGENT_COURSE_KNOWLEDGE,
    AGENT_LEARNING_PATH,
    AGENT_PROFILE,
    AGENT_SECTION_MARKDOWN,
    AGENT_SECTION_VIDEO_SEARCH,
    AGENT_SECTION_HTML_ANIMATION,
    ...
)
```

Add tools inside `create_tools_for_llm()`:

```python
    @tool
    async def section_markdown_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前课程的小节生成 Markdown 教学文档。

        Args:
            course_id: 课程 ID，留空时使用当前课程
            section_id: 小节或一级章节 ID
            scope: default_first_chapter/single_section/chapter_sections/course_sections
        """
        return ""

    @tool
    async def section_video_search_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前课程小节联网搜索教学视频链接和封面。"""
        return ""

    @tool
    async def section_html_animation_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前课程小节生成 HTML 动画资源。"""
        return ""
```

Return all six tools.

Add helper:

```python
def _section_markdown_force_args(state: OrchestrationState) -> dict[str, str]:
    query = str(state.get("query", "")).strip()
    course_knowledge = state.get("course_knowledge")
    course_id = course_knowledge.get("course_id", "") if isinstance(course_knowledge, dict) else ""
    if "当前课程" in query or "整门课" in query:
        return {"course_id": course_id, "section_id": "", "scope": "course_sections"}
    if "第一章" in query:
        return {"course_id": course_id, "section_id": "1", "scope": "chapter_sections"}
    return {"course_id": course_id, "section_id": "", "scope": "default_first_chapter"}
```

Add branch in `_force_call_response`:

```python
    elif agent_key == AGENT_SECTION_MARKDOWN:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": AGENT_SECTION_MARKDOWN,
                        "args": _section_markdown_force_args(state),
                        "id": f"force_{AGENT_SECTION_MARKDOWN}",
                    }],
                )
            ],
        }
```

- [ ] **Step 7: Modify graph**

Modify `backend/app/orchestration/graph.py` imports:

```python
from app.orchestration.agents.course_resources import (
    create_section_html_animation_agent_node,
    create_section_markdown_agent_node,
    create_section_video_search_agent_node,
)
from app.orchestration.llm import (
    get_search_worker_llm,
    get_supervisor_llm,
    get_thinking_worker_llm,
    get_worker_llm,
)
```

Update labels and workers:

```python
AGENT_LABELS = {
    "profile_agent": "画像智能体",
    "learning_path_agent": "学习路径智能体",
    "course_knowledge_agent": "课程大纲智能体",
    "section_markdown_agent": "小节文档智能体",
    "section_video_search_agent": "视频搜索智能体",
    "section_html_animation_agent": "HTML 动画智能体",
}

WORKER_AGENTS = {
    "profile_agent",
    "learning_path_agent",
    "course_knowledge_agent",
    "section_markdown_agent",
    "section_video_search_agent",
    "section_html_animation_agent",
}
```

Update `route_after_worker`:

```python
def route_after_worker(state: OrchestrationState) -> str:
    last_agent = _extract_last_tool_agent(state)
    if last_agent == "section_markdown_agent":
        return "section_video_search_agent"
    if last_agent == "section_video_search_agent":
        return "section_html_animation_agent"
    if should_auto_continue_learning_path_after_profile(state):
        return SUPERVISOR_NODE
    return END
```

Add `_extract_last_tool_agent` to the existing `rule_engine.py` import list in `graph.py` before this change.

In `build_orchestration_graph()`:

```python
search_worker_llm = get_search_worker_llm()
section_markdown_node = create_section_markdown_agent_node(thinking_worker_llm)
section_video_search_node = create_section_video_search_agent_node(search_worker_llm)
section_html_animation_node = create_section_html_animation_agent_node(thinking_worker_llm)
```

Add nodes and conditional edge map entries for the three new workers.

- [ ] **Step 8: Update graph LLM test**

Modify `backend/tests/test_orchestration_llm.py::test_graph_routes_learning_and_outline_agents_to_thinking_worker`:

```python
search_llm = object()
monkeypatch.setattr(graph_module, "get_search_worker_llm", lambda: search_llm)

def section_markdown_factory(llm):
    received["section_markdown_agent"] = llm
    return dummy_node

def section_video_search_factory(llm):
    received["section_video_search_agent"] = llm
    return dummy_node

def section_html_animation_factory(llm):
    received["section_html_animation_agent"] = llm
    return dummy_node

monkeypatch.setattr(graph_module, "create_section_markdown_agent_node", section_markdown_factory)
monkeypatch.setattr(graph_module, "create_section_video_search_agent_node", section_video_search_factory)
monkeypatch.setattr(graph_module, "create_section_html_animation_agent_node", section_html_animation_factory)

assert received["section_markdown_agent"] is thinking_llm
assert received["section_video_search_agent"] is search_llm
assert received["section_html_animation_agent"] is thinking_llm
```

- [ ] **Step 9: Run wiring tests**

Run:

```bash
cd backend && uv run pytest tests/test_rule_engine.py::test_course_resource_generation_query_keywords tests/test_rule_engine.py::test_profile_and_path_without_outline_forces_course_knowledge_for_resources tests/test_rule_engine.py::test_profile_path_and_outline_forces_section_markdown_for_resources tests/test_supervisor_force_call.py::test_force_call_response_uses_section_markdown_for_course_resources tests/test_orchestration_llm.py::test_graph_routes_learning_and_outline_agents_to_thinking_worker -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 5**

```bash
git add backend/app/orchestration/state.py backend/app/orchestration/rule_engine.py backend/app/orchestration/agents/supervisor.py backend/app/orchestration/graph.py backend/tests/test_rule_engine.py backend/tests/test_supervisor_force_call.py backend/tests/test_orchestration_llm.py
git commit -m "feat: wire section resource agents"
```

## Task 6: Chat API Persistence Flow

**Files:**
- Modify: `backend/app/api/orchestration.py`
- Modify: `backend/tests/test_orchestration_api.py`

- [ ] **Step 1: Add failing API test for chat-triggered resource generation and loaded resource summary**

Append inside `TestChatEndpoints` in `backend/tests/test_orchestration_api.py`:

```python
    def test_send_message_generates_section_resources_from_chat(self, tmp_path: Path) -> None:
        identifier = "resource-chat@example.com"
        database_url = f"sqlite:///{tmp_path / 'chat-test.db'}"

        async def resource_events(state):
            course_knowledge = dict(state["course_knowledge"])
            course_knowledge["section_markdowns"] = {
                "1.1": {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "title": "学习目标",
                    "markdown": "# 学习目标\n\n完整教学内容",
                    "animation_briefs": [],
                    "generated_at": "2026-06-06T00:00:00Z",
                }
            }
            course_knowledge["section_video_links"] = {
                "1.1": {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "query": "AI 应用开发 学习目标 视频教程",
                    "videos": [
                        {
                            "title": "学习目标视频",
                            "url": "https://example.com/video",
                            "cover_url": "data:image/svg+xml;utf8,<svg></svg>",
                            "cover_status": "fallback",
                            "source": "example.com",
                        }
                    ],
                    "generated_at": "2026-06-06T00:00:00Z",
                }
            }
            course_knowledge["section_html_animations"] = {
                "1.1": {
                    "section_id": "1.1",
                    "parent_section_id": "1",
                    "animations": [],
                    "generated_at": "2026-06-06T00:00:00Z",
                }
            }
            from sqlmodel import Session
            from app.database import build_engine
            from app.services.course_knowledge_service import upsert_user_course_knowledge_outline
            with Session(build_engine(database_url)) as session:
                upsert_user_course_knowledge_outline(session, state["user_id"], course_knowledge)
            yield {"event": "message_completed", "full_text": "《AI Agent 开发基础能力搭建》的 1.1 教学内容已生成：每个小节都有 Markdown 文档，视频与动画资源已同步保存。"}
            yield {
                "event": "session_completed",
                "session_id": state["session_id"],
                "has_profile": True,
                "has_paths": True,
                "has_outline": True,
            }

        with patch("app.api.orchestration.stream_orchestration_events", side_effect=resource_events):
            with chat_app(tmp_path) as client:
                token = _register_user(client, identifier, "resource123456")
                _seed_existing_learning_data(database_url, identifier)
                start_resp = client.post(
                    "/api/chat/start",
                    json={"query": "开始"},
                    headers=_auth_header(token),
                )
                session_id = start_resp.json()["session_id"]

                response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "请根据课程大纲生成教学内容"},
                    headers=_auth_header(token),
                )

                assert response.status_code == 200
                assert "教学内容已生成" in response.text

                summary_response = client.post(
                    "/api/chat/message",
                    json={"session_id": session_id, "message": "查看课程大纲"},
                    headers=_auth_header(token),
                )

                assert summary_response.status_code == 200
                assert "已生成教学文档" in summary_response.text
                assert "已生成视频资源" in summary_response.text
                assert "已生成动画资源" in summary_response.text
                assert "1.1" in summary_response.text

        engine = build_engine(database_url)
        with Session(engine) as session:
            row = session.exec(select(UserCourseKnowledgeOutline)).one()

        assert "1.1" in row.outline_data["section_markdowns"]
        assert row.outline_data["section_video_links"]["1.1"]["videos"][0]["url"] == "https://example.com/video"
```

- [ ] **Step 2: Run API test to verify current behavior**

Run:

```bash
cd backend && uv run pytest tests/test_orchestration_api.py::TestChatEndpoints::test_send_message_generates_section_resources_from_chat -q
```

Expected: FAIL at `assert "教学内容已生成" in response.text` because current `_is_outline_review_query()` treats `"请根据课程大纲生成教学内容"` as outline review and returns the existing outline before `stream_orchestration_events()` runs.

- [ ] **Step 3: Fix API helper behavior**

Change `_is_outline_review_query` in `backend/app/api/orchestration.py` so generation queries are not treated as outline review:

```python
def _is_course_resource_generation_query(query: str) -> bool:
    from app.orchestration.rule_engine import is_course_resource_generation_query
    return is_course_resource_generation_query(query)


def _is_outline_review_query(query: str) -> bool:
    text = query.strip()
    if _is_course_resource_generation_query(text):
        return False
    return "大纲" in text and ("课" in text or "课程" in text)
```

- [ ] **Step 4: Add loaded resource summary formatting**

Modify `_format_course_outline_text(course_knowledge: dict)` to include existing generated resources:

```python
    section_markdowns = course_knowledge.get("section_markdowns")
    if isinstance(section_markdowns, dict) and section_markdowns:
        lines.extend(["", "已生成教学文档"])
        lines.extend(sorted(str(section_id) for section_id in section_markdowns.keys()))

    section_video_links = course_knowledge.get("section_video_links")
    if isinstance(section_video_links, dict) and section_video_links:
        lines.extend(["", "已生成视频资源"])
        lines.extend(sorted(str(section_id) for section_id in section_video_links.keys()))

    section_html_animations = course_knowledge.get("section_html_animations")
    if isinstance(section_html_animations, dict) and section_html_animations:
        lines.extend(["", "已生成动画资源"])
        lines.extend(sorted(str(section_id) for section_id in section_html_animations.keys()))
```

- [ ] **Step 5: Run API test**

Run:

```bash
cd backend && uv run pytest tests/test_orchestration_api.py::TestChatEndpoints::test_send_message_generates_section_resources_from_chat -q
```

Expected: PASS.

- [ ] **Step 6: Run focused backend suite**

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py tests/test_orchestration_llm.py tests/test_rule_engine.py tests/test_supervisor_force_call.py tests/test_orchestration_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add backend/app/api/orchestration.py backend/tests/test_orchestration_api.py
git commit -m "feat: persist chat generated section resources"
```

## Self-Review

- Spec coverage:
  - Section-level Markdown generation: Task 2.
  - `1.1`/`1.2`/`1.3` each get docs for first chapter: Task 1 and Task 2 tests.
  - Video URL and cover fallback: Task 3.
  - HTML animation from Markdown animation briefs: Task 4.
  - Agent I/O and interconnection: Task 5 graph and rule wiring.
  - Chat-triggered generation and DB persistence: Task 6.
- Placeholder scan:
  - This plan contains no placeholder implementation sections and no unresolved file names.
- Type consistency:
  - Agent names use `section_markdown_agent`, `section_video_search_agent`, `section_html_animation_agent`.
  - Stored resource fields use `section_markdowns`, `section_video_links`, `section_html_animations`.
  - Shared plan state uses `course_resource_plan`; final summary uses `course_resource_result`.

## Final Verification

Run:

```bash
cd backend && uv run pytest tests/test_course_resource_agent_contract.py tests/test_orchestration_llm.py tests/test_rule_engine.py tests/test_supervisor_force_call.py tests/test_orchestration_api.py -q
```

Expected: PASS.
