# Events Recovery Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize stream events, add section-phase recovery checkpoints, and record compact traces without logging full教材正文, Markdown, or HTML.

**Architecture:** Add three small modules: `events.py`, `recovery.py`, and `observability.py`. Wire `stream_chapter_resource_generation` through these helpers while preserving current async phase ordering.

**Tech Stack:** Python 3.12, dataclasses, datetime, asyncio stream tests, pytest, Ruff.

---

### Task 1: Add Unified Event Builder

**Files:**
- Create: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/events.py`
- Create: `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`

- [ ] **Step 1: Write failing event tests**

Create `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`:

```python
from __future__ import annotations

from app.orchestration.contracts import quality_passed
from app.orchestration.events import build_agent_event


def test_build_agent_event_includes_order_dependencies_refs_and_quality() -> None:
    event = build_agent_event(
        event="agent_result",
        agent="section_markdown_agent",
        phase="markdown",
        status="completed",
        step_id="leaf-section-1.1-markdown",
        message="Markdown completed",
        depends_on=["course_knowledge_agent"],
        input_refs={
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "source_section_ids": ["2.3"],
        },
        output_refs={
            "section_markdown_id": "1.1",
            "video_brief_ids": ["video_1"],
            "animation_brief_ids": ["anim_1"],
        },
        quality_result=quality_passed(),
    )

    assert event == {
        "event": "agent_result",
        "agent": "section_markdown_agent",
        "agent_order": 5,
        "phase": "markdown",
        "status": "completed",
        "stepId": "leaf-section-1.1-markdown",
        "depends_on": ["course_knowledge_agent"],
        "input_refs": {
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "source_section_ids": ["2.3"],
        },
        "output_refs": {
            "section_markdown_id": "1.1",
            "video_brief_ids": ["video_1"],
            "animation_brief_ids": ["anim_1"],
        },
        "quality_result": {
            "passed": True,
            "severity": "informational",
            "reason": "",
            "checks": [],
        },
        "message": "Markdown completed",
    }
```

- [ ] **Step 2: Run event test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py::test_build_agent_event_includes_order_dependencies_refs_and_quality -q
```

Expected: FAIL because `app.orchestration.events` does not exist.

- [ ] **Step 3: Implement event builder**

Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/events.py`:

```python
from __future__ import annotations

from app.orchestration.contracts import AgentName, PhaseName, QualityResult, agent_order


def build_agent_event(
    *,
    event: str,
    agent: AgentName,
    phase: PhaseName,
    status: str,
    step_id: str,
    message: str = "",
    depends_on: list[AgentName] | None = None,
    input_refs: dict | None = None,
    output_refs: dict | None = None,
    quality_result: QualityResult | dict | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        "event": event,
        "agent": agent,
        "agent_order": agent_order(agent),
        "phase": phase,
        "status": status,
        "stepId": step_id,
        "depends_on": depends_on or [],
        "input_refs": input_refs or {},
        "output_refs": output_refs or {},
        "quality_result": _quality_payload(quality_result),
    }
    if message:
        payload["message"] = message
    if extra:
        payload.update(extra)
    return payload


def _quality_payload(value: QualityResult | dict | None) -> dict | None:
    if value is None:
        return None
    if isinstance(value, QualityResult):
        return value.to_dict()
    return value
```

- [ ] **Step 4: Run event test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py::test_build_agent_event_includes_order_dependencies_refs_and_quality -q
```

Expected: PASS.

### Task 2: Add Recovery Checkpoint Helpers

**Files:**
- Create: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/recovery.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`

- [ ] **Step 1: Add failing recovery tests**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`:

```python
from app.orchestration.recovery import (
    checkpoint_for_phase,
    section_phase_completed,
    update_section_phase_checkpoint,
)


def test_update_section_phase_checkpoint_writes_outline_json_without_losing_existing_phases() -> None:
    outline = {
        "section_resource_checkpoints": {
            "1.1": {
                "markdown": {
                    "status": "completed",
                    "updated_at": "2026-07-02T00:00:00+00:00",
                    "output_refs": {"section_markdown_id": "1.1"},
                    "quality_result": {"passed": True},
                }
            }
        }
    }

    updated = update_section_phase_checkpoint(
        outline,
        section_id="1.1",
        phase="video",
        status="unavailable",
        output_refs={"video_brief_ids": ["video_1"]},
        quality_result={"passed": False, "severity": "informational", "reason": "未找到合格视频"},
        failure_reason="未找到合格视频",
        updated_at="2026-07-02T01:00:00+00:00",
    )

    assert updated is not outline
    assert section_phase_completed(updated, "1.1", "markdown") is True
    assert checkpoint_for_phase(updated, "1.1", "video") == {
        "status": "unavailable",
        "updated_at": "2026-07-02T01:00:00+00:00",
        "output_refs": {"video_brief_ids": ["video_1"]},
        "quality_result": {
            "passed": False,
            "severity": "informational",
            "reason": "未找到合格视频",
        },
        "failure_reason": "未找到合格视频",
    }
```

- [ ] **Step 2: Run recovery test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py::test_update_section_phase_checkpoint_writes_outline_json_without_losing_existing_phases -q
```

Expected: FAIL because recovery helpers do not exist.

- [ ] **Step 3: Implement recovery helpers**

Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/recovery.py`:

```python
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.orchestration.contracts import PhaseName


def checkpoint_for_phase(outline: dict, section_id: str, phase: PhaseName) -> dict:
    checkpoints = outline.get("section_resource_checkpoints")
    if not isinstance(checkpoints, dict):
        return {}
    section_checkpoints = checkpoints.get(section_id)
    if not isinstance(section_checkpoints, dict):
        return {}
    value = section_checkpoints.get(phase)
    return value if isinstance(value, dict) else {}


def section_phase_completed(outline: dict, section_id: str, phase: PhaseName) -> bool:
    return checkpoint_for_phase(outline, section_id, phase).get("status") == "completed"


def update_section_phase_checkpoint(
    outline: dict,
    *,
    section_id: str,
    phase: PhaseName,
    status: str,
    output_refs: dict | None = None,
    quality_result: dict | None = None,
    failure_reason: str = "",
    updated_at: str | None = None,
) -> dict:
    updated = deepcopy(outline)
    checkpoints = updated.setdefault("section_resource_checkpoints", {})
    section_checkpoints = checkpoints.setdefault(section_id, {})
    phase_checkpoint = {
        "status": status,
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
        "output_refs": output_refs or {},
        "quality_result": quality_result or {},
    }
    if failure_reason:
        phase_checkpoint["failure_reason"] = failure_reason
    section_checkpoints[phase] = phase_checkpoint
    return updated
```

- [ ] **Step 4: Run recovery test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py::test_update_section_phase_checkpoint_writes_outline_json_without_losing_existing_phases -q
```

Expected: PASS.

### Task 3: Add Compact Trace Builder

**Files:**
- Create: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/observability.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`

- [ ] **Step 1: Add failing trace test**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`:

```python
from app.orchestration.observability import build_agent_trace


def test_trace_builder_records_compact_summaries_without_full_content() -> None:
    trace = build_agent_trace(
        trace_id="session-1:year_3_course_1:1.1:animation",
        agent="section_html_animation_agent",
        phase="animation",
        started_at_ms=1000,
        ended_at_ms=2450,
        input_summary={
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "brief_ids": ["anim_1"],
            "simulation_type": "data_structure_linked_list",
            "evidence_text": "教材完整正文不应进入 trace",
        },
        output_summary={
            "status": "available",
            "html": "<section>完整 HTML 不应进入 trace</section>",
            "html_length": 12840,
            "quality_passed": True,
        },
        failure_reason="",
    )

    assert trace == {
        "trace_id": "session-1:year_3_course_1:1.1:animation",
        "agent": "section_html_animation_agent",
        "phase": "animation",
        "duration_ms": 1450,
        "input_summary": {
            "course_id": "year_3_course_1",
            "section_id": "1.1",
            "source_textbook_id": "textbook-data-structures",
            "brief_ids": ["anim_1"],
            "simulation_type": "data_structure_linked_list",
        },
        "output_summary": {
            "status": "available",
            "html_length": 12840,
            "quality_passed": True,
        },
        "failure_reason": "",
    }
```

- [ ] **Step 2: Run trace test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py::test_trace_builder_records_compact_summaries_without_full_content -q
```

Expected: FAIL because trace helper does not exist.

- [ ] **Step 3: Implement trace builder**

Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/observability.py`:

```python
from __future__ import annotations

from app.orchestration.contracts import AgentName, PhaseName

_BLOCKED_TRACE_KEYS = {
    "evidence_text",
    "markdown",
    "html",
    "previous_html",
    "textbook_evidence_pack",
}


def _compact_mapping(value: dict) -> dict:
    compact: dict = {}
    for key, item in value.items():
        if key in _BLOCKED_TRACE_KEYS:
            continue
        if isinstance(item, str) and len(item) > 500:
            compact[f"{key}_length"] = len(item)
            continue
        compact[key] = item
    return compact


def build_agent_trace(
    *,
    trace_id: str,
    agent: AgentName,
    phase: PhaseName,
    started_at_ms: int,
    ended_at_ms: int,
    input_summary: dict,
    output_summary: dict,
    failure_reason: str = "",
) -> dict:
    return {
        "trace_id": trace_id,
        "agent": agent,
        "phase": phase,
        "duration_ms": max(0, ended_at_ms - started_at_ms),
        "input_summary": _compact_mapping(input_summary),
        "output_summary": _compact_mapping(output_summary),
        "failure_reason": failure_reason,
    }
```

- [ ] **Step 4: Run trace test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py::test_trace_builder_records_compact_summaries_without_full_content -q
```

Expected: PASS.

### Task 4: Wire Stream Events And Recovery Into Chapter Resource Generation

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/main.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Strengthen stream event test**

Update `test_stream_chapter_resource_generation_reports_agent_phases_in_order` in `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py` so it asserts the unified schema:

```python
def test_stream_chapter_resource_generation_reports_agent_phases_in_order(monkeypatch) -> None:
    events = asyncio.run(_collect_stream_events(monkeypatch))
    agent_events = [
        event
        for event in events
        if event.get("event") in {"agent_progress", "agent_result"}
        and event.get("agent")
        in {
            "section_markdown_agent",
            "section_video_search_agent",
            "section_html_animation_agent",
        }
    ]

    assert [event["phase"] for event in agent_events] == [
        "markdown",
        "markdown",
        "video",
        "video",
        "animation",
        "animation",
    ]
    assert [event["agent_order"] for event in agent_events] == [5, 5, 6, 6, 7, 7]
    for event in agent_events:
        assert "depends_on" in event
        assert "input_refs" in event
        assert "output_refs" in event
        assert "quality_result" in event
```

- [ ] **Step 2: Run stream event test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_stream_chapter_resource_generation_reports_agent_phases_in_order -q
```

Expected: FAIL until `main.py` uses `build_agent_event`.

- [ ] **Step 3: Replace event dictionaries in `main.py`**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/main.py`, import:

```python
from app.orchestration.contracts import quality_passed
from app.orchestration.events import build_agent_event
from app.orchestration.recovery import update_section_phase_checkpoint
```

Replace each section-level `yield { ... }` for Markdown, video, and animation with `build_agent_event`.

For Markdown running:

```python
        yield build_agent_event(
            event="agent_progress",
            agent="section_markdown_agent",
            phase="markdown",
            status="running",
            step_id=f"leaf-section-{section_id}-markdown",
            message="正在基于教材证据生成小节 Markdown 与资源规划",
            depends_on=["course_knowledge_agent"],
            input_refs={"course_id": course_id, "section_id": section_id},
            extra={
                "kind": "course_resource_section",
                "label": f"{section_id} 文案",
                "course_id": course_id,
                "chapter_section_id": chapter_section_id,
                "section_id": section_id,
            },
        )
```

For each completed phase, set `quality_result=quality_passed()` and fill `output_refs` with the IDs present in the outline value. After `state.update(markdown_result)`, update checkpoints for each section:

```python
        updated_outline = update_section_phase_checkpoint(
            state["course_knowledge"],
            section_id=section_id,
            phase="markdown",
            status="completed",
            output_refs={"section_markdown_id": section_id},
            quality_result=quality_passed().to_dict(),
        )
        state["course_knowledge"] = updated_outline
```

Repeat for video with status `"completed"` if `section_video_links[section_id].status != "unavailable"` else `"unavailable"`, and for animation with `"completed"`.

- [ ] **Step 4: Run stream event test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_course_resource_agent_contract.py::test_stream_chapter_resource_generation_reports_agent_phases_in_order -q
```

Expected: PASS.

### Task 5: Format, Run Phase Tests, Commit

**Files:**
- All files changed in this phase.

- [ ] **Step 1: Run Ruff**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run ruff check --fix app/orchestration/events.py app/orchestration/recovery.py app/orchestration/observability.py app/orchestration/agents/course_resources/main.py tests/test_orchestration_event_recovery_observability.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/events.py app/orchestration/recovery.py app/orchestration/observability.py app/orchestration/agents/course_resources/main.py tests/test_orchestration_event_recovery_observability.py tests/test_course_resource_agent_contract.py
```

Expected: commands complete successfully.

- [ ] **Step 2: Run phase tests**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_event_recovery_observability.py tests/test_course_resource_agent_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent
git add backend/app/orchestration/events.py backend/app/orchestration/recovery.py backend/app/orchestration/observability.py backend/app/orchestration/agents/course_resources/main.py backend/tests/test_orchestration_event_recovery_observability.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: add resource event recovery traces"
```

Expected: commit succeeds.
