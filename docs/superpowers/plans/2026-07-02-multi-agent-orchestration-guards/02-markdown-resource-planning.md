# Markdown Resource Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `section_markdown_agent` the single owner of textbook attribution, video planning, and simulation-first animation planning.

**Architecture:** Extend structured models first, then shared resource helpers, then Markdown normalization and quality gates. The HTML animation agent receives complete instructions later; it does not decide teaching meaning.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, Ruff.

---

### Task 1: Extend Markdown Resource Models

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/models.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_agent_contract_models.py`

- [ ] **Step 1: Add failing model tests**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_agent_contract_models.py`:

```python
def _source_reference() -> dict:
    return {
        "textbook_id": "textbook-ai-web",
        "textbook_title": "AI 应用开发项目教程",
        "section_id": "1.1",
        "section_title": "功能边界",
        "evidence_summary": "依据教材中对功能边界和验收标准的定义生成。",
        "content_char_count": 320,
    }


def _paragraph_bound_video_brief() -> dict:
    return {
        "video_id": "video_1",
        "title": "功能边界与验收标准讲解",
        "target_markdown_heading": "核心概念",
        "target_paragraph_summary": "解释功能边界如何限定输入、输出和验收标准。",
        "search_terms": ["功能边界", "验收标准", "输入输出"],
        "purpose": "辅助理解功能边界与验收标准的关系。",
    }


def _simulation_animation_brief() -> dict:
    return {
        "animation_id": "anim_1",
        "title": "功能边界输入输出流转",
        "target_markdown_heading": "步骤讲解",
        "target_paragraph_summary": "展示需求输入如何经过边界判断生成验收项。",
        "concept": "功能边界到验收标准的流转",
        "simulation_type": "process_boundary_flow",
        "visual_elements": ["需求输入", "边界判断", "验收项"],
        "visual_model": {
            "entities": [
                {"id": "input", "kind": "data", "label": "需求输入"},
                {"id": "boundary", "kind": "decision", "label": "边界判断"},
                {"id": "acceptance", "kind": "output", "label": "验收项"},
            ],
            "relations": [
                {"from": "input", "to": "boundary", "kind": "flows_to"},
                {"from": "boundary", "to": "acceptance", "kind": "produces"},
            ],
        },
        "timeline": [
            {"step": 1, "action": "show_entity", "target": "input"},
            {"step": 2, "action": "show_entity", "target": "boundary"},
            {"step": 3, "action": "connect", "from": "input", "to": "boundary"},
            {"step": 4, "action": "show_entity", "target": "acceptance"},
        ],
        "layout": "从左到右的流程结构",
        "motion": "实体依次通过 transform 进入，连线通过 opacity 出现。",
        "interaction": "点击步骤按钮切换当前实体。",
        "success_check": ["DOM 中包含需求输入", "DOM 中包含边界判断", "DOM 中包含验收项"],
        "placement_hint": "放在步骤讲解第一段之后",
    }


def test_section_markdown_output_requires_structured_source_references_and_briefs() -> None:
    markdown = SectionMarkdownOutput(
        section_id="1.1",
        parent_section_id="1",
        title="学习目标",
        markdown=_complete_markdown(),
        source_references=[_source_reference()],
        video_briefs=[_paragraph_bound_video_brief()],
        animation_briefs=[_simulation_animation_brief()],
    )

    assert markdown.source_references[0].textbook_id == "textbook-ai-web"
    assert markdown.video_briefs[0].target_markdown_heading == "核心概念"
    assert markdown.animation_briefs[0].simulation_type == "process_boundary_flow"


def test_section_markdown_output_rejects_generic_video_brief() -> None:
    brief = _paragraph_bound_video_brief()
    brief["purpose"] = "帮助理解本节内容"

    with pytest.raises(ValidationError) as exc_info:
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown=_complete_markdown(),
            source_references=[_source_reference()],
            video_briefs=[brief],
            animation_briefs=[_simulation_animation_brief()],
        )

    assert "video brief purpose is too generic" in str(exc_info.value)


def test_section_markdown_output_rejects_animation_without_visual_model() -> None:
    brief = _simulation_animation_brief()
    brief.pop("visual_model")

    with pytest.raises(ValidationError) as exc_info:
        SectionMarkdownOutput(
            section_id="1.1",
            parent_section_id="1",
            title="学习目标",
            markdown=_complete_markdown(),
            source_references=[_source_reference()],
            video_briefs=[_paragraph_bound_video_brief()],
            animation_briefs=[brief],
        )

    assert "Field required" in str(exc_info.value)
```

- [ ] **Step 2: Run model tests to verify they fail**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_agent_contract_models.py::test_section_markdown_output_requires_structured_source_references_and_briefs tests/test_agent_contract_models.py::test_section_markdown_output_rejects_generic_video_brief tests/test_agent_contract_models.py::test_section_markdown_output_rejects_animation_without_visual_model -q
```

Expected: FAIL because these fields do not exist yet.

- [ ] **Step 3: Implement model classes and validators**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/models.py`, add these classes above `SectionVideoBriefOutput`:

```python
class SectionSourceReferenceOutput(BaseModel):
    textbook_id: str = Field(description="教材 ID")
    textbook_title: str = Field(description="教材标题")
    section_id: str = Field(description="教材小节 ID")
    section_title: str = Field(description="教材小节标题")
    evidence_summary: str = Field(description="教材依据摘要")
    content_char_count: int = Field(ge=0, description="教材正文字符数")

    @field_validator(
        "textbook_id",
        "textbook_title",
        "section_id",
        "section_title",
        "evidence_summary",
    )
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)


class AnimationVisualEntityOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(description="视觉对象 ID")
    kind: str = Field(description="视觉对象类型")

    @field_validator("id", "kind")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)


class AnimationVisualRelationOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_: str = Field(alias="from", description="关系起点")
    to: str = Field(description="关系终点")
    kind: str = Field(description="关系类型")

    @field_validator("from_", "to", "kind")
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)


class AnimationVisualModelOutput(BaseModel):
    entities: list[AnimationVisualEntityOutput] = Field(min_length=1)
    relations: list[AnimationVisualRelationOutput] = Field(default_factory=list)


class AnimationTimelineStepOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    step: int = Field(ge=1)
    action: str = Field(description="动作类型")
    target: str = Field(default="", description="动作目标")

    @field_validator("action")
    @classmethod
    def require_action(cls, value: str) -> str:
        return _required_text(value, "action")
```

Replace `SectionVideoBriefOutput` with:

```python
class SectionVideoBriefOutput(BaseModel):
    video_id: str = Field(description="视频 brief ID")
    title: str = Field(description="视频检索标题")
    target_markdown_heading: str = Field(description="服务的 Markdown 二级标题")
    target_paragraph_summary: str = Field(description="服务的正文段落摘要")
    search_terms: list[str] = Field(min_length=3, description="检索关键词")
    purpose: str = Field(description="视频用途说明")

    @field_validator(
        "video_id",
        "title",
        "target_markdown_heading",
        "target_paragraph_summary",
        "purpose",
    )
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator("search_terms")
    @classmethod
    def require_search_terms(cls, value: list[str]) -> list[str]:
        terms = [_required_text(item, "search_terms") for item in value]
        if len(terms) < 3:
            raise ValueError("search_terms must contain at least three items")
        return terms

    @model_validator(mode="after")
    def reject_generic_purpose(self) -> "SectionVideoBriefOutput":
        if self.purpose.strip() in {"帮助理解本节内容", "辅助理解本节内容"}:
            raise ValueError("video brief purpose is too generic")
        return self
```

Replace `SectionAnimationBriefOutput` with a model that includes the simulation fields:

```python
class SectionAnimationBriefOutput(BaseModel):
    animation_id: str = Field(description="动画 brief ID")
    title: str = Field(description="动画标题")
    target_markdown_heading: str = Field(description="服务的 Markdown 二级标题")
    target_paragraph_summary: str = Field(description="服务的正文段落摘要")
    concept: str = Field(description="动画展示的具体概念")
    simulation_type: str = Field(description="模拟类型")
    visual_elements: list[str] = Field(description="必须出现的视觉对象")
    visual_model: AnimationVisualModelOutput
    timeline: list[AnimationTimelineStepOutput] = Field(min_length=1)
    layout: str = Field(description="布局要求")
    motion: str = Field(description="运动要求")
    interaction: str = Field(description="交互要求")
    success_check: list[str] = Field(min_length=1)
    placement_hint: str = Field(description="插入位置")

    @field_validator(
        "animation_id",
        "title",
        "target_markdown_heading",
        "target_paragraph_summary",
        "concept",
        "simulation_type",
        "layout",
        "motion",
        "interaction",
        "placement_hint",
    )
    @classmethod
    def require_text_field(cls, value: str, info) -> str:
        return _required_text(value, info.field_name)

    @field_validator("visual_elements", "success_check")
    @classmethod
    def require_text_list(cls, value: list[str], info) -> list[str]:
        items = [_required_text(item, info.field_name) for item in value]
        if not items:
            raise ValueError(f"{info.field_name} must not be empty")
        return items

    @model_validator(mode="after")
    def reject_text_only_animation_plan(self) -> "SectionAnimationBriefOutput":
        generic_titles = {"流程动画", "理解本节内容", "教学动画"}
        if self.title.strip() in generic_titles or self.concept.strip() in generic_titles:
            raise ValueError("animation brief is too generic")
        if len(self.visual_model.entities) < 2:
            raise ValueError("animation visual_model must contain at least two entities")
        return self
```

Add `source_references` to `SectionMarkdownOutput`:

```python
    source_references: list[SectionSourceReferenceOutput] = Field(default_factory=list)
```

Inside `validate_resource_contract`, before video checks:

```python
        if not self.source_references:
            raise ValueError("source_references must contain at least one item")
```

- [ ] **Step 4: Run model tests to verify they pass**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_agent_contract_models.py::test_section_markdown_output_requires_structured_source_references_and_briefs tests/test_agent_contract_models.py::test_section_markdown_output_rejects_generic_video_brief tests/test_agent_contract_models.py::test_section_markdown_output_rejects_animation_without_visual_model -q
```

Expected: PASS.

### Task 2: Build Source References From Section Bindings

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing helper tests**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def test_source_references_are_built_from_section_source_binding() -> None:
    from app.orchestration.agents.course_resources.common import _source_references_for_section

    refs = _source_references_for_section(
        {
            "source_textbook_id": "textbook-data-structures",
            "source_textbook_title": "数据结构教程",
            "source_section_ids": ["2.3"],
            "source_section_titles": ["单链表"],
            "source_content_chars": 842,
        }
    )

    assert refs == [
        {
            "textbook_id": "textbook-data-structures",
            "textbook_title": "数据结构教程",
            "section_id": "2.3",
            "section_title": "单链表",
            "evidence_summary": "依据《数据结构教程》2.3 单链表 的教材内容生成。",
            "content_char_count": 842,
        }
    ]
```

- [ ] **Step 2: Run helper test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_source_references_are_built_from_section_source_binding -q
```

Expected: FAIL because `_source_references_for_section` does not exist.

- [ ] **Step 3: Implement helper**

Add to `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py` near `_text_items` helpers:

```python
def _source_references_for_section(section: dict) -> list[dict]:
    textbook_id = _clean_text(section.get("source_textbook_id"))
    textbook_title = _clean_text(section.get("source_textbook_title"))
    section_ids = _text_items(section.get("source_section_ids"))
    section_titles = _text_items(section.get("source_section_titles"))
    content_chars = section.get("source_content_chars")
    try:
        content_char_count = int(content_chars)
    except (TypeError, ValueError):
        content_char_count = 0
    if not textbook_id or not textbook_title or not section_ids:
        return []

    refs: list[dict] = []
    for index, source_section_id in enumerate(section_ids):
        source_section_title = (
            section_titles[index] if index < len(section_titles) else source_section_id
        )
        refs.append(
            {
                "textbook_id": textbook_id,
                "textbook_title": textbook_title,
                "section_id": source_section_id,
                "section_title": source_section_title,
                "evidence_summary": (
                    f"依据《{textbook_title}》{source_section_id} "
                    f"{source_section_title} 的教材内容生成。"
                ),
                "content_char_count": content_char_count,
            }
        )
    return refs
```

- [ ] **Step 4: Run helper test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_source_references_are_built_from_section_source_binding -q
```

Expected: PASS.

### Task 3: Generate Paragraph-Bound Video Briefs And Simulation-First Animation Briefs

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Replace the existing generated brief test**

Update `test_generated_markdown_briefs_use_specific_data_structure_visual_plan` in `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py` to assert the new fields:

```python
def test_generated_markdown_briefs_use_specific_data_structure_visual_plan() -> None:
    from app.orchestration.agents.course_resources.common import (
        _generated_markdown_seed_data,
    )

    section = {
        "section_id": "2.3",
        "title": "单链表",
        "description": "讲解节点通过指针串联的线性结构。",
        "key_knowledge_points": ["节点", "指针", "插入删除"],
        "source_section_titles": ["链表的存储结构"],
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教程",
        "source_section_ids": ["2.3"],
        "source_content_chars": 842,
    }

    seed_data = _generated_markdown_seed_data(section)

    video_brief = seed_data["video_briefs"][0]
    animation_brief = seed_data["animation_briefs"][0]
    assert seed_data["source_references"][0]["textbook_id"] == "textbook-data-structures"
    assert video_brief["target_markdown_heading"] == "核心概念"
    assert video_brief["target_paragraph_summary"] == "解释单链表节点由 data 和 next 组成，next 指向下一个节点。"
    assert video_brief["search_terms"] == ["单链表", "节点", "next 指针", "链式存储"]
    assert animation_brief["simulation_type"] == "data_structure_linked_list"
    assert animation_brief["visual_model"]["entities"] == [
        {"id": "head", "kind": "pointer", "label": "head"},
        {"id": "node_1", "kind": "node", "fields": ["data", "next"]},
        {"id": "node_2", "kind": "node", "fields": ["data", "next"]},
        {"id": "none", "kind": "terminal", "label": "None"},
    ]
    assert animation_brief["visual_model"]["relations"] == [
        {"from": "head", "to": "node_1", "kind": "points_to"},
        {"from": "node_1.next", "to": "node_2", "kind": "points_to"},
        {"from": "node_2.next", "to": "none", "kind": "points_to"},
    ]
    assert animation_brief["timeline"][-1] == {
        "step": 6,
        "action": "connect",
        "from": "node_2.next",
        "to": "none",
    }
```

- [ ] **Step 2: Run brief test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_generated_markdown_briefs_use_specific_data_structure_visual_plan -q
```

Expected: FAIL until generated briefs include the new fields.

- [ ] **Step 3: Update generated seed data in both helper locations**

In both files:

- `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`
- `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`

Update `_generated_markdown_video_briefs` linked-list branch to return:

```python
        return [
            {
                "video_id": "video_1",
                "title": f"{title}节点与指针讲解视频",
                "target_markdown_heading": "核心概念",
                "target_paragraph_summary": "解释单链表节点由 data 和 next 组成，next 指向下一个节点。",
                "search_terms": ["单链表", "节点", "next 指针", "链式存储"],
                "purpose": f"辅助理解「{title}」中节点、data 域、next 指针、头指针与尾节点 None 如何共同构成线性结构。",
            }
        ]
```

Update the default video branch to include `target_markdown_heading`, `target_paragraph_summary`, and `search_terms`:

```python
            {
                "video_id": "video_1",
                "title": f"{title}专项讲解视频",
                "target_markdown_heading": "核心概念",
                "target_paragraph_summary": f"解释「{title}」中{focus}与学习任务之间的关系。",
                "search_terms": [term for term in [title, *focus_terms] if term][:4],
                "purpose": f"帮助学习者围绕「{title}」理解{focus}，并把本节内容落到可验收任务。",
            }
```

Update `_generated_markdown_animation_briefs` linked-list branch to return the full simulation contract from the approved spec:

```python
        return [
            {
                "animation_id": "anim_1",
                "title": f"{title}节点指针串联动画",
                "target_markdown_heading": "步骤讲解",
                "target_paragraph_summary": "解释单链表由节点组成，每个节点包含 data 和 next，next 指向下一个节点，尾节点指向 None。",
                "concept": f"展示「{title}」中节点通过 next 指针串联，头指针指向首节点，尾节点 next 指向 None 的结构。",
                "simulation_type": "data_structure_linked_list",
                "visual_elements": [
                    "头指针",
                    "节点(data,next)",
                    "next 指针",
                    "尾节点 None",
                ],
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
                    {"step": 4, "action": "show_entity", "target": "node_2"},
                    {"step": 5, "action": "connect", "from": "node_1.next", "to": "node_2"},
                    {"step": 6, "action": "connect", "from": "node_2.next", "to": "none"},
                ],
                "layout": "横向链式结构",
                "motion": "头指针先出现，节点依次通过 transform 从左到右进入，next 指针连线按顺序绘制，尾节点 None 最后淡入。",
                "interaction": "点击步骤按钮切换当前构建步骤。",
                "success_check": ["DOM 中包含头指针", "DOM 中包含 next 指针", "DOM 中包含 None", "至少 2 个节点可见"],
                "placement_hint": "步骤讲解中第一次解释节点指针关系之后。",
            }
        ]
```

Update the default animation branch to include the same required keys with `simulation_type="concept_process_flow"`, a three-entity visual model, four timeline steps, and a non-generic `success_check`.

Update `_generated_markdown_seed_data` to include:

```python
        "source_references": _source_references_for_section(section),
```

- [ ] **Step 4: Run brief test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_generated_markdown_briefs_use_specific_data_structure_visual_plan -q
```

Expected: PASS.

### Task 4: Enforce Markdown Quality Gate For Sources And Briefs

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing quality tests**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def test_markdown_quality_blocks_generic_resource_briefs() -> None:
    section = {
        "section_id": "1.1",
        "title": "复杂度分析",
        "description": "判断算法开销。",
        "key_knowledge_points": ["时间复杂度"],
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教程",
        "source_section_ids": ["1.1"],
        "source_section_titles": ["复杂度分析"],
    }
    markdown = _complete_section_markdown("1.1", "复杂度分析")

    issue = _markdown_quality_issue(
        markdown,
        section,
        [
            {
                "video_id": "video_1",
                "title": "复杂度分析视频",
                "target_markdown_heading": "核心概念",
                "target_paragraph_summary": "",
                "search_terms": ["复杂度", "时间复杂度", "算法开销"],
                "purpose": "帮助理解本节内容",
            }
        ],
        [
            {
                "animation_id": "anim_1",
                "title": "流程动画",
                "target_markdown_heading": "步骤讲解",
                "target_paragraph_summary": "展示输入规模和操作次数的关系。",
                "concept": "流程动画",
                "simulation_type": "",
                "visual_elements": ["输入规模", "操作次数"],
                "visual_model": {"entities": [], "relations": []},
                "timeline": [],
                "success_check": [],
            }
        ],
    )

    assert issue == "Markdown resource briefs are too generic."
```

- [ ] **Step 2: Run quality test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_markdown_quality_blocks_generic_resource_briefs -q
```

Expected: FAIL until `_markdown_quality_issue` validates the richer brief contract.

- [ ] **Step 3: Add brief quality helpers**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`, add:

```python
def _resource_briefs_are_specific(
    video_briefs: object, animation_briefs: object, markdown: str
) -> bool:
    headings = {match.group(1).strip() for match in _MARKDOWN_HEADING_PATTERN.finditer(markdown)}
    if not isinstance(video_briefs, list) or not isinstance(animation_briefs, list):
        return False
    for brief in video_briefs:
        if not isinstance(brief, dict):
            return False
        purpose = _clean_text(brief.get("purpose"))
        if purpose in {"帮助理解本节内容", "辅助理解本节内容"}:
            return False
        if _clean_text(brief.get("target_markdown_heading")) not in headings:
            return False
        if not _clean_text(brief.get("target_paragraph_summary")):
            return False
        if len(_text_items(brief.get("search_terms"))) < 3:
            return False
    for brief in animation_briefs:
        if not isinstance(brief, dict):
            return False
        if _clean_text(brief.get("title")) in {"流程动画", "教学动画"}:
            return False
        if _clean_text(brief.get("target_markdown_heading")) not in headings:
            return False
        if not _clean_text(brief.get("target_paragraph_summary")):
            return False
        if not _clean_text(brief.get("simulation_type")):
            return False
        visual_model = brief.get("visual_model")
        if not isinstance(visual_model, dict) or not isinstance(visual_model.get("entities"), list) or not visual_model.get("entities"):
            return False
        if not isinstance(brief.get("timeline"), list) or not brief.get("timeline"):
            return False
        if not _text_items(brief.get("success_check")):
            return False
    return True
```

Inside `_markdown_quality_issue`, before the source footer check:

```python
    if not _resource_briefs_are_specific(video_briefs, animation_briefs, text):
        return "Markdown resource briefs are too generic."
```

- [ ] **Step 4: Run quality test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_markdown_quality_blocks_generic_resource_briefs -q
```

Expected: PASS.

### Task 5: Normalize Markdown Outputs With Source References

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing normalization test**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def test_normalized_markdown_resources_preserve_source_references() -> None:
    from app.orchestration.agents.course_resources.markdown import _normalize_markdown_resources

    section = {
        "section_id": "2.3",
        "parent_section_id": "2",
        "title": "单链表",
        "source_textbook_id": "textbook-data-structures",
        "source_textbook_title": "数据结构教程",
        "source_section_ids": ["2.3"],
        "source_section_titles": ["单链表"],
        "source_content_chars": 842,
    }
    normalized = _normalize_markdown_resources(
        {
            "section_id": "2.3",
            "title": "单链表",
            "markdown": _complete_section_markdown("2.3", "单链表"),
            "video_briefs": [],
            "animation_briefs": [],
        },
        section,
    )

    assert normalized["source_references"][0]["section_id"] == "2.3"
    assert normalized["markdown"].rstrip().endswith("## 来源\n- 《数据结构教程》：2.3 单链表。")
```

- [ ] **Step 2: Run normalization test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_normalized_markdown_resources_preserve_source_references -q
```

Expected: FAIL until normalization stores `source_references`.

- [ ] **Step 3: Update `_normalize_markdown_resources`**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`, import `_source_references_for_section` from common.

Inside `_normalize_markdown_resources`, set:

```python
    source_references = markdown_data.get("source_references")
    if not isinstance(source_references, list) or not source_references:
        source_references = _source_references_for_section(section)
```

Add `"source_references": source_references` to the returned dict.

- [ ] **Step 4: Run normalization test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_normalized_markdown_resources_preserve_source_references -q
```

Expected: PASS.

### Task 6: Format, Run Phase Tests, Commit

**Files:**
- All files changed in this phase.

- [ ] **Step 1: Run Ruff**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run ruff check --fix app/orchestration/agents/models.py app/orchestration/agents/course_resources/common.py app/orchestration/agents/course_resources/markdown.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/agents/models.py app/orchestration/agents/course_resources/common.py app/orchestration/agents/course_resources/markdown.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py
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
git add backend/app/orchestration/agents/models.py backend/app/orchestration/agents/course_resources/common.py backend/app/orchestration/agents/course_resources/markdown.py backend/tests/test_agent_contract_models.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: strengthen markdown resource planning"
```

Expected: commit succeeds.
