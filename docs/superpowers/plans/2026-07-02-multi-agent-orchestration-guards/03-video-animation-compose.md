# Video Animation Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make video retrieval honest and make HTML animations implement concrete simulation specs rather than animated text explanations.

**Architecture:** Change video no-match from hard failure to an unavailable resource record. Strengthen animation quality checks against `visual_model` and `timeline`, then ensure compose preserves Markdown and shows resource status without deleting teaching content.

**Tech Stack:** Python 3.12, asyncio, pytest, Ruff.

---

### Task 1: Allow Honest Unavailable Video Output

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/models.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_agent_contract_models.py`

- [ ] **Step 1: Add failing video model test**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_agent_contract_models.py`:

```python
def test_section_video_search_output_allows_unavailable_with_failure_reason() -> None:
    output = SectionVideoSearchOutput(
        section_id="2.3",
        query="单链表 节点 next 指针",
        status="unavailable",
        failure_reason="未找到同时包含 单链表、节点、next 指针 的公开视频结果。",
        videos=[],
    )

    assert output.status == "unavailable"
    assert output.failure_reason.startswith("未找到")
    assert output.videos == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_agent_contract_models.py::test_section_video_search_output_allows_unavailable_with_failure_reason -q
```

Expected: FAIL because the model currently requires non-empty `videos`.

- [ ] **Step 3: Update `SectionVideoSearchOutput`**

Replace the current `SectionVideoSearchOutput` in `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/models.py` with:

```python
class SectionVideoSearchOutput(BaseModel):
    section_id: str = Field(default="", description="小节 ID")
    query: str = Field(default="", description="实际搜索查询")
    status: Literal["available", "unavailable"] = Field(default="available")
    failure_reason: str = Field(default="")
    videos: list[SectionVideoItemOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_payload(self) -> "SectionVideoSearchOutput":
        if self.status == "available" and not self.videos:
            raise ValueError("available video output must contain at least one item")
        if self.status == "unavailable" and not self.failure_reason.strip():
            raise ValueError("unavailable video output must include failure_reason")
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_agent_contract_models.py::test_section_video_search_output_allows_unavailable_with_failure_reason -q
```

Expected: PASS.

### Task 2: Return Unavailable Instead Of Search Fallback

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/video.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing video agent test**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
@pytest.mark.asyncio
async def test_video_search_no_match_returns_unavailable_without_hard_error(monkeypatch) -> None:
    from app.orchestration.agents.course_resources.video import run_section_video_search_agent

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
            "title": "学习目标",
            "markdown": _complete_section_markdown("1.1", "学习目标"),
            "source_references": [
                {
                    "textbook_id": "textbook-data-structures",
                    "textbook_title": "数据结构教程",
                    "section_id": "2.3",
                    "section_title": "单链表",
                    "evidence_summary": "依据链表教材内容生成。",
                    "content_char_count": 842,
                }
            ],
            "video_briefs": [
                {
                    "video_id": "video_1",
                    "title": "单链表节点与指针讲解视频",
                    "target_markdown_heading": "核心概念",
                    "target_paragraph_summary": "解释节点和 next 指针关系。",
                    "search_terms": ["单链表", "节点", "next 指针"],
                    "purpose": "辅助理解节点和指针关系。",
                }
            ],
            "animation_briefs": [],
        }
    }

    async def no_verified_videos(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.orchestration.agents.course_resources._find_verified_video_from_search",
        no_verified_videos,
    )

    result = await run_section_video_search_agent(
        {
            "user_id": "user-1",
            "course_knowledge": outline,
            "course_resource_plan": {"target_section_ids": ["1.1"]},
        },
        llm=None,
    )

    assert "error" not in result
    value = result["course_knowledge"]["section_video_links"]["1.1"]
    assert value["status"] == "unavailable"
    assert value["videos"] == []
    assert "未找到合格视频" in value["failure_reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_video_search_no_match_returns_unavailable_without_hard_error -q
```

Expected: FAIL because current code returns fallback search links or hard error.

- [ ] **Step 3: Change no-match handling**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/video.py`, inside `generate_video_links`, replace the fallback branch:

```python
            fallback_videos = _fallback_videos_for_briefs(
                video_briefs, section, outline
            )
            if fallback_videos:
                return target_section_id, {
                    "user_id": state.get("user_id", ""),
                    "section_id": target_section_id,
                    "parent_section_id": section.get("parent_section_id"),
                    "title": _section_title(outline, section),
                    "query": query,
                    "videos": fallback_videos,
                    "generated_at": _now_iso(),
                    "fallback_reason": quality_issue,
                }
            return target_section_id, {
                "error": f"{target_section_id} 视频资源质量不合格。"
            }
```

with:

```python
            return target_section_id, {
                "user_id": state.get("user_id", ""),
                "section_id": target_section_id,
                "parent_section_id": section.get("parent_section_id"),
                "title": _section_title(outline, section),
                "query": query,
                "status": "unavailable",
                "failure_reason": f"未找到合格视频：{quality_issue}",
                "videos": [],
                "generated_at": _now_iso(),
            }
```

Update the success return to include:

```python
            "status": "available",
            "failure_reason": "",
```

Keep `_fallback_videos_for_briefs` only for tests that still assert cover generation; do not use it as a successful search result.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_video_search_no_match_returns_unavailable_without_hard_error -q
```

Expected: PASS.

### Task 3: Add Simulation-First Animation Quality Checks

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/animation.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing animation quality tests**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def _linked_list_animation_brief() -> dict:
    return {
        "animation_id": "anim_1",
        "title": "单链表节点指针串联动画",
        "target_markdown_heading": "步骤讲解",
        "target_paragraph_summary": "解释节点、next 指针和 None 终点。",
        "concept": "单链表的节点与指针关系",
        "simulation_type": "data_structure_linked_list",
        "visual_elements": ["头指针", "节点(data,next)", "next 指针", "尾节点 None"],
        "visual_model": {
            "entities": [
                {"id": "head", "kind": "pointer", "label": "head"},
                {"id": "node_1", "kind": "node", "fields": ["data", "next"]},
                {"id": "node_2", "kind": "node", "fields": ["data", "next"]},
                {"id": "none", "kind": "terminal", "label": "None"},
            ],
            "relations": [
                {"from": "head", "to": "node_1", "kind": "points_to"},
                {"from": "node_1.next", "to": "node_2", "kind": "points_to"},
                {"from": "node_2.next", "to": "none", "kind": "points_to"},
            ],
        },
        "timeline": [
            {"step": 1, "action": "show_entity", "target": "head"},
            {"step": 2, "action": "show_entity", "target": "node_1"},
            {"step": 3, "action": "connect", "from": "head", "to": "node_1"},
        ],
        "layout": "横向链式结构",
        "motion": "节点通过 transform 进入，指针线通过 opacity 出现。",
        "interaction": "点击步骤按钮切换。",
        "success_check": ["DOM 中包含头指针", "DOM 中包含 next 指针", "DOM 中包含 None"],
        "placement_hint": "步骤讲解之后",
    }


def test_animation_quality_rejects_text_only_html_for_linked_list() -> None:
    issue = _normalized_animation_quality_issue(
        [
            {
                "animation_id": "anim_1",
                "html": '<!doctype html><html><head><meta charset="utf-8"></head><body><section class="section-animation"><style>@media (prefers-reduced-motion: reduce){.section-animation *{opacity: 1 !important;transform: none !important;}}</style><div class="animation-context">单链表说明</div><p>节点通过指针连接。</p></section></body></html>',
            }
        ],
        [_linked_list_animation_brief()],
        {"title": "单链表"},
    )

    assert issue == "动画 HTML 未实现 visual_model.entities。"


def test_animation_quality_accepts_linked_list_simulation_html() -> None:
    html = """<!doctype html><html><head><meta charset="utf-8"></head><body>
    <section class="section-animation">
    <style>
    :root{--line:oklch(70% 0.1 240);}
    @media (prefers-reduced-motion: reduce){.section-animation *{opacity: 1 !important;transform: none !important;}}
    </style>
    <div class="animation-context">单链表节点通过 next 指针串联，尾节点指向 None。</div>
    <svg data-timeline="linked-list">
      <g data-entity-id="head"><text>head 头指针</text></g>
      <g data-entity-id="node_1"><text>data</text><text>next</text></g>
      <g data-entity-id="node_2"><text>data</text><text>next</text></g>
      <g data-entity-id="none"><text>None</text></g>
      <line data-relation-from="head" data-relation-to="node_1"></line>
      <line data-relation-from="node_1.next" data-relation-to="node_2"></line>
      <line data-relation-from="node_2.next" data-relation-to="none"></line>
    </svg>
    <button data-step="1">1</button><button data-step="2">2</button>
    </section></body></html>"""

    issue = _normalized_animation_quality_issue(
        [{"animation_id": "anim_1", "html": html}],
        [_linked_list_animation_brief()],
        {"title": "单链表"},
    )

    assert issue is None
```

- [ ] **Step 2: Run animation tests to verify one fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_animation_quality_rejects_text_only_html_for_linked_list tests/test_course_resource_agent_contract.py::test_animation_quality_accepts_linked_list_simulation_html -q
```

Expected: the text-only rejection test fails until entity and relation checks are added.

- [ ] **Step 3: Implement animation brief checks**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/animation.py`, add helpers above `_normalized_animation_quality_issue`:

```python
def _html_contains_visual_entity(html_text: str, entity: dict) -> bool:
    entity_id = _clean_text(entity.get("id"))
    label = _clean_text(entity.get("label"))
    fields = _text_items(entity.get("fields"))
    if entity_id and (
        f'data-entity-id="{entity_id}"' in html_text
        or f"data-entity-id='{entity_id}'" in html_text
        or entity_id in html_text
    ):
        return True
    if label and label in html_text:
        return True
    return bool(fields and all(field in html_text for field in fields))


def _html_contains_visual_relation(html_text: str, relation: dict) -> bool:
    source = _clean_text(relation.get("from"))
    target = _clean_text(relation.get("to"))
    if source and target and source in html_text and target in html_text:
        return True
    return "line" in html_text or "connector" in html_text or "arrow" in html_text


def _animation_simulation_issue(html_text: str, brief: dict) -> str | None:
    visual_model = brief.get("visual_model")
    if not isinstance(visual_model, dict):
        return "动画 brief 缺少 visual_model。"
    entities = visual_model.get("entities")
    if not isinstance(entities, list) or not entities:
        return "动画 brief 缺少 visual_model.entities。"
    if not all(isinstance(entity, dict) and _html_contains_visual_entity(html_text, entity) for entity in entities):
        return "动画 HTML 未实现 visual_model.entities。"
    relations = visual_model.get("relations")
    if isinstance(relations, list) and relations:
        if not all(isinstance(relation, dict) and _html_contains_visual_relation(html_text, relation) for relation in relations):
            return "动画 HTML 未实现 visual_model.relations。"
    timeline = brief.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return "动画 brief 缺少 timeline。"
    if "data-step" not in html_text and "data-timeline" not in html_text and "setInterval" not in html_text:
        return "动画 HTML 未实现 timeline 或步骤状态。"
    if _clean_text(brief.get("simulation_type")) == "data_structure_linked_list":
        required_terms = ("head", "data", "next", "None")
        if not all(term in html_text or ("head" == term and "头指针" in html_text) for term in required_terms):
            return "链表动画缺少头指针、data、next 或 None。"
        if "line" not in html_text and "connector" not in html_text and "arrow" not in html_text:
            return "链表动画缺少指针连线。"
    return None
```

Inside `_normalized_animation_quality_issue`, build briefs by ID:

```python
    briefs_by_id = {
        _clean_text(brief.get("animation_id")): brief
        for brief in animation_briefs
        if isinstance(brief, dict) and _clean_text(brief.get("animation_id"))
    }
```

Inside the loop for each animation, after the existing brief-term check:

```python
        brief = briefs_by_id.get(
            _clean_text(animation.get("animation_id"))
            or _clean_text(animation.get("brief_id"))
        )
        if isinstance(brief, dict):
            simulation_issue = _animation_simulation_issue(html_text, brief)
            if simulation_issue:
                return simulation_issue
```

- [ ] **Step 4: Run animation tests to verify they pass**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_animation_quality_rejects_text_only_html_for_linked_list tests/test_course_resource_agent_contract.py::test_animation_quality_accepts_linked_list_simulation_html -q
```

Expected: PASS.

### Task 4: Compose Preserves Source References And Unavailable Resource Status

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing compose test**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def test_compose_preserves_source_references_and_unavailable_video_status() -> None:
    section_markdown = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "单链表",
        "markdown": _complete_section_markdown("1.1", "单链表"),
        "source_references": [
            {
                "textbook_id": "textbook-data-structures",
                "textbook_title": "数据结构教程",
                "section_id": "2.3",
                "section_title": "单链表",
                "evidence_summary": "依据链表教材内容生成。",
                "content_char_count": 842,
            }
        ],
        "video_briefs": [
            {
                "video_id": "video_1",
                "title": "单链表节点视频",
                "target_markdown_heading": "核心概念",
                "target_paragraph_summary": "解释节点与 next 指针。",
                "search_terms": ["单链表", "节点", "next 指针"],
                "purpose": "辅助理解节点与 next 指针。",
            }
        ],
        "animation_briefs": [],
    }

    composed = _compose_section_content(
        section_markdown,
        {
            "status": "unavailable",
            "failure_reason": "未找到合格视频",
            "videos": [],
        },
        {"animations": []},
    )

    assert composed["source_references"][0]["textbook_id"] == "textbook-data-structures"
    video_blocks = [block for block in composed["blocks"] if block["type"] == "video"]
    assert video_blocks[0]["status"] == "unavailable"
    assert video_blocks[0]["failure_reason"] == "未找到合格视频"
    assert composed["markdown"] == section_markdown["markdown"]
```

- [ ] **Step 2: Run compose test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_compose_preserves_source_references_and_unavailable_video_status -q
```

Expected: FAIL until compose copies `source_references` and failure reason.

- [ ] **Step 3: Update compose helpers**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`, update `_video_block` to include failure reason:

```python
def _video_block(brief_id: str, brief: dict, video: dict | None) -> dict:
    video_title = _clean_text(video.get("title")) if isinstance(video, dict) else ""
    return {
        "type": "video",
        "brief_id": brief_id,
        "title": _clean_text(brief.get("title")) or video_title,
        "status": "available" if isinstance(video, dict) else "unavailable",
        "failure_reason": _clean_text(brief.get("failure_reason")),
        "videos": [video] if isinstance(video, dict) else [],
    }
```

Update `_video_by_brief_id` so when `video_links.status == "unavailable"` it returns an empty dict and stores failure reasons by brief. Add:

```python
def _video_failure_by_brief_id(video_links: dict, video_briefs: dict[str, dict]) -> dict[str, str]:
    if _clean_text(video_links.get("status")) != "unavailable":
        return {}
    failure_reason = _clean_text(video_links.get("failure_reason"))
    return {brief_id: failure_reason for brief_id in video_briefs}
```

Inside `_compose_section_content`, compute:

```python
    video_failures = _video_failure_by_brief_id(video_links, video_briefs)
```

When calling `_video_block`, pass a brief dict that includes failure reason:

```python
                    {
                        **video_briefs.get(brief_id, {}),
                        "failure_reason": video_failures.get(brief_id, ""),
                    },
```

Add to returned dict:

```python
        "source_references": section_markdown.get("source_references", []),
```

- [ ] **Step 4: Run compose test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_compose_preserves_source_references_and_unavailable_video_status -q
```

Expected: PASS.

### Task 5: Format, Run Phase Tests, Commit

**Files:**
- All files changed in this phase.

- [ ] **Step 1: Run Ruff**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run ruff check --fix app/orchestration/agents/models.py app/orchestration/agents/course_resources/video.py app/orchestration/agents/course_resources/animation.py app/orchestration/agents/course_resources/common.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/agents/models.py app/orchestration/agents/course_resources/video.py app/orchestration/agents/course_resources/animation.py app/orchestration/agents/course_resources/common.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py
```

Expected: commands complete successfully.

- [ ] **Step 2: Run phase tests**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent
git add backend/app/orchestration/agents/models.py backend/app/orchestration/agents/course_resources/video.py backend/app/orchestration/agents/course_resources/animation.py backend/app/orchestration/agents/course_resources/common.py backend/tests/test_agent_contract_models.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: make resources honest and simulation first"
```

Expected: commit succeeds.
