# Contract Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the shared contract layer that models agent order, phase names, quality results, resource status, and enter guards.

**Architecture:** Create `contracts.py` for shared types and `guards.py` for boundary checks. Keep guards pure and easy to unit test; agent files call them later phases.

**Tech Stack:** Python 3.12, dataclasses, typing literals, pytest, Ruff.

---

### Task 1: Add Contract Types

**Files:**
- Create: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/contracts.py`
- Test: `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_contract_guards.py`

- [ ] **Step 1: Write the failing tests**

Add this file:

```python
from __future__ import annotations

import pytest

from app.orchestration.contracts import (
    AGENT_ORDER,
    ContractError,
    QualityCheck,
    QualityResult,
    ResourceStatus,
    agent_order,
    quality_passed,
)


def test_agent_order_matches_learning_resource_pipeline() -> None:
    assert AGENT_ORDER == {
        "profile_agent": 1,
        "learning_path_intake_agent": 2,
        "learning_path_agent": 3,
        "course_knowledge_agent": 4,
        "section_markdown_agent": 5,
        "section_video_search_agent": 6,
        "section_html_animation_agent": 7,
        "compose_resource": 8,
    }
    assert agent_order("section_markdown_agent") == 5


def test_quality_result_shape_is_machine_checkable() -> None:
    result = QualityResult(
        passed=False,
        severity="blocking",
        reason="source_references is empty",
        checks=[
            QualityCheck(
                name="source_references_present",
                passed=False,
                reason="source_references is empty",
            )
        ],
    )

    assert result.to_dict() == {
        "passed": False,
        "severity": "blocking",
        "reason": "source_references is empty",
        "checks": [
            {
                "name": "source_references_present",
                "passed": False,
                "reason": "source_references is empty",
            }
        ],
    }


def test_quality_passed_helper_uses_informational_severity() -> None:
    assert quality_passed().to_dict() == {
        "passed": True,
        "severity": "informational",
        "reason": "",
        "checks": [],
    }


def test_resource_status_values_are_explicit() -> None:
    statuses: set[ResourceStatus] = {
        "available",
        "unavailable",
        "recoverable_failed",
        "blocking_failed",
    }

    assert "available" in statuses


def test_contract_error_carries_agent_phase_and_quality_result() -> None:
    quality = QualityResult(
        passed=False,
        severity="blocking",
        reason="intake is not confirmed",
    )
    error = ContractError(
        "learning_path_agent",
        "path",
        "intake is not confirmed",
        quality,
    )

    assert str(error) == "learning_path_agent:path:intake is not confirmed"
    assert error.agent == "learning_path_agent"
    assert error.phase == "path"
    assert error.quality_result is quality
```

- [ ] **Step 2: Run the contract type test to verify it fails**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py -q
```

Expected: FAIL because `app.orchestration.contracts` does not exist.

- [ ] **Step 3: Implement the contract types**

Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/contracts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AgentName = Literal[
    "profile_agent",
    "learning_path_intake_agent",
    "learning_path_agent",
    "course_knowledge_agent",
    "section_markdown_agent",
    "section_video_search_agent",
    "section_html_animation_agent",
    "compose_resource",
]

PhaseName = Literal[
    "profile",
    "intake",
    "path",
    "outline",
    "markdown",
    "video",
    "animation",
    "compose",
]

Severity = Literal["blocking", "recoverable", "informational"]
ResourceStatus = Literal[
    "available",
    "unavailable",
    "recoverable_failed",
    "blocking_failed",
]

AGENT_ORDER: dict[AgentName, int] = {
    "profile_agent": 1,
    "learning_path_intake_agent": 2,
    "learning_path_agent": 3,
    "course_knowledge_agent": 4,
    "section_markdown_agent": 5,
    "section_video_search_agent": 6,
    "section_html_animation_agent": 7,
    "compose_resource": 8,
}


@dataclass(frozen=True)
class QualityCheck:
    name: str
    passed: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True)
class QualityResult:
    passed: bool
    severity: Severity
    reason: str = ""
    checks: list[QualityCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "reason": self.reason,
            "checks": [check.to_dict() for check in self.checks],
        }


class ContractError(ValueError):
    def __init__(
        self,
        agent: AgentName,
        phase: PhaseName,
        message: str,
        quality_result: QualityResult | None = None,
    ) -> None:
        super().__init__(f"{agent}:{phase}:{message}")
        self.agent = agent
        self.phase = phase
        self.quality_result = quality_result or QualityResult(
            passed=False,
            severity="blocking",
            reason=message,
        )


def agent_order(agent: AgentName) -> int:
    return AGENT_ORDER[agent]


def quality_passed() -> QualityResult:
    return QualityResult(passed=True, severity="informational", reason="")


def blocking_quality(reason: str, checks: list[QualityCheck] | None = None) -> QualityResult:
    return QualityResult(
        passed=False,
        severity="blocking",
        reason=reason,
        checks=checks or [],
    )


def recoverable_quality(
    reason: str, checks: list[QualityCheck] | None = None
) -> QualityResult:
    return QualityResult(
        passed=False,
        severity="recoverable",
        reason=reason,
        checks=checks or [],
    )
```

- [ ] **Step 4: Run the contract type test to verify it passes**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py -q
```

Expected: PASS.

### Task 2: Add Enter Guards

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_contract_guards.py`
- Create: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/guards.py`

- [ ] **Step 1: Add failing guard tests**

Append to `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_contract_guards.py`:

```python
from app.orchestration.guards import (
    require_confirmed_intake_for_learning_path,
    require_course_source_for_course_knowledge,
    require_profile_for_intake,
    require_section_source_for_markdown,
)


def test_profile_guard_requires_basic_profile() -> None:
    require_profile_for_intake(
        {"profile": {"type": "basic_profile", "confirmed_info": {"current_grade": "大三"}}}
    )

    with pytest.raises(ContractError) as exc_info:
        require_profile_for_intake({"profile": {"type": "collecting"}})

    assert exc_info.value.agent == "learning_path_intake_agent"
    assert exc_info.value.phase == "intake"
    assert exc_info.value.quality_result.reason == "profile is not complete"


def test_learning_path_guard_requires_confirmed_intake() -> None:
    require_confirmed_intake_for_learning_path(
        {"learning_path_intake": {"status": "confirmed", "courses": []}}
    )

    with pytest.raises(ContractError) as exc_info:
        require_confirmed_intake_for_learning_path(
            {"learning_path_intake": {"status": "draft", "courses": []}}
        )

    assert exc_info.value.agent == "learning_path_agent"
    assert exc_info.value.phase == "path"
    assert exc_info.value.quality_result.reason == "learning_path_intake.status is not confirmed"


def test_course_knowledge_guard_requires_course_source_binding() -> None:
    require_course_source_for_course_knowledge(
        {
            "course_node_id": "year_3_course_1",
            "source_textbook_id": "textbook-ai-web",
            "source_outline_section_ids": ["1.1"],
        }
    )

    with pytest.raises(ContractError) as exc_info:
        require_course_source_for_course_knowledge(
            {"course_node_id": "year_3_course_1", "source_outline_section_ids": []}
        )

    assert exc_info.value.agent == "course_knowledge_agent"
    assert exc_info.value.phase == "outline"
    assert exc_info.value.quality_result.reason == "course source binding is incomplete"


def test_markdown_guard_requires_section_source_binding() -> None:
    require_section_source_for_markdown(
        {
            "section_id": "1.1",
            "source_textbook_id": "textbook-ai-web",
            "source_section_ids": ["1.1"],
        }
    )

    with pytest.raises(ContractError) as exc_info:
        require_section_source_for_markdown({"section_id": "1.1"})

    assert exc_info.value.agent == "section_markdown_agent"
    assert exc_info.value.phase == "markdown"
    assert exc_info.value.quality_result.reason == "section source binding is incomplete"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py -q
```

Expected: FAIL because `app.orchestration.guards` does not exist.

- [ ] **Step 3: Implement enter guards**

Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/guards.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from app.orchestration.contracts import ContractError, blocking_quality


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _text_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def require_profile_for_intake(state: dict) -> None:
    profile = state.get("profile")
    if isinstance(profile, dict) and profile.get("type") == "basic_profile":
        confirmed_info = profile.get("confirmed_info")
        if isinstance(confirmed_info, dict) and confirmed_info:
            return
    raise ContractError(
        "learning_path_intake_agent",
        "intake",
        "profile is not complete",
        blocking_quality("profile is not complete"),
    )


def require_confirmed_intake_for_learning_path(state: dict) -> None:
    intake = state.get("learning_path_intake")
    if isinstance(intake, dict) and intake.get("status") == "confirmed":
        return
    raise ContractError(
        "learning_path_agent",
        "path",
        "learning_path_intake.status is not confirmed",
        blocking_quality("learning_path_intake.status is not confirmed"),
    )


def require_course_source_for_course_knowledge(course: dict) -> None:
    if _clean_text(course.get("source_textbook_id")) and _text_list(
        course.get("source_outline_section_ids")
    ):
        return
    raise ContractError(
        "course_knowledge_agent",
        "outline",
        "course source binding is incomplete",
        blocking_quality("course source binding is incomplete"),
    )


def require_section_source_for_markdown(section: dict) -> None:
    if _clean_text(section.get("source_textbook_id")) and _text_list(
        section.get("source_section_ids")
    ):
        return
    raise ContractError(
        "section_markdown_agent",
        "markdown",
        "section source binding is incomplete",
        blocking_quality("section source binding is incomplete"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py -q
```

Expected: PASS.

### Task 3: Wire Guards Into Existing Agent Inputs

**Files:**
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path_intake.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_knowledge.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_intake_agent_contract.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_agent_contract.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_knowledge_agent_contract.py`
- Modify: `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`

- [ ] **Step 1: Add focused tests around existing input builders**

Add one test to each contract test file, using the exact helper functions already imported in those files.

For `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_intake_agent_contract.py`, add:

```python
def test_intake_input_requires_complete_profile_before_prompt_building() -> None:
    with pytest.raises(Exception) as exc_info:
        _build_intake_generation_input({"profile": {"type": "collecting"}}, "AI 应用开发")

    assert "profile is not complete" in str(exc_info.value)
```

For `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_agent_contract.py`, add:

```python
def test_learning_path_input_requires_confirmed_intake_before_prompt_building() -> None:
    state = _state()
    state["learning_path_intake"]["status"] = "draft"

    with pytest.raises(Exception) as exc_info:
        _build_analysis_input(state)

    assert "learning_path_intake.status is not confirmed" in str(exc_info.value)
```

For `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_knowledge_agent_contract.py`, add:

```python
def test_course_knowledge_input_requires_course_source_binding_before_prompt_building() -> None:
    course = _current_course()
    course.pop("source_textbook_id")

    with pytest.raises(Exception) as exc_info:
        _build_analysis_input(_state(), course)

    assert "course source binding is incomplete" in str(exc_info.value)
```

For `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`, add:

```python
def test_markdown_input_requires_section_source_binding_before_prompt_building() -> None:
    outline = _outline()
    section = _section_by_id(outline, "1.1")
    assert section is not None

    with pytest.raises(Exception) as exc_info:
        _markdown_input({"profile": _profile(), "year_learning_paths": _year_learning_paths()}, outline, section)

    assert "section source binding is incomplete" in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_learning_path_intake_agent_contract.py::test_intake_input_requires_complete_profile_before_prompt_building tests/test_learning_path_agent_contract.py::test_learning_path_input_requires_confirmed_intake_before_prompt_building tests/test_course_knowledge_agent_contract.py::test_course_knowledge_input_requires_course_source_binding_before_prompt_building tests/test_course_resource_agent_contract.py::test_markdown_input_requires_section_source_binding_before_prompt_building -q
```

Expected: FAIL until input builders call guard functions.

- [ ] **Step 3: Add guard imports and calls**

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path_intake.py`, import and call before building the intake prompt:

```python
from app.orchestration.guards import require_profile_for_intake
```

Inside `_build_intake_generation_input`, before reading profile fields:

```python
    require_profile_for_intake(state)
```

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path.py`, import and call:

```python
from app.orchestration.guards import require_confirmed_intake_for_learning_path
```

Inside `_build_analysis_input`, before deriving the intake courses:

```python
    require_confirmed_intake_for_learning_path(state)
```

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_knowledge.py`, import and call:

```python
from app.orchestration.guards import require_course_source_for_course_knowledge
```

Inside `_build_analysis_input`, before payload construction:

```python
    require_course_source_for_course_knowledge(course)
```

Inside `_build_year_analysis_input`, call the same guard for each course dict that is sent to the outline agent.

In `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`, import:

```python
from app.orchestration.guards import require_section_source_for_markdown
```

Inside `_markdown_input`, before `_resource_context(state, outline, section)`:

```python
    require_section_source_for_markdown(section)
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_learning_path_intake_agent_contract.py::test_intake_input_requires_complete_profile_before_prompt_building tests/test_learning_path_agent_contract.py::test_learning_path_input_requires_confirmed_intake_before_prompt_building tests/test_course_knowledge_agent_contract.py::test_course_knowledge_input_requires_course_source_binding_before_prompt_building tests/test_course_resource_agent_contract.py::test_markdown_input_requires_section_source_binding_before_prompt_building -q
```

Expected: PASS.

### Task 4: Format, Run Phase Tests, Commit

**Files:**
- All files changed in this phase.

- [ ] **Step 1: Run Ruff**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run ruff check --fix app/orchestration/contracts.py app/orchestration/guards.py app/orchestration/agents/learning_path_intake.py app/orchestration/agents/learning_path.py app/orchestration/agents/course_knowledge.py app/orchestration/agents/course_resources/markdown.py tests/test_orchestration_contract_guards.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py
uv run ruff format app/orchestration/contracts.py app/orchestration/guards.py app/orchestration/agents/learning_path_intake.py app/orchestration/agents/learning_path.py app/orchestration/agents/course_knowledge.py app/orchestration/agents/course_resources/markdown.py tests/test_orchestration_contract_guards.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py
```

Expected: commands complete successfully.

- [ ] **Step 2: Run phase tests**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py tests/test_course_resource_agent_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

Run:

```bash
cd /Users/torch/torch/opt/mutiagent
git add backend/app/orchestration/contracts.py backend/app/orchestration/guards.py backend/app/orchestration/agents/learning_path_intake.py backend/app/orchestration/agents/learning_path.py backend/app/orchestration/agents/course_knowledge.py backend/app/orchestration/agents/course_resources/markdown.py backend/tests/test_orchestration_contract_guards.py backend/tests/test_learning_path_intake_agent_contract.py backend/tests/test_learning_path_agent_contract.py backend/tests/test_course_knowledge_agent_contract.py backend/tests/test_course_resource_agent_contract.py
git commit -m "feat: add orchestration contract guards"
```

Expected: commit succeeds.
