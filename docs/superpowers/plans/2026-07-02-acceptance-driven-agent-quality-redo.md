# Acceptance Driven Agent Quality Redo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the failed agent-quality pieces so Markdown is a textbook-grounded teaching document with references, outlines are Chinese, and HTML animations implement concrete simulations instead of text slides.

**Architecture:** Keep the existing multi-agent modules, but replace the misaligned prompt contracts and quality gates at their boundaries. The Markdown agent owns source references and detailed resource plans; the HTML animation agent only implements `visual_model` and `timeline`; course outline generation normalizes DB-derived English titles into Chinese student-facing titles.

**Tech Stack:** FastAPI backend, Python 3.12, Pydantic v2, pytest, Ruff.

---

## File Map

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/app/orchestration/agents/prompts.py`
  Update Markdown, course knowledge, and HTML animation prompts to match the accepted spec.

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/app/orchestration/agents/course_knowledge.py`
  Add Chinese title normalization for DB direct outline generation.

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/app/orchestration/agents/course_resources/animation.py`
  Strengthen prompt input and quality gate so animations must implement `visual_model.entities`, `visual_model.relations`, and `timeline`.

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/app/orchestration/agents/course_resources/markdown.py`
  Ensure Markdown quality rejects preview-style or prep-style documents and generic resource plans.

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/tests/test_agent_prompt_contracts.py`
  Add prompt contract tests for teaching-document wording, source references, rich brief schema, and simulation-first animation prompt.

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/tests/test_course_knowledge_agent_contract.py`
  Add English textbook outline to Chinese student outline test.

- Modify `/Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend/tests/test_course_resource_agent_contract.py`
  Add Markdown quality and animation quality acceptance tests.

## Task 1: Prompt Contract Reset

**Files:**
- Modify: `backend/app/orchestration/agents/prompts.py`
- Modify: `backend/tests/test_agent_prompt_contracts.py`

- [ ] **Step 1: Add failing prompt tests**

Add tests that assert:

```python
def test_section_markdown_prompt_is_teaching_document_not_preview() -> None:
    assert "教学文档 + 教材来源引用" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "不是预习材料" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "source_references" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "target_paragraph_summary" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "visual_model" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "timeline" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "success_check" in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT
    assert "预习" not in SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT


def test_html_animation_prompt_requires_simulation_not_text_slides() -> None:
    assert "只负责把 animation_briefs 写成可运行 HTML" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "不得重新解释教学含义" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "visual_model.entities" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "visual_model.relations" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "timeline" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "禁止做成文字卡片轮播" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "链表" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "head" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "next" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT
    assert "None" in SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT


def test_course_knowledge_prompt_requires_chinese_student_facing_outline() -> None:
    assert "学生端章节标题必须使用中文" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
    assert "英文教材标题不得原样作为 sections[].title" in COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT
```

- [ ] **Step 2: Run prompt tests and see them fail**

Run:

```bash
cd /Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend
uv run pytest tests/test_agent_prompt_contracts.py::test_section_markdown_prompt_is_teaching_document_not_preview tests/test_agent_prompt_contracts.py::test_html_animation_prompt_requires_simulation_not_text_slides tests/test_agent_prompt_contracts.py::test_course_knowledge_prompt_requires_chinese_student_facing_outline -q
```

Expected: FAIL because prompts still contain the old brief contract.

- [ ] **Step 3: Replace prompt requirements**

In `SECTION_MARKDOWN_AGENT_SYSTEM_PROMPT`, replace the old resource brief requirements with exact requirements for:

```text
- markdown 是教学文档 + 教材来源引用，不是预习材料、导读、摘要、课前预览或学习前准备。
- JSON 必须包含 source_references。
- video_briefs 必须包含 video_id、title、target_markdown_heading、target_paragraph_summary、search_terms、purpose。
- animation_briefs 必须包含 animation_id、title、target_markdown_heading、target_paragraph_summary、concept、simulation_type、visual_elements、visual_model、timeline、layout、motion、interaction、success_check、placement_hint。
- animation_briefs 是 HTML 动画智能体的完整施工图，HTML 动画智能体不得猜教学含义。
```

Update the JSON example to include `source_references`, rich `video_briefs`, and rich `animation_briefs`.

In `SECTION_HTML_ANIMATION_AGENT_SYSTEM_PROMPT`, add exact requirements:

```text
- 只负责把 animation_briefs 写成可运行 HTML，不得重新解释教学含义。
- 必须实现 visual_model.entities、visual_model.relations、timeline。
- 禁止做成文字卡片轮播、PPT 式文字淡入淡出、只有解释文本的动画。
- 链表类 simulation_type 必须展示 head、节点 data/next 字段、next 指针连线、None 终点和步骤状态。
```

In `COURSE_KNOWLEDGE_AGENT_SYSTEM_PROMPT`, add:

```text
- 学生端章节标题必须使用中文。
- 英文教材标题不得原样作为 sections[].title。
- 如果来源教材标题是英文，必须转写为中文教学标题，并把英文来源保留在 source_section_titles。
```

- [ ] **Step 4: Run prompt tests and see them pass**

Run the same command from Step 2.

Expected: PASS.

## Task 2: Chinese Outline Guard For DB Direct Outline

**Files:**
- Modify: `backend/app/orchestration/agents/course_knowledge.py`
- Modify: `backend/tests/test_course_knowledge_agent_contract.py`

- [ ] **Step 1: Add failing test**

Add:

```python
def test_db_outline_translation_outputs_chinese_student_titles_for_english_outline(tmp_path: Path) -> None:
    engine = build_engine(postgresql_test_url(tmp_path, "english-outline-chinese-title"))
    set_engine(engine)
    init_db(engine)
    with Session(engine) as session:
        session.add(enabled_source())
        row = published_textbook(textbook_id=SOURCE_TEXTBOOK_ID, title=SOURCE_TEXTBOOK_TITLE)
        row.language = "en"
        row.translated_language = "zh"
        row.outline = {
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "Linked Lists",
                    "sections": [
                        {"section_id": "1.1", "title": "Node and Pointer Structure"},
                        {"section_id": "1.2", "title": "Insertion and Deletion"},
                    ],
                }
            ]
        }
        session.add(row)
        session.add(
            section(
                textbook_id=SOURCE_TEXTBOOK_ID,
                section_content_id="linked-list-1-1",
                section_id="1.1",
                title="Node and Pointer Structure",
                content_original="A linked list stores elements in nodes. Each node contains data and a pointer to the next node.",
                content_zh="链表把元素存储在节点中。每个节点包含数据域和指向下一个节点的指针。",
                order_index=1,
            )
        )
        session.add(
            section(
                textbook_id=SOURCE_TEXTBOOK_ID,
                section_content_id="linked-list-1-2",
                section_id="1.2",
                title="Insertion and Deletion",
                content_original="Insertion and deletion update links between neighboring nodes.",
                content_zh="插入和删除操作会更新相邻节点之间的链接关系。",
                order_index=2,
            )
        )
        session.commit()

        outline = _try_db_outline_translation(
            session,
            {
                "course_node_id": "year_3_course_1",
                "course_or_chapter_theme": "数据结构",
                "grade_id": "year_3",
                "source_textbook_id": SOURCE_TEXTBOOK_ID,
                "source_textbook_title": SOURCE_TEXTBOOK_TITLE,
                "source_outline_section_ids": ["1.1", "1.2"],
            },
            "year_3",
        )

    assert outline is not None
    titles = [item["title"] for item in outline["sections"]]
    assert "Linked Lists" not in titles
    assert "Node and Pointer Structure" not in titles
    assert any("链表" in title for title in titles)
    assert all(any("\u4e00" <= char <= "\u9fff" for char in title) for title in titles)
```

- [ ] **Step 2: Run the test and see it fail**

Run:

```bash
cd /Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend
uv run pytest tests/test_course_knowledge_agent_contract.py::test_db_outline_translation_outputs_chinese_student_titles_for_english_outline -q
```

Expected: FAIL because DB direct titles remain English.

- [ ] **Step 3: Implement title normalization**

In `course_knowledge.py`, add helpers near DB outline translation helpers:

```python
def _contains_chinese_text(value: object) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(value or ""))


def _student_facing_chinese_title(raw_title: str, content_text: str, fallback: str) -> str:
    clean_title = _clean_text(raw_title)
    if _contains_chinese_text(clean_title):
        return clean_title
    text = _clean_text(content_text)
    if "链表" in text and ("节点" in text or "指针" in text):
        if "插入" in text or "删除" in text:
            return "链表的插入与删除"
        return "链表的节点与指针结构"
    if "向量" in text or "嵌入" in text:
        return "向量表示与语义检索"
    if "复杂度" in text:
        return "复杂度分析"
    return fallback
```

Use this helper in `_try_db_outline_translation`:

- Chapter title becomes `f"第一章：{topic}"` style Chinese when raw chapter title is English.
- Child section title becomes Chinese from `content_zh` when raw section title is English.
- Keep original English titles in `source_section_titles`.

- [ ] **Step 4: Run the test and see it pass**

Run the command from Step 2.

Expected: PASS.

## Task 3: Teaching Markdown And Simulation Quality Gates

**Files:**
- Modify: `backend/app/orchestration/agents/course_resources/markdown.py`
- Modify: `backend/app/orchestration/agents/course_resources/animation.py`
- Modify: `backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing tests**

Add:

```python
def test_markdown_quality_rejects_preview_or_prep_document_wording() -> None:
    markdown = _complete_section_markdown("1.1", "单链表").replace(
        "## 学习目标",
        "## 学习目标\n本节是课前预习材料，帮助你先浏览链表内容。\n\n## 学习目标",
    )
    issue = _markdown_quality_issue(
        markdown,
        {
            "section_id": "1.1",
            "title": "单链表",
            "description": "讲解节点和指针。",
            "key_knowledge_points": ["节点", "指针"],
            "source_textbook_id": "textbook-data-structures",
            "source_textbook_title": "数据结构教程",
            "source_section_ids": ["2.3"],
            "source_section_titles": ["单链表"],
        },
        _valid_markdown_video_briefs("单链表"),
        _valid_markdown_animation_briefs("单链表"),
    )

    assert issue == "Markdown 必须是教学文档，不得写成预习或导读材料。"


def test_animation_input_tells_agent_to_implement_visual_model_not_explain_text() -> None:
    outline = _outline()
    outline["sections"][1].update(
        {
            "source_textbook_id": "textbook-data-structures",
            "source_textbook_title": "数据结构教程",
            "source_section_ids": ["2.3"],
            "source_section_titles": ["单链表"],
            "source_content_chars": 842,
        }
    )
    outline["section_markdowns"] = {
        "1.1": {
            "section_id": "1.1",
            "parent_section_id": "1",
            "title": "单链表",
            "markdown": _complete_section_markdown("1.1", "单链表"),
            "source_references": [],
            "video_briefs": [],
            "animation_briefs": [_linked_list_animation_brief()],
        }
    }
    section = _section_by_id(outline, "1.1")
    assert section is not None

    query = _animation_input({"profile": _profile()}, outline, section)

    assert "visual_model.entities" in query
    assert "visual_model.relations" in query
    assert "timeline" in query
    assert "禁止做成文字卡片轮播" in query
```

- [ ] **Step 2: Run tests and see them fail**

Run:

```bash
cd /Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_markdown_quality_rejects_preview_or_prep_document_wording tests/test_course_resource_agent_contract.py::test_animation_input_tells_agent_to_implement_visual_model_not_explain_text -q
```

Expected: FAIL until gates and animation input are updated.

- [ ] **Step 3: Implement gates**

In `markdown.py`, add preview wording rejection in `_markdown_quality_issue`:

```python
    preview_markers = ("预习", "导读", "课前预览", "学习前准备", "先浏览")
    if any(marker in text for marker in preview_markers):
        return "Markdown 必须是教学文档，不得写成预习或导读材料。"
```

In `animation.py`, update `_animation_input` and `_animation_repair_input` instruction text to include:

```text
你必须实现 animation_briefs 中的 visual_model.entities、visual_model.relations 和 timeline。
禁止做成文字卡片轮播、PPT 式说明、只有中文解释段落的动画。
链表必须画出 head、节点 data/next 字段、next 指针连线、None 终点和步骤状态。
```

- [ ] **Step 4: Run tests and see them pass**

Run the command from Step 2.

Expected: PASS.

## Task 4: Final Focused Verification And Commit

**Files:**
- All modified files in this plan.

- [ ] **Step 1: Run Ruff**

Run:

```bash
cd /Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend
uv run ruff check --fix app/orchestration/agents/prompts.py app/orchestration/agents/course_knowledge.py app/orchestration/agents/course_resources/markdown.py app/orchestration/agents/course_resources/animation.py tests/test_agent_prompt_contracts.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/agents/prompts.py app/orchestration/agents/course_knowledge.py app/orchestration/agents/course_resources/markdown.py app/orchestration/agents/course_resources/animation.py tests/test_agent_prompt_contracts.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py
```

Expected: PASS.

- [ ] **Step 2: Run focused acceptance tests**

Run:

```bash
cd /Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards/backend
uv run pytest \
  tests/test_agent_prompt_contracts.py::test_section_markdown_prompt_is_teaching_document_not_preview \
  tests/test_agent_prompt_contracts.py::test_html_animation_prompt_requires_simulation_not_text_slides \
  tests/test_agent_prompt_contracts.py::test_course_knowledge_prompt_requires_chinese_student_facing_outline \
  tests/test_course_knowledge_agent_contract.py::test_db_outline_translation_outputs_chinese_student_titles_for_english_outline \
  tests/test_course_resource_agent_contract.py::test_markdown_quality_rejects_preview_or_prep_document_wording \
  tests/test_course_resource_agent_contract.py::test_animation_input_tells_agent_to_implement_visual_model_not_explain_text \
  tests/test_course_resource_agent_contract.py::test_animation_quality_rejects_text_only_html_for_linked_list \
  tests/test_course_resource_agent_contract.py::test_animation_quality_accepts_linked_list_simulation_html \
  -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

Run:

```bash
cd /Users/torch/.config/superpowers/worktrees/mutiagent/codex-multi-agent-orchestration-guards
git add backend/app/orchestration/agents/prompts.py backend/app/orchestration/agents/course_knowledge.py backend/app/orchestration/agents/course_resources/markdown.py backend/app/orchestration/agents/course_resources/animation.py backend/tests/test_agent_prompt_contracts.py backend/tests/test_course_knowledge_agent_contract.py backend/tests/test_course_resource_agent_contract.py
git commit -m "fix: align agent outputs with teaching quality spec"
```

Expected: commit succeeds.

## Self-Review

Spec coverage:

- Markdown prompt now requires a teaching document with source references, not preview material.
- Markdown resource briefs use the rich schema that lets downstream agents avoid guessing.
- HTML animation prompt and input require implementation of `visual_model` and `timeline`.
- Linked-list animation quality rejects text-only output.
- DB direct outline path converts English student-facing titles to Chinese.

Verification scope:

- The final tests directly cover the three reported acceptance failures.
- Broad contract tests are not run during every step to save time; run them only after this focused acceptance suite is green.
