# Prompt Budget Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prompt character budgets, ensure only Markdown receives full textbook evidence正文, and finish with a cross-agent regression contract.

**Architecture:** Add `prompt_budget.py` as a deterministic trimming helper and apply it at existing prompt builders. Keep current async concurrency unchanged and validate the entire chain with focused tests.

**Tech Stack:** Python 3.12, pytest, Ruff.

---

### Task 1: Add Prompt Budget Helper

**Files:**
- Create: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/prompt_budget.py`
- Create: `/Users/torch/torch/opt/mutiagent/backend/tests/test_prompt_budget.py`

- [ ] **Step 1: Write failing prompt budget tests**

Create `/Users/torch/torch/opt/mutiagent/backend/tests/test_prompt_budget.py`:

```python
from __future__ import annotations

from app.orchestration.prompt_budget import (
    PHASE_PROMPT_LIMITS,
    apply_prompt_budget,
)


def test_phase_prompt_limits_match_resource_contract() -> None:
    assert PHASE_PROMPT_LIMITS == {
        "intake": 8000,
        "path": 12000,
        "outline": 16000,
        "markdown": 28000,
        "video": 9000,
        "animation": 12000,
    }


def test_apply_prompt_budget_preserves_current_source_binding() -> None:
    prompt = "A" * 200 + "\nSOURCE_BINDING:textbook-ai-web:2.3\n" + "B" * 200

    result = apply_prompt_budget(
        prompt,
        phase="video",
        protected_fragments=["SOURCE_BINDING:textbook-ai-web:2.3"],
        limit=120,
    )

    assert result.prompt_budget_applied is True
    assert "SOURCE_BINDING:textbook-ai-web:2.3" in result.text
    assert len(result.text) <= 120


def test_apply_prompt_budget_does_not_trim_when_under_limit() -> None:
    result = apply_prompt_budget("short prompt", phase="intake")

    assert result.prompt_budget_applied is False
    assert result.text == "short prompt"
```

- [ ] **Step 2: Run prompt budget tests to verify they fail**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_prompt_budget.py -q
```

Expected: FAIL because `prompt_budget.py` does not exist.

- [ ] **Step 3: Implement prompt budget helper**

Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/prompt_budget.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.orchestration.contracts import PhaseName

PHASE_PROMPT_LIMITS: dict[str, int] = {
    "intake": 8000,
    "path": 12000,
    "outline": 16000,
    "markdown": 28000,
    "video": 9000,
    "animation": 12000,
}


@dataclass(frozen=True)
class PromptBudgetResult:
    text: str
    prompt_budget_applied: bool
    original_chars: int
    final_chars: int


def apply_prompt_budget(
    text: str,
    *,
    phase: PhaseName,
    protected_fragments: list[str] | None = None,
    limit: int | None = None,
) -> PromptBudgetResult:
    prompt_limit = limit or PHASE_PROMPT_LIMITS.get(phase, 12000)
    if len(text) <= prompt_limit:
        return PromptBudgetResult(
            text=text,
            prompt_budget_applied=False,
            original_chars=len(text),
            final_chars=len(text),
        )

    protected = [fragment for fragment in protected_fragments or [] if fragment]
    protected_text = "\n".join(protected)
    remaining_limit = max(0, prompt_limit - len(protected_text) - 2)
    head = text[: remaining_limit // 2]
    tail = text[-(remaining_limit - len(head)) :] if remaining_limit > len(head) else ""
    trimmed = f"{head}\n{protected_text}\n{tail}".strip()
    if len(trimmed) > prompt_limit:
        trimmed = trimmed[:prompt_limit]
        for fragment in protected:
            if fragment not in trimmed:
                trimmed = (trimmed[: max(0, prompt_limit - len(fragment) - 1)] + "\n" + fragment)[
                    :prompt_limit
                ]
    return PromptBudgetResult(
        text=trimmed,
        prompt_budget_applied=True,
        original_chars=len(text),
        final_chars=len(trimmed),
    )
```

- [ ] **Step 4: Run prompt budget tests to verify they pass**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_prompt_budget.py -q
```

Expected: PASS.

### Task 2: Apply Budgets To Existing Prompt Builders

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path_intake.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_knowledge.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_intake_agent_contract.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_agent_contract.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_knowledge_agent_contract.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add focused prompt-budget assertions**

Add to `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_intake_agent_contract.py`:

```python
def test_intake_prompt_uses_outline_summaries_without_full_textbook_content() -> None:
    payload = _build_intake_generation_input(_state(), "AI 应用开发")

    assert "prompt_budget_applied" in payload
    assert "evidence_text" not in payload
```

Add to `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_agent_contract.py`:

```python
def test_learning_path_prompt_declares_prompt_budget_metadata() -> None:
    payload = _build_analysis_input(_state())

    assert "prompt_budget_applied" in payload
```

Add to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_knowledge_agent_contract.py`:

```python
def test_course_knowledge_prompt_uses_section_ids_titles_and_summaries() -> None:
    payload = _build_analysis_input(_state(), _current_course())

    assert "prompt_budget_applied" in payload
    assert "source_outline_section_ids" in payload
    assert "evidence_text" not in payload
```

Add to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def test_video_and_animation_inputs_do_not_receive_full_textbook_evidence() -> None:
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
            "animation_briefs": [_linked_list_animation_brief()],
        }
    }
    section = _section_by_id(outline, "1.1")
    assert section is not None

    video_input = _video_input({"profile": _profile()}, outline, section)
    animation_input = _animation_input({"profile": _profile()}, outline, section)

    assert "prompt_budget_applied" in video_input
    assert "prompt_budget_applied" in animation_input
    assert "textbook_evidence_pack" not in video_input
    assert "textbook_evidence_pack" not in animation_input
```

- [ ] **Step 2: Run prompt integration tests to verify they fail**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_learning_path_intake_agent_contract.py::test_intake_prompt_uses_outline_summaries_without_full_textbook_content tests/test_learning_path_agent_contract.py::test_learning_path_prompt_declares_prompt_budget_metadata tests/test_course_knowledge_agent_contract.py::test_course_knowledge_prompt_uses_section_ids_titles_and_summaries tests/test_course_resource_agent_contract.py::test_video_and_animation_inputs_do_not_receive_full_textbook_evidence -q
```

Expected: FAIL until prompt builders include budget metadata and resource inputs omit full evidence outside Markdown.

- [ ] **Step 3: Apply budget helper in prompt builders**

In each prompt-builder file, import:

```python
from app.orchestration.prompt_budget import apply_prompt_budget
```

For functions that return a string prompt, wrap the final query:

```python
    budget = apply_prompt_budget(
        query,
        phase="video",
        protected_fragments=[
            _clean_text(section.get("source_textbook_id")),
            "、".join(_text_items(section.get("source_section_ids"))),
        ],
    )
    return f"{budget.text}\n\nprompt_budget_applied={str(budget.prompt_budget_applied).lower()}"
```

Use phase values exactly:

- `learning_path_intake.py`: `"intake"`
- `learning_path.py`: `"path"`
- `course_knowledge.py`: `"outline"`
- `common.py` `_markdown_input`: `"markdown"`
- `video.py` `_video_input`: `"video"`
- `animation.py` `_animation_input`: `"animation"`

For video and animation inputs, ensure the payload uses only `section_markdown.source_references`, `video_briefs`, `animation_briefs`, `target_paragraph_summary`, and section IDs. Do not include `textbook_evidence_pack` in those payloads.

- [ ] **Step 4: Run prompt integration tests to verify they pass**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_learning_path_intake_agent_contract.py::test_intake_prompt_uses_outline_summaries_without_full_textbook_content tests/test_learning_path_agent_contract.py::test_learning_path_prompt_declares_prompt_budget_metadata tests/test_course_knowledge_agent_contract.py::test_course_knowledge_prompt_uses_section_ids_titles_and_summaries tests/test_course_resource_agent_contract.py::test_video_and_animation_inputs_do_not_receive_full_textbook_evidence -q
```

Expected: PASS.

### Task 3: Add End-To-End Contract Regression

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add failing cross-agent contract test**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`:

```python
def test_cross_agent_contract_preserves_source_and_briefs_through_compose() -> None:
    source_textbook_id = "textbook-data-structures"
    source_section_ids = ["2.3"]
    section = {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "单链表",
        "description": "讲解节点通过指针串联的线性结构。",
        "key_knowledge_points": ["节点", "指针", "插入删除"],
        "source_textbook_id": source_textbook_id,
        "source_textbook_title": "数据结构教程",
        "source_section_ids": source_section_ids,
        "source_section_titles": ["单链表"],
        "source_content_chars": 842,
    }
    markdown_data = _generated_markdown_seed_data(section)
    markdown_data["markdown"] = _complete_section_markdown("1.1", "单链表")
    markdown_data["markdown"] = markdown_data["markdown"].replace(
        "<!-- animation:id=anim_1 -->",
        "<!-- animation:id=anim_1 -->",
    )
    video_links = {
        "section_id": "1.1",
        "status": "unavailable",
        "failure_reason": "未找到合格视频",
        "videos": [],
    }
    animation_html = """<!doctype html><html><head><meta charset="utf-8"></head><body>
    <section class="section-animation">
    <style>:root{--line:oklch(70% 0.1 240);}@media (prefers-reduced-motion: reduce){.section-animation *{opacity: 1 !important;transform: none !important;}}</style>
    <div class="animation-context">单链表节点通过 next 指针串联，尾节点指向 None。</div>
    <svg data-timeline="linked-list">
      <g data-entity-id="head"><text>head 头指针</text></g>
      <g data-entity-id="node_1"><text>data</text><text>next</text></g>
      <g data-entity-id="node_2"><text>data</text><text>next</text></g>
      <g data-entity-id="none"><text>None</text></g>
      <line data-relation-from="head" data-relation-to="node_1"></line>
      <line data-relation-from="node_1.next" data-relation-to="node_2"></line>
      <line data-relation-from="node_2.next" data-relation-to="none"></line>
    </svg><button data-step="1">1</button></section></body></html>"""

    assert markdown_data["source_references"][0]["textbook_id"] == source_textbook_id
    assert markdown_data["source_references"][0]["section_id"] == source_section_ids[0]
    assert markdown_data["video_briefs"][0]["target_paragraph_summary"]
    assert markdown_data["animation_briefs"][0]["visual_model"]["entities"]
    assert _normalized_animation_quality_issue(
        [{"animation_id": "anim_1", "html": animation_html}],
        markdown_data["animation_briefs"],
        section,
    ) is None

    composed = _compose_section_content(
        markdown_data,
        video_links,
        {"animations": [{"animation_id": "anim_1", "html": animation_html}]},
    )

    assert composed["source_references"][0]["textbook_id"] == source_textbook_id
    assert any(block["type"] == "video" and block["status"] == "unavailable" for block in composed["blocks"])
    assert any(block["type"] == "animation" and block["status"] == "available" for block in composed["blocks"])
```

- [ ] **Step 2: Run regression test to verify it fails or passes based on previous phase state**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_cross_agent_contract_preserves_source_and_briefs_through_compose -q
```

Expected: PASS if phases 2 and 3 are complete. If it fails, fix the exact failing contract field before continuing.

### Task 4: Full Verification

**Files:**
- All files changed across the implementation.

- [ ] **Step 1: Run Ruff across touched backend files and tests**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run ruff check --fix app/orchestration/contracts.py app/orchestration/guards.py app/orchestration/events.py app/orchestration/recovery.py app/orchestration/observability.py app/orchestration/prompt_budget.py app/orchestration/agents/prompts.py app/orchestration/agents/learning_path_intake.py app/orchestration/agents/learning_path.py app/orchestration/agents/course_knowledge.py app/orchestration/agents/course_resources/common.py app/orchestration/agents/course_resources/markdown.py app/orchestration/agents/course_resources/video.py app/orchestration/agents/course_resources/animation.py app/orchestration/agents/course_resources/main.py tests/test_orchestration_contract_guards.py tests/test_orchestration_event_recovery_observability.py tests/test_prompt_budget.py tests/test_agent_contract_models.py tests/test_agent_prompt_contracts.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/contracts.py app/orchestration/guards.py app/orchestration/events.py app/orchestration/recovery.py app/orchestration/observability.py app/orchestration/prompt_budget.py app/orchestration/agents/prompts.py app/orchestration/agents/learning_path_intake.py app/orchestration/agents/learning_path.py app/orchestration/agents/course_knowledge.py app/orchestration/agents/course_resources/common.py app/orchestration/agents/course_resources/markdown.py app/orchestration/agents/course_resources/video.py app/orchestration/agents/course_resources/animation.py app/orchestration/agents/course_resources/main.py tests/test_orchestration_contract_guards.py tests/test_orchestration_event_recovery_observability.py tests/test_prompt_budget.py tests/test_agent_contract_models.py tests/test_agent_prompt_contracts.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py
```

Expected: commands complete successfully.

- [ ] **Step 2: Run full contract regression tests**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py tests/test_orchestration_event_recovery_observability.py tests/test_prompt_budget.py tests/test_agent_contract_models.py tests/test_agent_prompt_contracts.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Run at least one API stream test**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_learning_path_api.py -q
```

Expected: PASS. If this file requires services unavailable in the local test environment, record the exact failing fixture or service message in the final implementation report and rely on the contract tests above as the local verification.

- [ ] **Step 4: Commit**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent
git add backend/app/orchestration/contracts.py backend/app/orchestration/guards.py backend/app/orchestration/events.py backend/app/orchestration/recovery.py backend/app/orchestration/observability.py backend/app/orchestration/prompt_budget.py backend/app/orchestration/agents/prompts.py backend/app/orchestration/agents/learning_path_intake.py backend/app/orchestration/agents/learning_path.py backend/app/orchestration/agents/course_knowledge.py backend/app/orchestration/agents/course_resources/common.py backend/app/orchestration/agents/course_resources/markdown.py backend/app/orchestration/agents/course_resources/video.py backend/app/orchestration/agents/course_resources/animation.py backend/app/orchestration/agents/course_resources/main.py backend/tests/test_orchestration_contract_guards.py backend/tests/test_orchestration_event_recovery_observability.py backend/tests/test_prompt_budget.py backend/tests/test_agent_contract_models.py backend/tests/test_agent_prompt_contracts.py backend/tests/test_learning_path_intake_agent_contract.py backend/tests/test_learning_path_agent_contract.py backend/tests/test_course_knowledge_agent_contract.py backend/tests/test_course_resource_agent_contract.py
git commit -m "perf: add agent prompt budgets"
```

Expected: commit succeeds.

## Self-Review

Spec coverage:

- Prompt budgets exist for intake, path, outline, Markdown, video, and animation.
- Protected source binding fragments are preserved during trimming.
- Video and animation prompt tests assert they do not receive `textbook_evidence_pack`.
- Cross-agent regression checks source IDs, paragraph-bound briefs, linked-list simulation HTML, video unavailable status, animation availability, and compose preservation.

Type consistency:

- Phase strings match `PhaseName`.
- Resource status strings match `SectionVideoSearchOutput`.
- Brief fields match the models introduced in phase 2.
